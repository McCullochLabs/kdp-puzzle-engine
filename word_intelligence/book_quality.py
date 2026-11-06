"""Whole-book quality scoring (Word Intelligence 2.0, spec PART K/U).

Scores a fully built book - not individual words - so weak books are
caught before they become commercial products.  Metrics are honest about
what they can and cannot measure: every score carries its calculation
basis, and hard failures never hide behind soft warnings.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .anchors import compatibility_closure
from .normalization import clean_surface, split_tokens
from .quality import PuzzleWorthiness, assess_quality
from .records import TRUSTED, APPROVED


# A puzzle is "coherent" when its dominant cluster supplies at least this
# share of the words (mini-theme feel).
COHERENCE_DOMINANT_SHARE = 0.5


@dataclass
class BookQualityReport:
    topic_id: str
    puzzles: int = 0
    word_slots: int = 0
    unique_vocabulary: int = 0
    repeated_words: int = 0          # distinct words used more than once
    max_word_reuse: int = 0
    repetition_rate: float = 0.0     # reused slots / slots
    topic_purity: float = 0.0        # on-topic-or-compatible / graded words; see coverage
    reviewed_vocabulary: int = 0
    reviewed_coverage: float = 0.0
    unknown_words: list[str] = field(default_factory=list)
    unreviewed_words: list[str] = field(default_factory=list)
    evidence_status: str = 'insufficient evidence'
    off_topic_words: list[str] = field(default_factory=list)
    flagged_words: list[str] = field(default_factory=list)
    weak_review_words: int = 0
    subtopics_represented: list[str] = field(default_factory=list)
    cluster_balance: float = 0.0     # 1.0 = perfectly even cluster usage
    cluster_modelled: bool = False   # True only when the topic has real mini-themes
    coherence_grades: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    hard_failures: list[str] = field(default_factory=list)
    overall: str = "F"

    def to_dict(self) -> dict:
        return {
            "topic_id": self.topic_id,
            "puzzles": self.puzzles,
            "word_slots": self.word_slots,
            "unique_vocabulary": self.unique_vocabulary,
            "repeated_words": self.repeated_words,
            "max_word_reuse": self.max_word_reuse,
            "repetition_rate": self.repetition_rate,
            "topic_purity": self.topic_purity,
            "reviewed_vocabulary": self.reviewed_vocabulary,
            "reviewed_coverage": self.reviewed_coverage,
            "unknown_words": list(self.unknown_words),
            "unknown_word_count": len(self.unknown_words),
            "unreviewed_words": list(self.unreviewed_words),
            "unreviewed_word_count": len(self.unreviewed_words),
            "evidence_status": self.evidence_status,
            "off_topic_words": list(self.off_topic_words),
            "flagged_words": list(self.flagged_words),
            "weak_review_words": self.weak_review_words,
            "subtopics_represented": list(self.subtopics_represented),
            "cluster_balance": self.cluster_balance,
            "cluster_modelled": self.cluster_modelled,
            "coherence_grades": list(self.coherence_grades),
            "warnings": list(self.warnings),
            "hard_failures": list(self.hard_failures),
            "overall": self.overall,
        }


def _letter(fraction: float) -> str:
    if fraction >= 0.9:
        return "A"
    if fraction >= 0.75:
        return "B"
    if fraction >= 0.6:
        return "C"
    if fraction >= 0.4:
        return "D"
    return "F"


def _cluster_of(topic_id: str, word: str) -> str:
    """Use the same reviewed cluster mapping as the pool and production gate."""
    from .clusters import GENERAL_CLUSTER, assign_clusters
    norm = clean_surface(word)
    return assign_clusters(None, None, topic_id, [word]).get(norm, GENERAL_CLUSTER)


def score_book(store, taxonomy, topic_id: str, puzzles: list[list[str]],
               puzzle_clusters: list[str] | None = None,
               repetition_pressure: float | None = None) -> BookQualityReport:
    """Deterministic quality report for one proposed book."""
    resolved = taxonomy.resolve(topic_id) or topic_id
    report = BookQualityReport(topic_id=resolved)
    report.puzzles = len(puzzles)

    flat: list[str] = [clean_surface(w) for p in puzzles for w in p]
    report.word_slots = len(flat)
    if not flat:
        report.hard_failures.append("Book contains no puzzles")
        return report

    counts: dict[str, int] = {}
    for word in flat:
        counts[word] = counts.get(word, 0) + 1
    report.unique_vocabulary = len(counts)
    report.repeated_words = sum(1 for c in counts.values() if c > 1)
    report.max_word_reuse = max(counts.values())
    reused_slots = len(flat) - len(counts)
    if repetition_pressure is None:
        repetition_pressure = round(reused_slots / len(flat), 4)
    report.repetition_rate = repetition_pressure

    compatible = compatibility_closure(taxonomy, resolved)
    on_topic = off_topic = graded = weakish = 0
    for word in sorted(counts):
        record = store.get(word)
        if record is None:
            report.unknown_words.append(word)
            continue                      # unknown -> not graded here
        if record.safety_review or record.trademark_review:
            report.flagged_words.append(word)
            continue
        quality = assess_quality(record)
        if quality.worthiness == PuzzleWorthiness.REVIEW:
            weakish += 1
        links = {l.topic_id for l in record.topics if l.status in (TRUSTED,APPROVED)}
        if not links:
            report.unreviewed_words.append(word)
            continue
        graded += 1
        if resolved in links or (links & compatible):
            on_topic += 1
        else:
            off_topic += 1
            if len(report.off_topic_words) < 25:
                report.off_topic_words.append(word)
    if graded:
        report.topic_purity = round(on_topic / graded, 4)
    report.reviewed_vocabulary = graded
    report.reviewed_coverage = round(graded / len(counts), 4)
    report.evidence_status = 'sufficient coverage' if report.reviewed_coverage >= .95 else 'insufficient evidence'
    if report.reviewed_coverage < .95:
        report.warnings.append(f'Insufficient evidence: {report.reviewed_coverage:.0%} vocabulary reviewed; {len(report.unknown_words)} unknown and {len(report.unreviewed_words)} unreviewed word(s).')
    report.weak_review_words = weakish

    # Subtopic spread + balance (spec PART S).
    if puzzle_clusters:
        from .clusters import SEED_CLUSTERS
        report.cluster_modelled = bool(SEED_CLUSTERS.get(resolved))
        report.subtopics_represented = sorted(set(puzzle_clusters))
        usage: dict[str, int] = {}
        for label in puzzle_clusters:
            usage[label] = usage.get(label, 0) + 1
        total = sum(usage.values()) or 1
        even = 1.0 / len(usage) if usage else 0.0
        deviation = sum(abs(n / total - even) for n in usage.values()) / 2
        report.cluster_balance = round(max(0.0, 1.0 - deviation), 3)

    # Per-puzzle coherence from dominant-cluster share (spec PART I/AR).
    if report.cluster_modelled and puzzle_clusters and len(puzzle_clusters) == len(puzzles):
        for words, label in zip(puzzles, puzzle_clusters):
            if not words:
                report.coherence_grades.append("F")
                continue
            share = sum(1 for w in words
                        if _cluster_of(resolved, w) == label)
            report.coherence_grades.append(_letter(share / len(words)))

    # ---- Warnings vs hard failures -------------------------------------
    if off_topic:
        report.hard_failures.append(
            f"{off_topic} word(s) point outside the topic and its anchors")
    if report.flagged_words:
        report.hard_failures.append(
            f"{len(report.flagged_words)} trademark/safety-flagged word(s)")
    if report.repetition_rate > 0.25:
        report.warnings.append(
            f"Repetition rate {report.repetition_rate:.0%} exceeds 25%")
    if weakish > max(2, report.word_slots // 50):
        report.warnings.append(
            f"{weakish} review-tier word(s) need human eyes")
    if puzzle_clusters and len(report.subtopics_represented) < 2 \
            and report.puzzles >= 10:
        report.warnings.append("One mini-theme dominates the book")
    if not report.cluster_modelled and report.puzzles >= 10:
        report.warnings.append(
            "This topic does not yet have a reviewed mini-theme map; "
            "coherence cannot be certified")

    # A letter grade must never hide a safety failure.  Warnings remain
    # warnings here because a caller can choose a different commercial
    # policy, but every hard failure is an automatic F.
    if report.hard_failures:
        report.overall = "F"
        return report

    score = 1.0
    score -= 0.6 * min(1.0, len(report.hard_failures) / 2)
    score -= 0.15 * min(1.0, len(report.warnings) / 3)
    score -= (1.0 - report.topic_purity) * 0.8
    score -= report.repetition_rate * 0.3
    report.overall = _letter(max(0.0, min(1.0, score)))
    if report.evidence_status == 'insufficient evidence':
        report.overall = 'Unverified'
    return report
