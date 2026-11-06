"""One truthful production decision shared by builders and publishing tools.

This module deliberately evaluates the *actual words selected for a book*.
It does not pad a short subject with unrelated dictionary words or convert a
warning into a green light merely because the cover and PDF can be created.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .book_quality import BookQualityReport, score_book
from .clusters import GENERAL_CLUSTER, SEED_CLUSTERS, assign_clusters
from .normalization import clean_surface, split_tokens


@dataclass
class ProductionTruth:
    ready: bool
    status: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    recommended_puzzles: int = 0
    recommended_words_per_puzzle: int = 0
    quality: BookQualityReport | None = None

    def to_dict(self) -> dict:
        return {
            "ready": self.ready, "status": self.status,
            "errors": list(self.errors), "warnings": list(self.warnings),
            "notes": list(self.notes),
            "recommended_puzzles": self.recommended_puzzles,
            "recommended_words_per_puzzle": self.recommended_words_per_puzzle,
            "quality": self.quality.to_dict() if self.quality else None,
        }


def recommended_format(unique_words: int) -> tuple[int, int]:
    """Return the largest repeat-free standard format the pool can support."""
    for puzzles, per_puzzle in ((100, 12), (60, 12), (48, 12)):
        if unique_words >= puzzles * per_puzzle:
            return puzzles, per_puzzle
    return max(0, unique_words // 12), 12


def _dominant_clusters(store, taxonomy, topic_id: str,
                       puzzles: list[list[str]]) -> list[str]:
    labels: list[str] = []
    for puzzle in puzzles:
        assigned = assign_clusters(store, taxonomy, topic_id, puzzle)
        counts: dict[str, int] = {}
        for word in puzzle:
            label = assigned.get(clean_surface(word), GENERAL_CLUSTER)
            counts[label] = counts.get(label, 0) + 1
        labels.append(sorted(counts, key=lambda item: (-counts[item], item))[0]
                      if counts else GENERAL_CLUSTER)
    return labels


def evaluate_book(store, taxonomy, topic_id: str, puzzles: list[list[str]],
                  *, require_no_repeats: bool = True,
                  required_puzzles: int | None = None,
                  min_words_per_puzzle: int = 12,
                  puzzle_names: list[str] | None = None) -> ProductionTruth:
    """Evaluate a proposed book without writing any project data."""
    errors: list[str] = []
    warnings: list[str] = []
    notes: list[str] = []
    if required_puzzles is not None and len(puzzles) != required_puzzles:
        errors.append(f"Book has {len(puzzles)} of the requested {required_puzzles} puzzles.")
    if not puzzles:
        return ProductionTruth(False, "Blocked — no puzzles", ["Book contains no puzzles."])
    bad_sizes = [index + 1 for index, words in enumerate(puzzles)
                 if len(words) < min_words_per_puzzle]
    if bad_sizes:
        errors.append("Puzzle(s) " + ", ".join(map(str, bad_sizes[:8])) +
                      f" contain fewer than {min_words_per_puzzle} words.")
    flat = [clean_surface(word) for puzzle in puzzles for word in puzzle
            if clean_surface(word)]
    unique_words = len(set(flat))
    recommended_puzzles, recommended_words = recommended_format(unique_words)
    if require_no_repeats and unique_words != len(flat):
        errors.append("This book repeats puzzle words. The no-repeat promise cannot be used until every repeated word is replaced.")

    resolved = taxonomy.resolve(topic_id)
    if not resolved:
        warnings.append("This book has no recognized Master Library topic yet; its topic coherence cannot be certified.")
        return ProductionTruth(not errors, "Ready with topic review" if not errors else "Blocked",
                               errors, warnings, notes, recommended_puzzles, recommended_words)

    clusters = _dominant_clusters(store, taxonomy, resolved, puzzles)
    quality = score_book(store, taxonomy, resolved, puzzles, clusters)
    if quality.hard_failures:
        errors.extend(quality.hard_failures)
    if quality.repetition_rate > 0 and require_no_repeats:
        errors.append("Word reuse was detected by the book-quality check.")
    if quality.cluster_modelled and quality.coherence_grades:
        poor = sum(grade in {"D", "F"} for grade in quality.coherence_grades)
        if poor:
            errors.append(f"{poor} puzzle(s) do not meet the topic-coherence standard.")
    warnings.extend(quality.warnings)
    if quality.evidence_status == 'insufficient evidence':
        notes.append('Vocabulary coverage is incomplete; the quality grade is Unverified, not a topic certification.')
    if quality.cluster_modelled:
        notes.append("Topic coherence was checked against reviewed mini-themes.")
        # A saved puzzle label is buyer-facing. A generic 'Puzzle 1' is fine,
        # but a specific, unrelated label makes an otherwise good collection
        # feel like a copied template. Surface it for review without changing
        # the user's saved theme automatically.
        seeds = {token for cluster in SEED_CLUSTERS.get(resolved, {}).values()
                 for word in cluster for token in split_tokens(clean_surface(word))}
        odd_labels = []
        for index, name in enumerate(puzzle_names or [], 1):
            topic_tokens = set(split_tokens(clean_surface(taxonomy.topics[resolved].display_name)))
            tokens = set(split_tokens(clean_surface(name))) - {"PUZZLE", "WORD", "SEARCH"} - topic_tokens
            if tokens and not tokens <= {str(index)} and not (tokens & seeds):
                odd_labels.append(str(name))
        if odd_labels:
            warnings.append(
                f"{len(odd_labels)} puzzle label(s) do not clearly match this topic "
                f"(for example, '{odd_labels[0]}'). Rename them or use simple Puzzle numbers.")
    else:
        warnings.append("This topic needs a reviewed mini-theme map before the app can certify puzzle coherence.")
    status = ("Blocked" if errors else
              "Ready with review" if warnings else "Ready for package")
    return ProductionTruth(not errors, status, list(dict.fromkeys(errors)),
                           list(dict.fromkeys(warnings)), notes,
                           recommended_puzzles, recommended_words, quality)
