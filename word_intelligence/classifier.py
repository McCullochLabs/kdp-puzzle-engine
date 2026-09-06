"""Deterministic word->topic classifier.

Combines signal evidence into confidence scores with explainable evidence,
respecting human decisions (approvals/rejections always win) and never
touching trusted master-bank membership.

Confidence bands (mission §6):
    >=95 VERY_HIGH  auto-linkable (apply engine may connect after sampling gate)
    80-94 HIGH      surfaced for periodic audit
    60-79 MEDIUM    routed to the human review queue
    <60  LOW        recorded only as context; never connected
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .records import (
    APPROVED,
    CLASSIFIER_VERSION,
    PROPOSED,
    REJECTED,
    TRUSTED,
    EvidenceItem,
    SIGNAL_AMBIGUITY,
    SIGNAL_THEME_HISTORY,
    TopicLink,
    band_of,
)
from .signals import (
    detect_ambiguity,
    damped_total,
    negative_evidence,
    TopicSignalIndex,
)

# Minimum score worth recording as a proposal; below this we simply leave
# the word unclassified rather than filling reports with noise.
PROPOSAL_FLOOR = 40.0

AUTO_LINK_MIN = 95.0     # VERY_HIGH
AUDIT_BAND_MIN = 80.0    # HIGH
POINTS_GATE = 85.0       # exact-lexicon strength (kept for report tooling)


@dataclass
class RunStats:
    words_seen: int = 0
    words_classified: int = 0       # received at least one proposal
    proposals: int = 0
    very_high: int = 0
    high: int = 0
    medium: int = 0
    ambiguous_words: int = 0
    skipped_human_decisions: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "words_seen": self.words_seen,
            "words_classified": self.words_classified,
            "proposals": self.proposals,
            "very_high": self.very_high,
            "high": self.high,
            "medium": self.medium,
            "ambiguous_words": self.ambiguous_words,
            "skipped_human_decisions": self.skipped_human_decisions,
            "errors": list(self.errors),
        }


class Classifier:
    """Scores candidate topics for words and records PROPOSED links."""

    def __init__(self, store, taxonomy, ambiguity_registry=None) -> None:
        self.store = store
        self.taxonomy = taxonomy
        self.index = TopicSignalIndex(store, taxonomy)
        self.families = {cid: t.family for cid, t in taxonomy.topics.items()}
        from .ambiguity import AmbiguityRegistry, ambiguity_guard
        self.ambiguity_registry = ambiguity_registry or AmbiguityRegistry()
        self._ambiguity_guard = ambiguity_guard

    # ------------------------------------------------------------------

    def prepare(self, catalog: dict | None = None, themes_dir=None) -> dict:
        """Build indexes once per run (theme scan is the slow part)."""
        attached = 0
        if catalog:
            resolve = self.taxonomy.resolve
            attached = self.index.attach_root_suggestions(catalog, resolve)
        themes = 0
        if themes_dir:
            themes = self.index.build_theme_index(themes_dir)
        return {"root_suggestions": attached, "themes_scanned": themes}

    def score_word(self, record) -> list[TopicLink]:
        """Score every viable topic for a word. Pure - returns new links."""
        norm = record.normalized
        existing = {l.topic_id: l for l in record.topics}
        blocked = {cid for cid, l in existing.items() if l.status == REJECTED}
        approved = {cid for cid, l in existing.items()
                    if l.status == APPROVED or l.status == TRUSTED}
        candidates = sorted(self.index.candidate_topics(norm) - blocked)

        scored: list[tuple[str, float, list]] = []
        for cid in candidates:
            if cid in approved:
                continue  # human/trusted association already owns this pair
            evidence = self.index.evaluate(record, cid)
            neg = negative_evidence(record, cid, self.taxonomy)
            if neg is not None:
                evidence.append(neg)
            weights = [e.weight for e in evidence]
            total = damped_total(weights)
            conf = max(0.0, min(99.0, total))
            prior_links = [TopicLink(t, PROPOSED, c) for t, c, _ in scored]
            guard = self._ambiguity_guard(
                record, self.ambiguity_registry, self.families, prior_links)
            if guard < 1.0:
                conf *= guard
                evidence.append(EvidenceItem(
                    SIGNAL_AMBIGUITY,
                    "Score damped: word has unresolved alternate senses", 0.0))
            # WI2 Phase 3 promotion guard: VERY_HIGH must rest on more than
            # theme-history repetition.  Without an independent anchor-grade
            # signal (exact lexicon / curated research / strong phrase
            # support) the link is capped inside the audited HIGH band.
            if conf >= AUTO_LINK_MIN:
                independent = [e for e in evidence
                               if e.signal != SIGNAL_THEME_HISTORY
                               and e.weight >= 60]
                history_only = [e for e in evidence
                                if e.signal == SIGNAL_THEME_HISTORY]
                if not independent and history_only:
                    conf = min(conf, AUDIT_BAND_MIN + 9.0)
                    evidence.append(EvidenceItem(
                        "promotion_guard",
                        "Theme history alone capped below auto-promotion",
                        0.0))
            if conf >= PROPOSAL_FLOOR:
                scored.append((cid, conf, evidence))

        links: list[TopicLink] = []
        for cid, conf, evidence in scored:
            links.append(TopicLink(
                topic_id=cid,
                status=PROPOSED,
                confidence=round(conf, 1),
                evidence=list(evidence),
                classifier_version=CLASSIFIER_VERSION,
            ))
        return links

    def classify_record(self, record, stats: RunStats | None = None) -> int:
        """Apply scoring to one record in place; returns proposals added."""
        stats = stats or RunStats()
        before_ids = {(l.topic_id, l.status) for l in record.topics}
        new_links = self.score_word(record)

        kept = [l for l in record.topics if l.status != PROPOSED]
        by_topic = {l.topic_id: l for l in kept}
        added = 0
        top_pairs: list[tuple[str, float]] = []
        for link in new_links:
            prev = by_topic.get(link.topic_id)
            if prev is not None and prev.confidence >= link.confidence:
                link = prev  # never silently downgrade an earlier decision
            by_topic[link.topic_id] = link
            if (link.topic_id, link.status) not in before_ids:
                added += 1
            top_pairs.append((link.topic_id, link.confidence))

        amb, competing = detect_ambiguity(top_pairs, self.families)
        senses: list[str] = []
        if amb is not None and new_links:
            senses = [new_links[0].topic_id]
            if competing:
                senses.append(competing)

        record.topics = sorted(by_topic.values(),
                               key=lambda l: (-l.confidence, l.topic_id))
        record.ambiguous_senses = senses
        record.last_classified = datetime.now().isoformat(timespec="seconds")
        record.classifier_version = CLASSIFIER_VERSION

        stats.words_seen += 1
        if added:
            stats.words_classified += 1
        stats.proposals += len(new_links)
        if senses:
            stats.ambiguous_words += 1
        for link in new_links:
            band = band_of(link.confidence)
            if band == "very_high":
                stats.very_high += 1
            elif band == "high":
                stats.high += 1
            elif band == "medium":
                stats.medium += 1
        return added

    def classify_many(self, records, stats: RunStats | None = None) -> RunStats:
        stats = stats or RunStats()
        for record in records:
            try:
                self.classify_record(record, stats)
            except Exception as exc:  # keep runs going; surface at end
                stats.errors.append(f"{record.normalized}: {exc}")
        return stats


def scope_records(store, scope: str):
    """Word selection scopes (mission §52)."""
    if scope == "proven":
        return [r for r in store.records.values() if r.sources]
    if scope == "unclassified":
        return [r for r in store.records.values() if r.is_unclassified()]
    if scope == "stale":
        return [r for r in store.records.values()
                if r.classifier_version != CLASSIFIER_VERSION]
    if scope == "all_known":  # every record (NOT the raw dictionary tail)
        return list(store.records.values())
    raise ValueError(f"Unknown classification scope: {scope}")
