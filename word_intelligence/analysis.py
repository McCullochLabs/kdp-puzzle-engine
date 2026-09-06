"""Topic health, capacity estimation and coverage analytics.

Reads the store/taxonomy and produces plain dict reports for the GUI,
CLI and saved reports.  Extends the master bank's existing capacity idea
(unique words -> no-repeat puzzles/books) with confidence-stratified
eligibility so publishers can see what is safely usable TODAY versus what
more classification would unlock.
"""

from __future__ import annotations

from .quality import (
    PuzzleWorthiness,
    assess_quality,
    exclusivity_score,
)
from .records import (
    APPROVED,
    PROPOSED,
    TRUSTED,
    band_of,
)

STANDARD_BOOK_WORDS = 576   # 48 puzzles x 12 words
SIGNATURE_BOOK_WORDS = 1200


def _usable(record, min_band: str = "medium") -> bool:
    """A word counts toward capacity when a human or confident classifier
    ties it to the topic AND its quality is placeable."""
    if record.safety_review:
        return False
    quality = assess_quality(record)
    if quality.worthiness in (PuzzleWorthiness.EXCLUDE, PuzzleWorthiness.REVIEW):
        return False
    band_order = {"low": 0, "medium": 1, "high": 2, "very_high": 3}
    threshold = band_order[min_band]
    for link in record.topics:
        if link.status in (TRUSTED, APPROVED):
            return True
        if link.status == PROPOSED and band_order[band_of(link.confidence)] >= threshold:
            return True
    return False


def words_for_topic(store, topic_id: str, min_band: str = "medium") -> list[str]:
    out = []
    for norm, record in sorted(store.records.items()):
        if any(l.topic_id == topic_id for l in record.topics) and _usable(record, min_band):
            out.append(norm)
    return out


def estimate_capacity(words_count: int, words_per_puzzle: int,
                      max_word_reuse: int = 0) -> dict:
    """No-repeat book math mirroring the master bank's own conventions.

    ``max_word_reuse`` > 0 models controlled reuse: each word may appear in
    up to that many puzzles, which is how narrow niches survive large book
    requests (spec PART O/AS).  The default keeps the historic unique-only
    semantics.
    """
    if words_per_puzzle <= 0:
        return {
            "unique_words": words_count,
            "no_repeat_0_word_puzzles": 0,
            "books_48_puzzles": 0,
            "books_100_puzzles": 0,
        }
    effective = words_count * (max_word_reuse + 1) if max_word_reuse else words_count
    puzzles = effective // words_per_puzzle
    key = (f"no_repeat_{words_per_puzzle}_word_puzzles"
           if not max_word_reuse else
           f"reuse_x{max_word_reuse}_{words_per_puzzle}_word_puzzles")
    return {
        "unique_words": words_count,
        "max_word_reuse": max_word_reuse,
        key: puzzles,
        "books_48_puzzles": puzzles // 48,
        "books_100_puzzles": puzzles // 100,
    }


def topic_capacity_report(store, taxonomy, topic_id: str,
                          requested_sizes=((12, 48), (15, 50), (20, 100))) -> dict:
    """Quality-stratified capacity for one topic (spec PART G / PART O).

    Answers 'can this niche support a commercial book?' honestly: raw
    vocabulary counts are separated from genuinely usable capacity after
    quality tiers and repetition constraints.
    """
    cid = taxonomy.resolve(topic_id)
    if not cid:
        return {"topic_id": topic_id, "resolved": False}
    members = [store.get(n) for n in words_for_topic(store, cid, min_band="low")]
    tiers = {"excellent": 0, "good": 0, "acceptable": 0, "review": 0}
    safe_pool: list[str] = []
    trusted = 0
    from .records import APPROVED, PROPOSED, TRUSTED, band_of
    for record in members:
        quality = assess_quality(record)
        if quality.worthiness == PuzzleWorthiness.PREFERRED:
            tiers["excellent"] += 1
            safe_pool.append(record.normalized)
        elif quality.worthiness == PuzzleWorthiness.ACCEPTABLE:
            tiers["good" if quality.familiarity in ("common", "familiar")
                  else "acceptable"] += 1
            safe_pool.append(record.normalized)
        elif quality.worthiness == PuzzleWorthiness.SPECIALIZED:
            tiers["acceptable"] += 1
        else:
            tiers["review"] += 1
        link = record.link_for(cid)
        if link and link.status in (TRUSTED, APPROVED):
            trusted += 1

    sizes = {}
    for words_per, target_count in requested_sizes:
        strict = estimate_capacity(tiers["excellent"] + tiers["good"],
                                   words_per)["no_repeat_%d_word_puzzles" % words_per] \
            if words_per else 0
        relaxed = estimate_capacity(len(safe_pool), words_per,
                                    max_word_reuse=2)[f"reuse_x2_{words_per}_word_puzzles"]
        sizes[words_per] = {
            "unique_only_capacity": strict,
            "supports_requested_books": strict >= target_count,
            "controlled_reuse_capacity_x2": relaxed,
            "reuse_supports_requested_books": relaxed >= target_count,
        }
    return {
        "topic_id": cid,
        "display_name": taxonomy.display_name(cid),
        "resolved": True,
        "tiers": tiers,
        "trusted_words": trusted,
        "safe_unique_pool": len(safe_pool),
        "capacity": sizes,
    }


