"""Word quality scoring: puzzle-worthiness, roles, exclusivity.

Quality is independent of classification confidence: a word can be a
PERFECT gardening match yet unsuitable for children's puzzles, or a great
general word with weak topic ties.  Keeping the axes separate preserves
honest reporting (mission §13).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

VOWELS = frozenset("AEIOU")  # Y excluded: RHYTHMS-style words still flag

MIN_WORD_LEN = 3
MAX_WORD_LEN = 21          # matches the production word-search placement gate
BEST_MAX_LEN = 12          # comfortable for large-print grids

ZIPF_COMMON = 4.0
ZIPF_FAMILIAR = 3.2
ZIPF_MODERATE = 2.6
ZIPF_OBSCURE = 2.2


class PuzzleWorthiness(str, Enum):
    PREFERRED = "preferred"      # showcase vocabulary
    ACCEPTABLE = "acceptable"    # fine for general books
    SPECIALIZED = "specialized"  # enthusiasts will enjoy; flag for kids' books
    REVIEW = "review"            # human should decide
    EXCLUDE = "exclude"          # never place


@dataclass
class WordQualityScore:
    worthiness: PuzzleWorthiness
    familiarity: str             # common/familiar/moderate/rare/unknown
    reasons: list[str]

    def to_dict(self) -> dict:
        return {
            "worthiness": self.worthiness.value,
            "familiarity": self.familiarity,
            "reasons": list(self.reasons),
        }


def familiarity_tier(frequency) -> str:
    if frequency is None:
        return "unknown"
    if frequency >= ZIPF_COMMON:
        return "common"
    if frequency >= ZIPF_FAMILIAR:
        return "familiar"
    if frequency >= ZIPF_MODERATE:
        return "moderate"
    if frequency >= ZIPF_OBSCURE:
        return "rare"
    return "very_rare"


def assess_quality(record) -> WordQualityScore:
    """Rule-ordered assessment; first decisive rule wins."""
    reasons: list[str] = []
    tier = familiarity_tier(record.frequency)

    if record.safety_review:
        return WordQualityScore(PuzzleWorthiness.EXCLUDE,
                                tier, ["Carries an exclusion/safety flag"])
    if record.trademark_review:
        return WordQualityScore(PuzzleWorthiness.REVIEW,
                                tier, ["Trademark-review term"])

    n = len(record.normalized)
    if n < MIN_WORD_LEN or n > MAX_WORD_LEN:
        return WordQualityScore(
            PuzzleWorthiness.EXCLUDE, tier,
            [f"Length {n} outside printable range {MIN_WORD_LEN}-{MAX_WORD_LEN}"])
    if not set(record.normalized) & VOWELS and n > 4:
        reasons.append("No vowels - likely not pronounceable")
        return WordQualityScore(PuzzleWorthiness.REVIEW, tier, reasons)

    if n > BEST_MAX_LEN:
        reasons.append(f"Long ({n} letters) - large-print grids only")
        if tier in ("unknown", "very_rare"):
            return WordQualityScore(PuzzleWorthiness.REVIEW, tier, reasons)

    if tier == "very_rare":
        return WordQualityScore(PuzzleWorthiness.REVIEW, tier,
                                reasons + [f"Very uncommon (zipf {record.frequency:.1f})"])
    if tier == "rare":
        return WordQualityScore(PuzzleWorthiness.SPECIALIZED, tier,
                                reasons + [f"Uncommon (zipf {record.frequency:.1f})"])
    if tier == "unknown":
        # No frequency data: acceptable but not preferred until measured.
        reasons.append("No frequency data")
        return WordQualityScore(PuzzleWorthiness.ACCEPTABLE, tier, reasons)

    if tier == "moderate":
        reasons.append(f"Moderately common (zipf {record.frequency:.1f})")
        return WordQualityScore(PuzzleWorthiness.ACCEPTABLE, tier, reasons)

    reasons.append(f"Widely familiar (zipf {record.frequency:.1f})")
    worthiness = (PuzzleWorthiness.PREFERRED
                  if MIN_WORD_LEN + 1 <= n <= BEST_MAX_LEN
                  else PuzzleWorthiness.ACCEPTABLE)
    return WordQualityScore(worthiness, tier, reasons)


# ---------------------------------------------------------------------------
# Roles within a topic pool
# ---------------------------------------------------------------------------

def role_for(worthiness: PuzzleWorthiness, confidence: float, is_trusted: bool) -> str:
    """ANCHOR/SUPPORT/SPECIALTY role inside a topic's word pool."""
    if is_trusted and worthiness == PuzzleWorthiness.PREFERRED:
        return "anchor"
    if worthiness == PuzzleWorthiness.SPECIALIZED:
        return "specialty"
    if worthiness in (PuzzleWorthiness.PREFERRED, PuzzleWorthiness.ACCEPTABLE):
        return "support" if confidence < 95 else "anchor"
    return "support"


def exclusivity_score(record, topic_id: str) -> float:
    """How loyal this word is to one topic (1.0 = appears nowhere else).

    Exclusive words are valuable: they make puzzles feel tightly on-topic.
    """
    links = [l for l in record.topics if l.status in ("trusted", "approved", "proposed")]
    if not links:
        return 0.0
    total = sum(l.confidence for l in links) or 1.0
    own = next((l.confidence for l in links if l.topic_id == topic_id), 0.0)
    return round(own / total, 3)
