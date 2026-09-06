"""Phase 2 capacity truth tests; no generators or production data are changed."""
from __future__ import annotations

import json
from pathlib import Path

from word_intelligence.capacity import (
    CapacityRequest, ContentCapacityEngine, REVIEW_LEGACY, REVIEW_STRICT,
)
from word_intelligence.cache_manifest import safe_rebuild_store
from word_intelligence.content_contracts import (
    ContentRecord, FormatRules, Provenance, QualityStatus, TopicReference,
    deterministic_content_id, normalized_value,
)
from word_intelligence.content_registry import ContentRegistry
from word_intelligence.qualification import ApprovalDecision
from word_intelligence.taxonomy import TopicTaxonomy


def _record(value, *, content_type="word", topic="gardening", editorial="approved",
            link_status="approved", factual="verified", source="curated", payload=None):
    return ContentRecord(
        id=deterministic_content_id(content_type, value, source_id=f"{source}:{value}"),
        type=content_type, display=value, normalized=normalized_value(value),
        topics=(TopicReference(topic, "primary", 100, link_status),),
        format_rules=FormatRules(), quality=QualityStatus(editorial, factual, False, False),
        provenance=Provenance(source, f"fixture:{value}"), payload=payload or {},
    )


def _engine(records, reservations=None):
    taxonomy = TopicTaxonomy.from_master_bank({"topics": {
        "Gardening": ["TROWEL"], "Garden Related": ["GREENHOUSE"], "Baking": ["OVEN"],
    }})
    garden = taxonomy.resolve("Gardening")
    related = taxonomy.resolve("Garden Related")
    taxonomy.topics[garden].related.append(related)
    registry = ContentRegistry()
    for record in records: registry.add(record)
    engine = ContentCapacityEngine(".", taxonomy, registry, cache_state={"state": "fresh"})
    engine.manifest = {"source_hashes": {"fixture": "yes"}}
    engine.source_revision = "fixture"
    engine.reservation_evidence = reservations or []
    return engine, garden, related


def test_strict_and_legacy_capacity_are_explicitly_different():
    record = _record("Trowel", editorial="legacy_unreviewed", link_status="legacy_unreviewed", source="legacy")
    engine, garden, _ = _engine([record])
    strict = engine.evaluate(CapacityRequest(garden, "word_search", 1, 1, REVIEW_STRICT))
    compatible = engine.evaluate(CapacityRequest(garden, "word_search", 1, 1, REVIEW_LEGACY))
    assert strict.verified_capacity == 0 and strict.status == "needs_topic_review"
    assert compatible.verified_capacity == 1 and compatible.status == "ready"


def test_explicit_human_overlay_counts_in_strict_capacity_and_changes_revision():
    record = _record("Trowel", editorial="legacy_unreviewed", link_status="legacy_unreviewed", source="legacy")
    engine, garden, _ = _engine([record])
    before = engine.source_revision
    engine.approval_decisions = {record.id: ApprovalDecision(record.id, garden, "approved")}
    # Recreate the engine with the explicit overlay to obtain its complete
    # source/approval fingerprint, exactly as project loading does.
    revised = ContentCapacityEngine(".", engine.taxonomy, engine.registry, cache_state={"state": "fresh"}, approval_decisions=engine.approval_decisions)
    revised.manifest = {"source_hashes": {"fixture": "yes"}}
    assert revised.evaluate(CapacityRequest(garden, "word_search", 1, 1)).verified_capacity == 1
    assert revised.source_revision != before


def test_word_search_filters_long_blank_and_duplicate_normalized_values():
    valid = _record("A" * 21)
    long = _record("B" * 22)
    punctuated = _record("Garden-Trowel")
    duplicate = _record("Garden Trowel", source="imported")
    engine, garden, _ = _engine([valid, long, punctuated, duplicate])
    result = engine.evaluate(CapacityRequest(garden, "word_search", 3, 1))
    assert result.verified_capacity == 2
    assert result.excluded_counts["word_search_too_long"] == 1
    assert result.duplicate_exclusions == 1


def test_rejected_or_unresolved_topic_records_do_not_count():
    rejected = _record("Trowel", editorial="rejected")
    unresolved = _record("Hoe", topic="unresolved_topic")
    engine, garden, _ = _engine([rejected, unresolved])
    result = engine.evaluate(CapacityRequest(garden, "word_search", 1, 1))
    assert result.verified_capacity == 0


def test_approved_related_topic_is_visible_only_when_requested():
    record = _record("Greenhouse", topic="garden_related")
    engine, garden, _ = _engine([record])
    plain = engine.evaluate(CapacityRequest(garden, "word_search", 1, 1))
    related = engine.evaluate(CapacityRequest(garden, "word_search", 1, 1, allow_related_topics=True))
    assert plain.verified_capacity == 0
    assert related.related_topic_count == 1 and related.verified_capacity == 1


