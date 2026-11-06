"""Deterministic word-pool builder for puzzle generation.

Implements the mission's selection gate (§55-58): eligible words must be
topic-eligible AND quality-screened; each puzzle gets an anchor/support/
specialty mix; repetition policy is honoured exactly or raises - words are
never silently reused or dropped.

The builder NEVER invents vocabulary: if the pool cannot satisfy the
request it returns the shortfall with actionable detail.

Word Intelligence 2.0 additions (spec PART H/I/J):

*   STRICTNESS - ``strict`` / ``balanced`` / ``broad`` controls how wide the
    quality/familiarity net is cast.  It NEVER widens topical scope: a broad
    BBQ book still contains only BBQ vocabulary.
*   CLUSTER COHERENCE - puzzles draw primarily from one concept cluster
    (mini-theme) at a time, rotating across clusters so the BOOK spreads
    over the topic while each PUZZLE stays internally coherent.
*   DIVERSITY - usage counts, configurable controlled reuse and explicit
    repetition-pressure reporting instead of silent recycling.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from .analysis import estimate_capacity, words_for_topic
from .clusters import GENERAL_CLUSTER, assign_clusters
from .quality import PuzzleWorthiness, assess_quality, familiarity_tier


DIFFICULTY_MIN_ZIPF = {
    "easy": 3.2,       # very familiar words only
    "medium": 2.6,     # standard screen (matches existing audit rules)
    "hard": 2.2,       # enthusiasts' vocabulary allowed
}
DEFAULT_DIFFICULTY = "medium"

MAX_SPECIALTY_SHARE = 0.2   # specialty words per puzzle
MIN_ANCHORS_PER_PUZZLE = 1
MAX_ANCHOR_TARGET = 4

# Strictness -> minimum confidence band of links eligible for the pool.
# Topical scope never changes with strictness; only how proven a link must
# be and how familiar the vocabulary needs to be.
STRICTNESS_MIN_BAND = {
    "strict": "high",      # trusted/high-confidence anchors only
    "balanced": "medium",  # default commercial behaviour
    "broad": "low",        # wider related vocabulary, still screened
}
STRICTNESS_MIN_ZIPF_BONUS = {
    "strict": 0.4,         # demand slightly more familiar words too
    "balanced": 0.0,
    "broad": -0.3,         # allow deeper specialty cuts, still >= floor
}


@dataclass
class PoolRequest:
    topic_id: str
    puzzle_count: int
    words_per_puzzle: int
    difficulty: str = DEFAULT_DIFFICULTY
    subtopics: list[str] | None = None      # canonical subtopic ids to balance
    series_context: list[str] | None = None # words already used by sibling books
    seed: int | None = None
    strictness: str = "balanced"            # strict | balanced | broad
    max_word_reuse: int = 0                 # 0 = unique-only (previous behaviour)
    cluster_aware: bool = True              # mini-theme assembly


@dataclass
class PoolResult:
    puzzles: list[list[str]] = field(default_factory=list)
    unused_pool: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    shortfall: int = 0
    capacity: dict = field(default_factory=dict)
    puzzle_clusters: list[str] = field(default_factory=list)
    reuse_counts: dict[str, int] = field(default_factory=dict)
    repetition_pressure: float = 0.0   # reused slots / total slots

    def to_dict(self) -> dict:
        return {
            "puzzles": [list(p) for p in self.puzzles],
            "unused_pool": list(self.unused_pool),
            "warnings": list(self.warnings),
            "shortfall": self.shortfall,
            "capacity": dict(self.capacity),
            "puzzle_clusters": list(self.puzzle_clusters),
            "reuse_counts": dict(self.reuse_counts),
            "repetition_pressure": self.repetition_pressure,
        }


def _difficulty_ok(record, difficulty: str,
                   strictness: str = "balanced") -> tuple[bool, str]:
    min_zipf = DIFFICULTY_MIN_ZIPF.get(difficulty, DIFFICULTY_MIN_ZIPF["medium"])
    min_zipf += STRICTNESS_MIN_ZIPF_BONUS.get(strictness, 0.0)
    if record.safety_review:
        return False, "safety"
    quality = assess_quality(record)
    if quality.worthiness in (PuzzleWorthiness.EXCLUDE,):
        return False, "quality exclude"
    freq = record.frequency
    if freq is not None and freq < min_zipf:
        return False, f"zipf {freq:.1f} below {difficulty} floor {min_zipf:.1f}"
    if quality.worthiness == PuzzleWorthiness.REVIEW:
        return False, "needs review"
    if quality.worthiness == PuzzleWorthiness.SPECIALIZED and difficulty == "easy":
        return False, "specialized word in easy book"
    return True, ""


def collect_eligible_words(store, taxonomy, request: PoolRequest,
                           min_band: str | None = None) -> dict[str, list[str]]:
    """Eligible pool keyed by role: anchor / support / specialty.

    ``min_band`` defaults to the strictness-derived band so callers get
    consistent behaviour without repeating the mapping themselves.
    """
    from .quality import role_for
    from .records import APPROVED, PROPOSED, TRUSTED, band_of

    if min_band is None:
        min_band = STRICTNESS_MIN_BAND.get(request.strictness, "medium")
    roles: dict[str, list[str]] = {"anchor": [], "support": [], "specialty": []}
    used_elsewhere = set(request.series_context or [])
    for norm in words_for_topic(store, request.topic_id, min_band=min_band):
        if norm in used_elsewhere:
            continue
        record = store.get(norm)
        ok, _reason = _difficulty_ok(record, request.difficulty,
                                     request.strictness)
        if not ok:
            continue
        link = record.link_for(request.topic_id)
        is_trusted = bool(link and link.status in (TRUSTED, APPROVED))
        role = role_for(assess_quality(record).worthiness,
                        link.confidence if link else 0.0, is_trusted)
        roles[role].append(norm)
    return roles


def _cluster_rotation(clusters: dict[str, list[str]], puzzle_count: int,
                      rng: random.Random) -> list[str]:
    """Deterministic cluster order: biggest first, round-robin repeats.

    Rotating spreads the BOOK across the topic's mini-themes while each
    individual puzzle stays inside one of them (spec PART I vs PART S).
    """
    order = sorted((c for c in clusters
                    if c != GENERAL_CLUSTER and clusters[c]),
                   key=lambda c: (-len(clusters[c]), c))
    if clusters.get(GENERAL_CLUSTER):
        order.append(GENERAL_CLUSTER)
    if not order:
        return [GENERAL_CLUSTER] * max(puzzle_count, 1)
    return [order[i % len(order)] for i in range(puzzle_count)]


def build_word_pool(store, taxonomy, request: PoolRequest,
                    min_band: str | None = None) -> PoolResult:
    rng = random.Random(request.seed)
    needed = request.puzzle_count * request.words_per_puzzle
    result = PoolResult()

    roles = collect_eligible_words(store, taxonomy, request, min_band)
    all_eligible = sorted(set().union(*roles.values()))
    result.capacity = estimate_capacity(len(all_eligible), request.words_per_puzzle)

    # Cluster map drives mini-theme coherence (spec PART I).  Cheap even
    # for large pools; skipped entirely when the caller disables it.
    word_clusters: dict[str, str] = {}
    if request.cluster_aware:
        word_clusters = assign_clusters(taxonomy=taxonomy, store=store,
                                        topic_id=request.topic_id,
                                        words=all_eligible)
    clusters: dict[str, list[str]] = {}
    for norm in all_eligible:
        clusters.setdefault(word_clusters.get(norm, GENERAL_CLUSTER),
                            []).append(norm)
    rotation = (_cluster_rotation(clusters, request.puzzle_count, rng)
                if request.cluster_aware else
                [GENERAL_CLUSTER] * max(request.puzzle_count, 1))

    for role in ("anchor", "support", "specialty"):
        roles[role] = sorted(set(roles[role]) - set(request.series_context or []))
        rng.shuffle(roles[role])

    total_available = sum(len(v) for v in roles.values())
    max_reuse = max(0, int(request.max_word_reuse))
    if total_available < needed and max_reuse == 0:
        result.shortfall = needed - total_available
        result.warnings.append(
            f"Pool short by {result.shortfall} eligible words "
            f"(have {total_available}, need {needed}); "
            f"classify more vocabulary or relax filters")
        return result

    anchors = roles["anchor"]
    supports = roles["support"]
    specialties = roles["specialty"]
    usage: dict[str, int] = {n: 0 for n in all_eligible}

    ranked = list(all_eligible)
    rng.shuffle(ranked)
    selection_rank = {word: index for index, word in enumerate(ranked)}

    def take(pool: list[str], count: int, prefer: set[str], strict: bool = False) -> list[str]:
        """Pop up to ``count`` words honouring the reuse cap.

        Words inside ``prefer`` (this puzzle's primary cluster) are drawn
        first; among equals the least-used word wins so vocabulary spreads
        across the book before anything repeats.
        """
        taken: list[str] = []
        taken_set: set[str] = set()
        while len(taken) < count and pool:
            # Soft mini-theme preference: use primary-cluster words when any
            # are still available under the caps, otherwise fall back to the
            # wider pool so a small cluster can never stall a puzzle.
            usable = [w for w in pool
                      if usage[w] <= max_reuse and w not in taken_set]
            preferred = [w for w in usable if w in prefer]
            if preferred or strict:
                usable = preferred
            if not usable:
                break
            pick = min(usable, key=lambda w: (usage[w], selection_rank[w]))
            if max_reuse == 0:
                # Unique-only mode keeps the historic behaviour: a chosen
                # word leaves the candidate pool entirely.
                pool.remove(pick)
            # Controlled-reuse mode keeps the word available across puzzles
            # until its cap (usage[w] <= max_reuse) is exceeded; the
            # least-used-first key guarantees progress, and taken_set keeps
            # a single puzzle duplicate-free.
            taken.append(pick)
            taken_set.add(pick)
        return taken

    anchor_target_by_puzzle = min(
        MAX_ANCHOR_TARGET,
        max(MIN_ANCHORS_PER_PUZZLE, request.words_per_puzzle // 6))
    specialty_cap = int(request.words_per_puzzle * MAX_SPECIALTY_SHARE)

    for index in range(request.puzzle_count):
        primary = rotation[index]
        # Do not scatter the last few words of tiny mini-themes through a
        # full puzzle when another on-topic cluster can fill it completely.
        remaining_clusters = {}
        for word, cluster in word_clusters.items():
            if usage[word] <= max_reuse:
                remaining_clusters[cluster] = remaining_clusters.get(cluster, 0) + 1
        complete = {cluster for cluster, size in remaining_clusters.items()
                    if size >= request.words_per_puzzle}
        strict_primary = bool(request.cluster_aware and complete)
        if strict_primary and primary not in complete:
            primary = GENERAL_CLUSTER if GENERAL_CLUSTER in complete else sorted(complete, key=lambda cluster: (-remaining_clusters[cluster], cluster))[0]
        puzzle: list[str] = []

        def draw(pool: list[str], count: int) -> None:
            if not pool:
                return
            prefer = {w for w in pool
                      if word_clusters.get(w, GENERAL_CLUSTER) == primary}
            puzzle.extend(take(pool, count, prefer, strict=strict_primary))

        draw(anchors, anchor_target_by_puzzle)
        draw(specialties, min(specialty_cap, len(specialties)))
        remaining = request.words_per_puzzle - len(puzzle)
        draw(supports, remaining)
        if len(puzzle) < request.words_per_puzzle:
            # Top up across every role, still favouring the mini-theme.
            for backup in (supports, anchors, specialties):
                draw(backup, request.words_per_puzzle - len(puzzle))
                if len(puzzle) >= request.words_per_puzzle:
                    break
        if len(puzzle) < request.words_per_puzzle:
            break  # exhausted mid-run; report shortfall below
        for word in puzzle:
            usage[word] = usage.get(word, 0) + 1
        # Candidate storage is intentionally sorted for stable audits, but the
        # reader-facing word list must not look like a dictionary page. Mix
        # each completed puzzle with the request's seeded RNG so reruns remain
        # reproducible without returning A-to-Z lists.
        rng.shuffle(puzzle)
        result.puzzles.append(list(puzzle))
        # A narrow title is allowed only when every word actually belongs to
        # that mini-theme.  Soft-preference top-ups make a good mixed puzzle,
        # but must receive the honest general-topic label instead.
        strict_cluster = primary if primary != GENERAL_CLUSTER and all(
            word_clusters.get(word, GENERAL_CLUSTER) == primary for word in puzzle
        ) else GENERAL_CLUSTER
        result.puzzle_clusters.append(strict_cluster)

    placed = sum(len(p) for p in result.puzzles)
    reused_slots = sum(count - 1 for count in usage.values() if count > 1)
    result.reuse_counts = {w: c for w, c in sorted(usage.items()) if c > 1}
    if placed:
        result.repetition_pressure = round(reused_slots / placed, 4)
    if placed < needed:
        result.shortfall = needed - placed
        result.warnings.append(
            f"Built {len(result.puzzles)} of {request.puzzle_count} puzzles "
            f"before exhausting the pool")
    if reused_slots:
        result.warnings.append(
            f"Controlled reuse applied: {reused_slots} repeated slot(s) "
            f"(max_word_reuse={max_reuse}); topic capacity below request")

    leftovers: set[str] = set()
    for role in ("anchor", "support", "specialty"):
        leftovers |= set(roles[role])
    consumed = {w for w, c in usage.items() if c}
    leftovers -= consumed
    result.unused_pool = sorted(leftovers)
    return result
