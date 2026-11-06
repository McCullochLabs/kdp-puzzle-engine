"""Tests for quality scoring and the ambiguity registry."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from word_intelligence.ambiguity import (
    SEED_AMBIGUOUS,
    AmbiguityRegistry,
    ambiguity_guard,
    scan_for_ambiguity,
)
from word_intelligence.classifier import Classifier
from word_intelligence.quality import (
    PuzzleWorthiness,
    assess_quality,
    exclusivity_score,
    familiarity_tier,
    role_for,
)
from word_intelligence.records import PROPOSED, TRUSTED, TopicLink, WordRecord
from word_intelligence.store import make_test_store
from word_intelligence.taxonomy import TopicTaxonomy


def _rec(word, freq=None, **kw):
    return WordRecord(normalized=word, display=word.title(), frequency=freq, **kw)


# ---------------------------------------------------------------------------
# quality
# ---------------------------------------------------------------------------

def test_familiarity_tiers():
    assert familiarity_tier(None) == "unknown"
    assert familiarity_tier(4.5) == "common"
    assert familiarity_tier(3.3) == "familiar"
    assert familiarity_tier(2.7) == "moderate"
    assert familiarity_tier(2.3) == "rare"
    assert familiarity_tier(1.5) == "very_rare"


def test_preferred_word():
    result = assess_quality(_rec("SUNFLOWER", 4.6))
    assert result.worthiness == PuzzleWorthiness.PREFERRED
    assert result.familiarity == "common"
    assert result.to_dict()["worthiness"] == "preferred"


def test_safety_flag_excludes_before_anything_else():
    result = assess_quality(_rec("CASINO", 4.0, safety_review=True))
    assert result.worthiness == PuzzleWorthiness.EXCLUDE


def test_trademark_terms_require_review():
    result = assess_quality(_rec("DISNEY", 4.9, trademark_review=True))
    assert result.worthiness == PuzzleWorthiness.REVIEW


def test_length_bounds_exclude():
    assert assess_quality(_rec("AB", 4.0)).worthiness == PuzzleWorthiness.EXCLUDE
    long_word = "A" * 22
    assert assess_quality(_rec(long_word, 4.0)).worthiness == PuzzleWorthiness.EXCLUDE


def test_vowelless_words_review():
    assert assess_quality(_rec("RHYTHMS", 3.0)).worthiness == PuzzleWorthiness.REVIEW


def test_rare_words_specialized_or_review():
    assert assess_quality(_rec("OBFUSCATE", 2.4)).worthiness == PuzzleWorthiness.SPECIALIZED
    assert assess_quality(_rec("QUAZGIMBLE", 1.8)).worthiness == PuzzleWorthiness.REVIEW


def test_unknown_frequency_is_acceptable_not_preferred():
    assert assess_quality(_rec("MYSTERYWORD")).worthiness == PuzzleWorthiness.ACCEPTABLE


def test_long_common_word_downgraded_to_acceptable():
    result = assess_quality(_rec("INTERNATIONALIZATION"[:18], 4.4))
    assert result.worthiness == PuzzleWorthiness.ACCEPTABLE


def test_roles_follow_strength():
    assert role_for(PuzzleWorthiness.PREFERRED, 100, True) == "anchor"
    assert role_for(PuzzleWorthiness.PREFERRED, 96, False) == "anchor"
    assert role_for(PuzzleWorthiness.PREFERRED, 90, False) == "support"
    assert role_for(PuzzleWorthiness.SPECIALIZED, 60, False) == "specialty"


def test_exclusivity_concentrates_on_single_topic():
    rec = _rec("TROWEL")
    rec.topics = [TopicLink("gardening", TRUSTED, 100)]
    assert exclusivity_score(rec, "gardening") == 1.0
    rec.topics.append(TopicLink("tools", PROPOSED, 100))
    assert exclusivity_score(rec, "gardening") == pytest.approx(0.5)
    assert exclusivity_score(rec, "nowhere") == 0.0
    empty = _rec("ORPHAN")
    assert exclusivity_score(empty, "gardening") == 0.0


# ---------------------------------------------------------------------------
# ambiguity registry
# ---------------------------------------------------------------------------

def test_registry_seeded_with_known_multi_sense_words():
    registry = AmbiguityRegistry.seeded()
    assert registry.is_ambiguous("BASS")
    assert not registry.is_ambiguous("TROWEL")
    assert set(SEED_AMBIGUOUS) <= set(registry.entries)


def test_register_and_resolve_round_trip(tmp_path):
    registry = AmbiguityRegistry()
    registry.register("CRANE", ["birds", "machinery"])
    assert registry.is_ambiguous("CRANE")
    registry.resolve("CRANE", "birds", note="decided by human")
    assert not registry.is_ambiguous("CRANE")
    path = registry.save(tmp_path)
    loaded = AmbiguityRegistry.load(tmp_path)
    assert path.exists()
    assert loaded.entries["CRANE"]["resolved_to"] == "birds"
    loaded.unresolve("CRANE")
    assert loaded.is_ambiguous("CRANE")


def test_load_missing_dir_returns_seeded(tmp_path):
    registry = AmbiguityRegistry.load(tmp_path / "missing")
    assert registry.is_ambiguous("BASS")


def _mini_world():
    bank = {
        "topics": {
            "Freshwater Fish": ["BASS", "TROUT"],
            "Music Instruments": ["GUITAR", "DRUMS"],
            "Gardening": ["TROWEL"],
        },
        "words": [],
    }
    taxonomy = TopicTaxonomy.from_master_bank(bank)
    store = make_test_store(bank["topics"])
    return store, taxonomy


def test_scan_trusted_multifamily_is_curation_not_ambiguity():
    store, taxonomy = _mini_world()
    registry = AmbiguityRegistry()
    # BASS trusted in two unrelated families = deliberate curation; only
    # conflicting PROPOSALS are auto-flagged.
    store.get("BASS").topics.append(TopicLink("music_instruments", TRUSTED, 100))
    families = {c: t.family for c, t in taxonomy.topics.items()}
    families.update({"freshwater_fish": "Animals & Nature",
                     "music_instruments": "Entertainment & Hobbies"})
    assert scan_for_ambiguity(store, families, registry) == []

    # Two strong PROPOSALS in unrelated families DO flag.
    record = WordRecord(normalized="BOW", display="Bow")
    record.topics += [TopicLink("freshwater_fish", PROPOSED, 92),
                      TopicLink("music_instruments", PROPOSED, 88)]
    store.records["BOW"] = record
    detected = scan_for_ambiguity(store, families, registry)
    assert detected == ["BOW"]
    assert registry.is_ambiguous("BOW")


def test_scan_ignores_cross_cutting_grab_bag_family():
    store, taxonomy = _mini_world()
    registry = AmbiguityRegistry()
    store.get("BASS").topics.append(TopicLink("music_instruments", TRUSTED, 100))
    families = {"freshwater_fish": "General & Flexible",   # cross-cutting
                "music_instruments": "Entertainment & Hobbies"}
    detected = scan_for_ambiguity(store, families, registry)
    assert detected == []          # grab-bag membership is not a sense conflict


def test_scan_ignores_resolved_and_single_family_words():
    store, taxonomy = _mini_world()
    registry = AmbiguityRegistry()
    registry.resolve("bass", "freshwater_fish")
    store.get("BASS").topics.append(TopicLink("music_instruments", TRUSTED, 100))
    detected = scan_for_ambiguity(
        store, {c: t.family for c, t in taxonomy.topics.items()}, registry)
    assert detected == []


def test_ambiguity_guard_caps_unresolved_scores():
    store, taxonomy = _mini_world()
    registry = AmbiguityRegistry.seeded()   # BASS unresolved
    record = store.get("BASS")
    families = {c: t.family for c, t in taxonomy.topics.items()}
    strong = [TopicLink("freshwater_fish", PROPOSED, 92)]
    weak = [TopicLink("freshwater_fish", PROPOSED, 50)]

    assert ambiguity_guard(record, registry, families, strong) < 1.0
    assert ambiguity_guard(record, registry, families, weak) == 0.8

    registry.resolve("BASS", "freshwater_fish")
    assert ambiguity_guard(record, registry, families, strong) == 1.0
    assert ambiguity_guard(record, registry, families, weak) == 1.0


def test_classifier_damps_registered_ambiguous_word():
    store, taxonomy = _mini_world()
    clf = Classifier(store, taxonomy, AmbiguityRegistry.seeded())
    record = WordRecord(normalized="BASS", display="Bass", frequency=3.5)
    links = clf.score_word(record)
    fish = next(l for l in links if l.topic_id == "freshwater_fish")
    # Exact entry (92) + familiar (6) would be ~98; the unresolved-sense
    # guard must keep it out of auto-link range.
    assert fish.confidence < 95
    assert any(e.signal == "ambiguity_warning" for e in fish.evidence)

    clf.ambiguity_registry.resolve("BASS", "freshwater_fish")
    fish2 = next(l for l in clf.score_word(record) if l.topic_id == "freshwater_fish")
    assert fish2.confidence >= 95   # resolved sense scores normally