def test_freshness_policy_uses_real_normalized_reservation_evidence():
    record = _record("Trowel")
    reservations = [{"words": {"TROWEL"}, "scope_key": "garden-series", "title": "Prior", "source": "fixture"}]
    engine, garden, _ = _engine([record], reservations)
    kept = engine.evaluate(CapacityRequest(garden, "word_search", 1, 1, freshness_policy="allow_all"))
    excluded = engine.evaluate(CapacityRequest(garden, "word_search", 1, 1, freshness_policy="exclude_prior_series_use", series_scope="garden-series"))
    assert kept.verified_capacity == 1
    assert excluded.verified_capacity == 0 and excluded.excluded_counts["prior_series_reserved"] == 1


def test_capacity_requirement_and_alternative_are_truthful():
    records = [_record(f"Word{index}") for index in range(5)]
    engine, garden, _ = _engine(records)
    result = engine.evaluate(CapacityRequest(garden, "word_search", 48, 12))
    assert result.required_count == 576 and result.status == "insufficient_verified_content"
    assert any("Expand reviewed" in item for item in result.alternatives)


def test_cryptogram_strict_excludes_mechanical_and_legacy_prompts():
    mechanical = _record("CURIOSITY MAKES MARS MORE INTERESTING TO EXPLORE", content_type="cryptogram_prompt", editorial="legacy_unreviewed", link_status="legacy_unreviewed", source="legacy")
    clear = _record("MARS IS OFTEN CALLED THE RED PLANET", content_type="cryptogram_prompt", editorial="legacy_unreviewed", link_status="legacy_unreviewed", source="legacy")
    engine, garden, _ = _engine([mechanical, clear])
    strict = engine.evaluate(CapacityRequest(garden, "cryptogram", 1, 1))
    compatible = engine.evaluate(CapacityRequest(garden, "cryptogram", 2, 1, REVIEW_LEGACY))
    assert strict.verified_capacity == 0
    assert compatible.verified_capacity == 2 and compatible.excluded_counts["mechanical_prompt"] == 1


def test_cryptogram_layout_and_duplicates_are_filtered():
    valid = _record("A CLEAR PROMPT", content_type="cryptogram_prompt")
    long = _record("A" * 111, content_type="cryptogram_prompt")
    duplicate = _record("A CLEAR PROMPT", content_type="cryptogram_prompt", source="imported")
    engine, garden, _ = _engine([valid, long, duplicate])
    result = engine.evaluate(CapacityRequest(garden, "cryptogram", 1, 1))
    assert result.verified_capacity == 1
    assert result.excluded_counts["cryptogram_layout_invalid"] == 1


def test_trivia_requires_complete_verified_linked_record():
    good = _record("Mars", content_type="trivia", payload={"question": "Which planet is red?", "answer": "Mars"})
    incomplete = _record("Venus", content_type="trivia", payload={"question": "Which planet is hot?"})
    old_fact = _record("Earth", content_type="trivia", factual="legacy_unreviewed", payload={"question": "Which planet is ours?", "answer": "Earth"})
    engine, garden, _ = _engine([good, incomplete, old_fact])
    strict = engine.evaluate(CapacityRequest(garden, "scramble_trivia", 1, 1))
    compatible = engine.evaluate(CapacityRequest(garden, "scramble_trivia", 2, 1, REVIEW_LEGACY))
    assert strict.verified_capacity == 1 and strict.excluded_counts["incomplete_trivia"] == 1
    assert compatible.verified_capacity == 2


def test_sudoku_reports_algorithmic_capacity_not_word_bank_capacity():
    engine, garden, _ = _engine([])
    result = engine.evaluate(CapacityRequest(garden, "sudoku", 60, 1))
    assert result.status == "ready" and result.verified_capacity == 60
    assert "algorithmic" in result.warnings[0].casefold()


def test_mixed_exposes_section_capacity_without_routing_or_generation():
    crypto = _record("A CLEAR PROMPT", content_type="cryptogram_prompt")
    trivia = _record("Mars", content_type="trivia", payload={"question": "Which planet is red?", "answer": "Mars"})
    engine, garden, _ = _engine([crypto, trivia])
    sections = engine.mixed_sections(garden, puzzle_count=3)
    assert set(sections) == {"sudoku", "cryptogram", "scramble_trivia"}
    assert sections["sudoku"].status == "ready"


def test_batch_uses_the_same_read_only_capacity_engine():
    engine, garden, _ = _engine([_record("Trowel")])
    results = engine.evaluate_batch([
        CapacityRequest(garden, "word_search", 1, 1),
        CapacityRequest(garden, "sudoku", 2, 1),
    ])
    assert [result.puzzle_type for result in results] == ["word_search", "sudoku"]
    assert [result.status for result in results] == ["ready", "ready"]


def test_safe_cache_rebuild_writes_manifest_and_preserves_prior_store(tmp_path):
    bank = tmp_path / "word_banks" / "Guided_Builder_Master_Word_Bank.json"
    bank.parent.mkdir(parents=True)
    bank.write_text(json.dumps({"topics": {"Gardening": ["TROWEL"]}, "words": ["TROWEL"]}), encoding="utf-8")
    active = tmp_path / "word_banks" / "word_intelligence"
    active.mkdir(); (active / "word_store.json").write_text("old", encoding="utf-8")
    result = safe_rebuild_store(tmp_path)
    assert result["rebuilt"]
    assert (active / "source_manifest.json").is_file()
    assert (active / "word_store.previous.json").read_text(encoding="utf-8") == "old"