def topic_health(store, taxonomy, min_band: str = "medium") -> list[dict]:
    """One health row per canonical topic, worst first."""
    rows = []
    for cid, topic in sorted(taxonomy.topics.items()):
        members = words_for_topic(store, cid, min_band)
        vh = high = med = 0
        for norm in members:
            record = store.get(norm)
            for link in record.topics:
                if link.topic_id == cid and link.status == PROPOSED:
                    band = band_of(link.confidence)
                    if band == "very_high":
                        vh += 1
                    elif band == "high":
                        high += 1
                    elif band == "medium":
                        med += 1
        trusted = sum(
            1 for norm in members
            if any(l.topic_id == cid and l.status in (TRUSTED, APPROVED)
                   for l in store.get(norm).topics))
        cap12 = estimate_capacity(len(members), 12)
        cap20 = estimate_capacity(len(members), 20)
        grade = _grade(len(members), topic.min_vocabulary_target)
        rows.append({
            "topic_id": cid,
            "display_name": topic.display_name,
            "family": topic.family,
            "usable_words": len(members),
            "trusted_words": trusted,
            "proposed_very_high": vh,
            "proposed_high": high,
            "proposed_medium": med,
            "grade": grade,
            "ready_standard_book": len(members) >= STANDARD_BOOK_WORDS,
            "ready_signature_book": len(members) >= SIGNATURE_BOOK_WORDS,
            "capacity_12w": cap12,
            "capacity_20w": cap20,
            "min_target": topic.min_vocabulary_target,
            "signature_target": topic.signature_target,
        })
    rows.sort(key=lambda r: (r["usable_words"], r["display_name"]))
    return rows


def _grade(usable: int, target: int) -> str:
    ratio = usable / target if target else 0
    if usable >= SIGNATURE_BOOK_WORDS:
        return "A"
    if ratio >= 1.0:
        return "B"
    if ratio >= 0.5:
        return "C"
    if ratio >= 0.25:
        return "D"
    return "F"


def coverage_summary(store) -> dict:
    records = list(store.records.values())
    confirmed = [r for r in records if not r.is_unclassified()]
    bands = {"very_high": 0, "high": 0, "medium": 0, "low": 0}
    proposals = 0
    for record in records:
        for link in record.topics:
            if link.status == PROPOSED:
                proposals += 1
                bands[band_of(link.confidence)] += 1
    return {
        "total_records": len(records),
        "dictionary_words": len(store.dictionary_words),
        "confirmed_records": len(confirmed),
        "unclassified_records": len(records) - len(confirmed),
        "open_proposals": proposals,
        "proposal_bands": bands,
        "trademark_review": sum(1 for r in records if r.trademark_review),
        "safety_rejected": sum(1 for r in records if r.safety_review),
        "stale_classifier_runs": sum(
            1 for r in records
            if r.last_classified and not r.classifier_version),
    }


def duplicate_topic_warnings(taxonomy) -> list[dict]:
    """Near-duplicate topics needing curation decisions (not auto-merged)."""
    warnings = []
    for cand in taxonomy.merge_candidates:
        id_a = taxonomy.resolve(cand["a"])
        id_b = taxonomy.resolve(cand["b"])
        a, b = taxonomy.topics.get(id_a or ""), taxonomy.topics.get(id_b or "")
        if not a or not b:
            continue
        words_a = taxonomy.trusted_words.get(id_a, set())
        words_b = taxonomy.trusted_words.get(id_b, set())
        overlap_a = sum(1 for w in words_a if w in words_b)
        warnings.append({
            "a": cand["a"], "b": cand["b"],
            "display_a": a.display_name, "display_b": b.display_name,
            "jaccard": round(cand["jaccard"], 3),
            "shared_words": overlap_a,
            "same_family": a.family == b.family,
        })
    return warnings


def exclusive_words_preview(store, topic_id: str, limit: int = 25) -> list[str]:
    """Highly loyal, human-trusted vocabulary for a topic - puzzle anchors."""
    scored = []
    for norm in words_for_topic(store, topic_id):
        record = store.get(norm)
        link = record.link_for(topic_id)
        if link is None or link.status not in (TRUSTED, APPROVED):
            continue
        score = exclusivity_score(record, topic_id)
        if score >= 0.9:
            scored.append((norm, score))
    scored.sort(key=lambda pair: (-pair[1], pair[0]))
    return [norm for norm, _ in scored[:limit]]
