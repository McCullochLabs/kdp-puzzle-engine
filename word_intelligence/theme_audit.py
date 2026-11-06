"""Theme auditing: does each production theme's vocabulary hold up?

For every theme we resolve its intended topic, grade every puzzle word
(on-topic / related / weak / off-topic / flagged), detect intra-theme
duplicates, and suggest replacements drawn from the same topic's strong
pool.  Audits are READ-ONLY - they never rewrite themes.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .analysis import words_for_topic
from .normalization import clean_surface
from .quality import PuzzleWorthiness, assess_quality
from .records import APPROVED, TRUSTED, band_of

# Grade-vocabulary topics are deliberate catch-alls; membership there says
# nothing about topical fit and must never act as "points elsewhere" proof.
_CATCH_ALL_PATTERN = re.compile(
    r"^(grade(\s+\d+)?(\s+school)?|middle\s+school|high\s+school|elementary)$",
    re.IGNORECASE)


def _is_catch_all_topic(taxonomy, topic_id: str) -> bool:
    topic = taxonomy.topics.get(topic_id)
    if topic is None:
        return False
    names = [topic.display_name, *topic.aliases]
    for name in names:
        cleaned = re.sub(r"\s*vocabulary\b", "", name or "", flags=re.IGNORECASE).strip()
        if _CATCH_ALL_PATTERN.match(cleaned):
            return True
    return False


VERDICT_PASS = "PASS"
VERDICT_PASS_WITH_NOTES = "PASS_WITH_NOTES"
VERDICT_REVIEW_REQUIRED = "REVIEW_REQUIRED"
VERDICT_FAIL = "FAIL"


@dataclass
class WordFinding:
    normalized: str
    display: str
    status: str          # on_topic | related | likely_ok | weak | off_topic | flagged | duplicate
    detail: str = ""
    puzzle_index: int = -1   # which puzzle the occurrence came from (-1 = file-level)

    def to_dict(self) -> dict:
        return {"word": self.display, "normalized": self.normalized,
                "status": self.status, "detail": self.detail,
                "puzzle_index": self.puzzle_index}


@dataclass
class ThemeAuditReport:
    theme_file: str
    title: str = ""
    target_topics: list[str] = field(default_factory=list)
    target_resolution: str = ""      # how the target was determined
    word_count: int = 0
    findings: list[WordFinding] = field(default_factory=list)
    suggestions: dict[str, list[str]] = field(default_factory=dict)
    duplicate_pairs: list[tuple] = field(default_factory=list)
    verdict: str = VERDICT_REVIEW_REQUIRED
    notes: list[str] = field(default_factory=list)
    # Parsed source data, when the report came from a file. Carried so
    # downstream passes (inventory/repair) never re-read/re-parse themes.
    theme_data: dict | None = None

    def to_dict(self) -> dict:
        return {
            "theme_file": self.theme_file,
            "title": self.title,
            "target_topics": self.target_topics,
            "target_resolution": self.target_resolution,
            "word_count": self.word_count,
            "verdict": self.verdict,
            "notes": list(self.notes),
            "counts": _status_counts(self.findings),
            "findings": [f.to_dict() for f in self.findings],
            "suggestions": {k: v for k, v in sorted(self.suggestions.items())},
            "duplicate_pairs": [list(p) for p in self.duplicate_pairs],
        }


def _status_counts(findings) -> dict:
    out: dict[str, int] = {}
    for finding in findings:
        out[finding.status] = out.get(finding.status, 0) + 1
    return out


def resolve_target_topics(theme: dict, taxonomy) -> tuple[list[str], str]:
    anchor = theme.get("source_word_bank") or {}
    raw = anchor.get("topics") or []
    if isinstance(raw, str):
        raw = [raw]
    cids = [c for c in (taxonomy.resolve(r) for r in raw) if c]
    if cids:
        return cids, "source_word_bank"

    cid = taxonomy.resolve(theme.get("detected_topic") or "")
    if cid:
        return [cid], "detected_topic"

    # Token-based title match: a legacy file titled "Christmas Word Search
    # Puzzles" should anchor to the Christmas topic even though its cleaned
    # title never equals an alias string. Multi-token aliases must appear in
    # full inside the title; a single-token alias is accepted only when that
    # token is specific enough (used by at most a few topics) so generic
    # words like "Fun" or "Party" can never hijack a book.
    from .taxonomy import _name_tokens_in_order

    title_set = set(_name_tokens_in_order(str(theme.get("title") or "")))
    if title_set:
        token_topics: dict[str, set[str]] = {}
        for slug, topic in taxonomy.topics.items():
            for alias in topic.aliases:
                for token in _name_tokens_in_order(alias):
                    token_topics.setdefault(token, set()).add(slug)
        best_slug, best_len = "", 0
        for slug, topic in taxonomy.topics.items():
            for alias in topic.aliases:
                alias_tokens = _name_tokens_in_order(alias)
                if not alias_tokens:
                    continue
                if len(alias_tokens) == 1:
                    token = alias_tokens[0]
                    if len(token_topics.get(token, ())) > 3 or token not in title_set:
                        continue
                elif not (set(alias_tokens) <= title_set):
                    continue
                if len(alias_tokens) > best_len:
                    best_slug, best_len = slug, len(alias_tokens)
        if best_slug:
            return [best_slug], "title_match"
    return [], "unresolved"


def _classify_word(norm, record, targets, related_ids, taxonomy,
                   compatible_ids=None, sibling_ids=None) -> WordFinding:
    """Grade one word against the theme's target topics.

    ``compatible_ids`` is the multi-anchor closure (target + taxonomy
    neighbours + curated anchor pairs).  Words pointing only inside it are
    legitimately themed and must not fail the book.  ``sibling_ids`` (same
    family) softens a bare off_topic to weak: still surfaced for review,
    never silently accepted.
    """
    display = record.display if record else norm.title()
    compatible_ids = compatible_ids or set()
    sibling_ids = sibling_ids or set()
    if record is None:
        return WordFinding(norm, norm.title(), "unverified",
                           "Unknown to the intelligence store")
    if record.safety_review:
        return WordFinding(norm, display, "flagged", "Exclusion flag")
    if record.trademark_review:
        return WordFinding(norm, display, "flagged", "Trademark-review term")
    if not targets:
        # No resolved topic context: the word cannot be judged off-topic.
        return WordFinding(norm, display, "unverified",
                           "Theme topic unresolved")

    quality = assess_quality(record)
    if quality.worthiness == PuzzleWorthiness.EXCLUDE:
        return WordFinding(norm, display, "weak",
                           "; ".join(quality.reasons))

    links = [l for l in record.topics if l.topic_id in targets]
    for link in links:
        if link.status in (TRUSTED, APPROVED):
            return WordFinding(norm, display, "on_topic")
    for link in links:
        if band_of(link.confidence) in ("very_high", "high"):
            return WordFinding(norm, display, "likely_ok",
                               f"Strong proposal ({link.confidence:.0f})")

    if record.ambiguous_senses:
        return WordFinding(norm, display, "weak",
                           "Ambiguous senses unresolved")

    if any(l.topic_id in related_ids for l in record.topics):
        return WordFinding(norm, display, "related",
                           "Belongs to a neighbouring topic")
    anchors_hit = sorted({l.topic_id for l in record.topics
                          if l.topic_id in compatible_ids})
    if anchors_hit:
        names = "/".join(taxonomy.display_name(c) for c in anchors_hit[:3])
        return WordFinding(norm, display, "related",
                           f"Multi-anchor match via {names}")

    elsewhere = [l for l in record.topics
                 if not _is_catch_all_topic(taxonomy, l.topic_id)
                 and (l.status in (TRUSTED, APPROVED)
                      or band_of(l.confidence) in ("very_high", "high"))]
    if elsewhere:
        others = "/".join(sorted({l.topic_id for l in elsewhere})[:3])
        return WordFinding(norm, display, "off_topic", f"Points elsewhere: {others}")

    # Only weak/medium counter-evidence exists: not enough to accuse the
    # word of being off-topic, but worth surfacing as unresolved context.
    if record.topics:
        return WordFinding(norm, display, "unverified",
                           "Only weak competing signals so far")

    if record.topics:
        # Only catch-all memberships: nothing topical to judge with yet.
        return WordFinding(norm, display, "unverified",
                           "Only grade-vocabulary membership so far")

    if quality.worthiness == PuzzleWorthiness.REVIEW:
        return WordFinding(norm, display, "weak", "; ".join(quality.reasons))
    if record.frequency is not None and record.frequency < 2.6:
        return WordFinding(norm, display, "weak",
                           f"Obscure (zipf {record.frequency:.1f}), no topic tie")
    # No links anywhere and nothing suspicious: merely unclassified so far.
    return WordFinding(norm, display, "unverified",
                       "No classification evidence yet")


def _best_anchor(puzzle_words, anchors, store) -> str:
    """Pick the anchor topic with the most exact lexicon hits in a puzzle."""
    best, best_hits = anchors[0], -1
    for cid in anchors:
        lexicon = store.topic_lexicon.get(cid, set())
        hits = sum(1 for w in puzzle_words if w in lexicon)
        if hits > best_hits:
            best, best_hits = cid, hits
    return best


def audit_theme(theme_data: dict, theme_file: str, store, taxonomy,
                suggest_count: int = 5) -> ThemeAuditReport:
    report = ThemeAuditReport(
        theme_file=theme_file,
        title=theme_data.get("title") or "",
    )
    file_targets, resolution = resolve_target_topics(theme_data, taxonomy)
    report.target_topics = file_targets
    report.target_resolution = resolution

    # Collect words per puzzle (order-preserving).
    puzzle_words: list[list[str]] = []
    seen_norms: dict[str, int] = {}
    all_words: list[str] = []
    for puzzle in theme_data.get("puzzles") or []:
        words_here: list[str] = []
        for raw in puzzle.get("words") or []:
            norm = clean_surface(raw)
            if not norm:
                continue
            words_here.append(norm)
            all_words.append(norm)
            seen_norms[norm] = seen_norms.get(norm, 0) + 1
        puzzle_words.append(words_here)
    report.word_count = len(all_words)

    # Multi-topic word-bank files (100-themed banks etc.) must judge each
    # puzzle against ITS OWN best-matching anchor, not one file-wide topic.
    # Files with no resolvable anchor fall back to per-puzzle names.
    multi_anchor = len(file_targets) > 1
    related_cache: dict[str, set[str]] = {}
    findings_by_norm: dict[str, WordFinding] = {}
    used_puzzle_names = False

    for puzzle_index, (puzzle, words_here) in enumerate(
            zip(theme_data.get("puzzles") or [], puzzle_words)):
        if multi_anchor:
            targets = [_best_anchor(words_here, file_targets, store)]
        elif file_targets:
            targets = list(file_targets)
        else:
            name_cid = taxonomy.resolve(str(puzzle.get("name") or ""))
            targets = [name_cid] if name_cid else []
            if name_cid:
                used_puzzle_names = True
        key = targets[0] if targets else ""
        if key not in related_cache:
            from .anchors import compatibility_closure, family_sibling_ids
            related: set[str] = set()
            compatible: set[str] = set()
            for cid in targets:
                related |= taxonomy.related_closure(cid, hops=1)
                compatible |= compatibility_closure(taxonomy, cid)
            related_cache[key] = (related, compatible,
                                  family_sibling_ids(taxonomy, key))
        related, compatible, siblings = related_cache[key]
        for norm in words_here:
            record = store.get(norm)
            finding = _classify_word(norm, record, set(targets), related,
                                     taxonomy, compatible_ids=compatible,
                                     sibling_ids=siblings)
            finding.puzzle_index = puzzle_index
            existing = findings_by_norm.get(norm)
            if existing is None or (existing.status == "off_topic"
                                    and finding.status != "off_topic"):
                findings_by_norm[norm] = finding
            report.findings.append(finding)

    if used_puzzle_names:
        report.target_resolution += "+puzzle_name"

    # Mark repeats (same word used multiple times inside one theme).
    # Keep-first semantics: the first occurrence keeps its original status;
    # every later occurrence is reported as a duplicate finding.
    from publishing.repetition_policy import requested as repetition_requested, evaluate as evaluate_repetition
    repetition = evaluate_repetition(theme_data) if repetition_requested(theme_data) else None
    bounded_repetition = bool(repetition and repetition["passed"])
    if bounded_repetition:
        report.notes.append("Approved collection repetition limits passed; every occurrence still retains its topic/safety classification.")
    seen_once: set[str] = set()
    for norm, count in seen_norms.items():
        if count > 1 and norm in findings_by_norm and not bounded_repetition:
            dup = findings_by_norm[norm]
            dup.status = "duplicate"
            dup.detail = f"Used {count}x in this theme"
            report.duplicate_pairs.append((norm, count))
    if report.duplicate_pairs:
        repeated = {norm for norm, _count in report.duplicate_pairs}
        for finding in report.findings:
            if finding.normalized in repeated:
                if finding.normalized in seen_once:
                    finding.status = "duplicate"
                    finding.detail = "Repeated within the same theme"
                else:
                    seen_once.add(finding.normalized)

    counts = _status_counts(report.findings)

    # Replacement suggestions from strong same-topic pools.
    bad = [f for f in report.findings
           if f.status in ("weak", "off_topic", "duplicate")]
    if file_targets or multi_anchor:
        pool_source = file_targets[0] if file_targets else ""
        pool = [w for w in words_for_topic(store, pool_source, min_band="high")
                if w not in set(all_words)]
        pool_set = set(pool)
        for finding in bad[:suggest_count * 3]:
            if len(report.suggestions) >= suggest_count * 3:
                break
            candidates = [w for w in sorted(pool_set)[:40]
                          if abs(len(w) - len(finding.normalized)) <= 4][:suggest_count]
            if candidates:
                report.suggestions[finding.normalized] = candidates

    # Verdict rules (mission §28). Order matters: safety failures outrank
    # everything; an unresolved topic blocks off-topic judgement entirely.
    flagged = counts.get("flagged", 0)
    off_topic = counts.get("off_topic", 0)
    weak = counts.get("weak", 0)
    unverified = counts.get("unverified", 0)
    if flagged:
        report.verdict = VERDICT_FAIL
        report.notes.append(f"{flagged} flagged word(s)")
    elif not file_targets:
        report.verdict = VERDICT_REVIEW_REQUIRED
        report.notes.append("Target topic could not be resolved")
    elif off_topic > max(2, report.word_count // 20):
        report.verdict = VERDICT_FAIL
        report.notes.append(f"{off_topic} clearly off-topic word(s)")
    elif weak or off_topic or report.duplicate_pairs or unverified:
        report.verdict = VERDICT_PASS_WITH_NOTES
        if weak:
            report.notes.append(f"{weak} weak word(s)")
        if off_topic:
            report.notes.append(f"{off_topic} unverified word(s)")
        if unverified:
            report.notes.append(f"{unverified} unverifiable (no topic anchor)")
        if report.duplicate_pairs:
            report.notes.append("Duplicate words inside theme")
    else:
        report.verdict = VERDICT_PASS
    if repetition and not repetition["passed"]:
        report.verdict = VERDICT_FAIL
        report.notes.extend(repetition["errors"])
    return report


def load_theme(path) -> dict | None:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def audit_theme_file(path, store, taxonomy, **kwargs) -> ThemeAuditReport | None:
    data = load_theme(path)
    if data is None:
        return None
    report = audit_theme(data, str(path), store, taxonomy, **kwargs)
    report.theme_data = data   # carried for downstream passes; no re-parse
    return report


def audit_all_themes(themes_dir, store, taxonomy, limit: int | None = None) -> dict:
    """Audit every theme JSON under a directory; returns summary."""
    reports = []
    skipped = 0
    paths = sorted(Path(themes_dir).rglob("*.json"))
    for path in paths:
        if limit is not None and len(reports) >= limit:
            break
        report = audit_theme_file(path, store, taxonomy)
        if report is None:
            skipped += 1
            continue
        reports.append(report)
    verdict_counts: dict[str, int] = {}
    for report in reports:
        verdict_counts[report.verdict] = verdict_counts.get(report.verdict, 0) + 1
    return {
        "themes_scanned": len(paths),
        "audited": len(reports),
        "skipped_unreadable": skipped,
        "verdicts": verdict_counts,
        "reports": reports,
    }
