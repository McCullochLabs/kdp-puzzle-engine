"""Word Intelligence 2.0: multi-anchor compatibility, clusters, coherence.

Covers the spec's PART B/C/D (multi-anchor), PART H (strictness),
PART I/J (coherence + diversity) and PART K (book quality scoring) with
deterministic fixtures - no production data is touched.
"""

from __future__ import annotations

import pytest

from word_intelligence.anchors import (
    CURATED_ANCHOR_LINKS,
    compatibility_closure,
    family_sibling_ids,
)
from word_intelligence.clusters import GENERAL_CLUSTER, assign_clusters
from word_intelligence.pool_builder import PoolRequest, build_word_pool
from word_intelligence.book_quality import score_book
from word_intelligence.production_gate import evaluate_book, recommended_format


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def nature_world():
    """Mini taxonomy/store: gardening + baking + ocean in two families."""
    from word_intelligence.store import make_test_store
    from word_intelligence.taxonomy import TopicTaxonomy

    bank = {"topics": {
        "Gardening": ["TROWEL", "COMPOST", "MULCH", "SEEDS", "SPADE",
                      "WEEDER", "PRUNER"],
        "Baking": ["OVEN", "FLOUR", "KNEAD"],
        "Ocean Life": ["WHALE", "CORAL", "TIDE"],
    }}
    taxonomy = TopicTaxonomy.from_master_bank(bank)
    store = make_test_store(bank["topics"])
    return store, taxonomy


# ---------------------------------------------------------------------------
# Multi-anchor closure (PART B/C/D)
# ---------------------------------------------------------------------------

def test_compatibility_closure_is_symmetric(nature_world):
    _store, taxonomy = nature_world
    for left, rights in CURATED_ANCHOR_LINKS.items():
        for right in rights:
            if left in taxonomy.topics and right in taxonomy.topics:
                assert right in compatibility_closure(taxonomy, left)


def test_unknown_topic_yields_empty_closure(nature_world):
    _store, taxonomy = nature_world
    assert compatibility_closure(taxonomy, "totally_unknown") == set()


def test_family_siblings_exclude_self(nature_world):
    _store, taxonomy = nature_world
    sibs = family_sibling_ids(taxonomy, "gardening")
    assert "gardening" not in sibs


def test_curated_links_resolve_against_real_library():
    """Every curated anchor id must exist in the real canonical taxonomy."""
    from word_intelligence.pipeline import load_taxonomy
    full = load_taxonomy(".")
    missing = sorted({b for bs in CURATED_ANCHOR_LINKS.values()
                      for b in bs if b not in full.topics} |
                     {a for a in CURATED_ANCHOR_LINKS if a not in full.topics})
    assert not missing, f"stale curated anchors: {missing}"


# ---------------------------------------------------------------------------
# Clusters (PART I)
# ---------------------------------------------------------------------------

def test_seed_words_land_in_their_cluster():
    mapping = assign_clusters(None, None, "gardening",
                              ["COMPOST", "TROWEL", "ZUCCHINI"])
    assert mapping["COMPOST"] == "soil_compost"
    assert mapping["TROWEL"] == "tools"


def test_unmatched_word_falls_back_to_general():
    mapping = assign_clusters(None, None, "gardening", ["QQQUUUVVV"])
    assert mapping["QQQUUUVVV"] == GENERAL_CLUSTER


# ---------------------------------------------------------------------------
# Strictness / coherence / diversity in the pool builder (PART H/I/J)
# ---------------------------------------------------------------------------

def test_strict_pool_is_subset_of_balanced_pool(nature_world):
    store, taxonomy = nature_world
    base = dict(topic_id="gardening", puzzle_count=1, words_per_puzzle=3,
                seed=5)
    strict = build_word_pool(store, taxonomy, PoolRequest(**base,
                                                         strictness="strict"))
    balanced = build_word_pool(store, taxonomy, PoolRequest(**base))
    assert set().union(*strict.puzzles) <= (
        set().union(*balanced.puzzles) | set(strict.unused_pool))


def test_cluster_aware_result_reports_mini_themes(nature_world):
    store, taxonomy = nature_world
    request = PoolRequest(topic_id="gardening", puzzle_count=2,
                          words_per_puzzle=4, seed=9)
    result = build_word_pool(store, taxonomy, request)
    assert len(result.puzzle_clusters) == len(result.puzzles)


def test_controlled_reuse_is_reported_never_silent(nature_world):
    store, taxonomy = nature_world
    request = PoolRequest(topic_id="gardening", puzzle_count=4,
                          words_per_puzzle=5, seed=3, max_word_reuse=2)
    result = build_word_pool(store, taxonomy, request)
    placed = sum(len(p) for p in result.puzzles)
    unique = len({w for p in result.puzzles for w in p})
    if placed > unique:                     # reuse actually happened
        assert result.repetition_pressure > 0
        assert any("reuse" in w.lower() or "repeated" in w.lower()
                   for w in result.warnings)


def test_no_reuse_request_keeps_disjoint_guarantee(nature_world):
    store, taxonomy = nature_world
    request = PoolRequest(topic_id="gardening", puzzle_count=2,
                          words_per_puzzle=6, seed=11)
    result = build_word_pool(store, taxonomy, request)
    flat = [w for p in result.puzzles for w in p]
    assert len(flat) == len(set(flat))


# ---------------------------------------------------------------------------
# Book quality scoring (PART K)
# ---------------------------------------------------------------------------

def test_clean_book_scores_high_and_has_no_hard_failures(nature_world):
    store, taxonomy = nature_world
    puzzles = [["TROWEL", "COMPOST"], ["MULCH", "SEEDS"]]
    report = score_book(store, taxonomy, "gardening", puzzles)
    assert report.topic_purity == 1.0
    assert not report.hard_failures
    assert report.overall in ("A", "B")


def test_contaminated_book_hard_fails(nature_world):
    store, taxonomy = nature_world
    puzzles = [["TROWEL", "WHALE"], ["CORAL", "SEEDS"]]   # ocean words
    report = score_book(store, taxonomy, "gardening", puzzles)
    assert report.hard_failures
    assert report.off_topic_words
    assert report.overall in ("C", "D", "F")


def test_production_truth_blocks_repeated_words(nature_world):
    store, taxonomy = nature_world
    truth = evaluate_book(store, taxonomy, "gardening",
                          [["TROWEL", "COMPOST"], ["TROWEL", "SEEDS"]],
                          min_words_per_puzzle=2)
    assert not truth.ready
    assert any("repeats" in item.lower() or "reuse" in item.lower()
               for item in truth.errors)


def test_recommended_format_never_promises_more_than_unique_pool():
    assert recommended_format(576) == (48, 12)
    assert recommended_format(575) == (47, 12)


def test_production_truth_flags_unrelated_buyer_facing_puzzle_label(nature_world):
    store, taxonomy = nature_world
    truth = evaluate_book(store, taxonomy, "gardening",
                          [["TROWEL", "COMPOST"], ["MULCH", "SEEDS"]],
                          min_words_per_puzzle=2,
                          puzzle_names=["Ocean Traditions", "Garden Tools"])
    assert any("label" in item.lower() for item in truth.warnings)
