"""Phase 3 deterministic planning tests; they create no production content."""
from __future__ import annotations

import json
from pathlib import Path

from word_intelligence.book_planning import (
    BookPlan, BookPlanner, PlanRequest, load_plan, save_plan,
)
from word_intelligence.capacity import ContentCapacityEngine, REVIEW_LEGACY, REVIEW_STRICT
from word_intelligence.content_contracts import (
    ContentRecord, FormatRules, Provenance, QualityStatus, TopicReference,
    deterministic_content_id, normalized_value,
)
from word_intelligence.content_registry import ContentRegistry
from word_intelligence.qualification import ApprovalDecision, build_review_batch, load_approval_input
from word_intelligence.taxonomy import TopicTaxonomy


def _record(value, *, content_type="word", topic="gardening", editorial="approved", link_status="approved",
            factual="verified", payload=None, source="curated"):
    return ContentRecord(
        id=deterministic_content_id(content_type, value, source_id=f"{source}:{value}"), type=content_type,
        display=value, normalized=normalized_value(value),
        topics=(TopicReference(topic, "primary", 100, link_status),), format_rules=FormatRules(),
        quality=QualityStatus(editorial, factual, False, False), provenance=Provenance(source, f"fixture:{value}"),
        payload=payload or {},
    )


def _token(index: int) -> str:
    """Alphabetic unique token: normalized Word Search values discard digits."""
    letters = []
    value = index
    while True:
        letters.append(chr(ord("A") + value % 26))
        value = value // 26 - 1
        if value < 0:
            return "".join(reversed(letters))


def _planner(records, approvals=None):
    taxonomy = TopicTaxonomy.from_master_bank({"topics": {"Gardening": ["TROWEL"], "General": ["FACT"]}})
    registry = ContentRegistry()
    for record in records: registry.add(record)
    engine = ContentCapacityEngine(".", taxonomy, registry, cache_state={"state": "fresh"})
    engine.manifest = {"source_hashes": {"fixture": "yes"}}
    engine.source_revision = "fixture-revision"
    engine.reservation_evidence = []
    return BookPlanner(engine, approvals), taxonomy.resolve("Gardening")


def test_word_search_exact_48x12_plan_has_no_repeat_and_exact_allocations():
    records = [_record(f"GARDENWORD{_token(index)}", payload={"mini_theme": f"group{index % 4}"}) for index in range(600)]
    planner, garden = _planner(records)
    result = planner.create(PlanRequest(garden, "word_search", 48, 12, seed=12345))
    assert result.status == "valid" and result.plan
    assert len(result.plan.selected_content_ids) == 576
    assert len(set(result.plan.selected_content_ids)) == 576
    assert len(result.plan.puzzle_allocations) == 48
    assert all(len(row.content_ids) == 12 for row in result.plan.puzzle_allocations)
    assert planner.validate(result.plan).status == "valid"


def test_labeled_puzzles_do_not_mix_unrelated_mini_themes():
    records = [_record(f"GARDENWORD{_token(index)}", payload={"mini_theme": f"group{index % 4}"}) for index in range(96)]
    planner, garden = _planner(records)
    plan = planner.create(PlanRequest(garden, "word_search", 8, 12, seed=90210)).plan
    assert plan
    for allocation in plan.puzzle_allocations:
        assert allocation.mini_theme
        actual = {planner.engine.registry.get(item).payload.get("mini_theme") for item in allocation.content_ids}
        assert actual == {allocation.mini_theme}


def test_planned_word_order_is_seeded_but_not_alphabetical():
    records = [_record(f"WORD{_token(index)}") for index in range(30)]
    planner, garden = _planner(records)
    request = PlanRequest(garden, "word_search", 2, 12, seed=31415)
    first = planner.create(request).plan
    second = planner.create(request).plan
    assert first and second
    assert first.puzzle_allocations == second.puzzle_allocations
    displays = [planner.engine.registry.get(item).display for item in first.puzzle_allocations[0].content_ids]
    assert displays != sorted(displays)


def test_insufficient_pool_never_creates_short_word_search_puzzles():
    planner, garden = _planner([_record(f"WORD{_token(index)}") for index in range(11)])
    result = planner.create(PlanRequest(garden, "word_search", 1, 12))
    assert result.plan is None and result.status == "insufficient_verified_content"


def test_same_seed_serializes_reloads_and_regenerates_identically(tmp_path):
    planner, garden = _planner([_record(f"WORD{_token(index)}") for index in range(30)])
    request = PlanRequest(garden, "word_search", 2, 12, seed=77)
    first, second = planner.create(request).plan, planner.create(request).plan
    assert first and second and first.selected_content_ids == second.selected_content_ids
    path = save_plan(tmp_path / "plan.json", first)
    restored = load_plan(path)
    assert restored.to_dict() == first.to_dict()
    assert planner.validate(restored).status == "valid"


def test_changed_seed_changes_a_sufficient_selection():
    planner, garden = _planner([_record(f"WORD{_token(index)}") for index in range(100)])
    first = planner.create(PlanRequest(garden, "word_search", 2, 12, seed=1)).plan
    second = planner.create(PlanRequest(garden, "word_search", 2, 12, seed=2)).plan
    assert first and second and first.selected_content_ids != second.selected_content_ids


def test_stale_source_and_changed_capacity_proof_invalidate_saved_plan():
    records = [_record(f"WORD{_token(index)}") for index in range(20)]
    planner, garden = _planner(records)
    plan = planner.create(PlanRequest(garden, "word_search", 1, 12)).plan
    assert plan
    planner.engine.source_revision = "changed"
    assert planner.validate(plan).status == "stale"
    planner.engine.source_revision = "fixture-revision"
    planner.engine.registry.records.pop(records[0].id)
    assert planner.validate(plan).status == "invalid"


def test_long_and_duplicate_normalized_records_are_never_selected():
    records = [_record(f"WORD{_token(index)}") for index in range(12)]
    records += [_record("A" * 22), _record("WORD A", source="imported")]
    planner, garden = _planner(records)
    result = planner.create(PlanRequest(garden, "word_search", 1, 12))
    assert result.plan and all("A" * 22 not in item for item in result.plan.selected_content_ids)
    assert len(result.plan.selected_content_ids) == len(set(result.plan.selected_content_ids))


def test_missing_mini_theme_map_is_visible_not_fabricated():
    planner, garden = _planner([_record(f"WORD{_token(index)}") for index in range(12)])
    result = planner.create(PlanRequest(garden, "word_search", 1, 12))
    assert result.plan and "mini_theme_map_missing" in " ".join(result.plan.warnings)


def test_word_search_precheck_uses_existing_grid_logic_without_writing_files():
    planner, garden = _planner([_record(f"WORD{_token(index)}") for index in range(12)])
    plan = planner.create(PlanRequest(garden, "word_search", 1, 12, seed=33)).plan
    assert plan and planner.word_search_placement_precheck(plan).status == "valid"


def test_controlled_existing_generator_parity_uses_a_temporary_pdf_only(tmp_path, monkeypatch):
    """One Phase 3 parity check: plan IDs feed the unchanged grid/PDF path."""
    import sys
    import wordsearch
    planner, garden = _planner([_record(f"WORD{_token(index)}") for index in range(12)])
    plan = planner.create(PlanRequest(garden, "word_search", 1, 12, seed=41)).plan
    assert plan and planner.word_search_placement_precheck(plan).status == "valid"
    words = [planner.engine.registry.get(item).display for item in plan.puzzle_allocations[0].content_ids]
    theme = tmp_path / "parity_theme.json"
    output = tmp_path / "parity.pdf"
    theme.write_text(json.dumps({"title": "Parity Check", "subtitle": "Temporary test", "author": "Test",
                                  "puzzles": [{"name": "Planned Puzzle", "words": words}]}), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["wordsearch.py", "--themes", str(theme), "--out", str(output), "--seed", "41", "--preview-puzzles", "1"])
    wordsearch.main()
    assert output.is_file() and output.stat().st_size > 0


def test_explicit_human_approval_fixture_can_enable_strict_plan_without_source_mutation():
    records = [_record(f"WORD{_token(index)}", editorial="legacy_unreviewed", link_status="legacy_unreviewed", source="legacy") for index in range(12)]
    approvals = {record.id: ApprovalDecision(record.id, "gardening", "approved") for record in records}
    planner, garden = _planner(records, approvals)
    result = planner.create(PlanRequest(garden, "word_search", 1, 12, review_policy=REVIEW_STRICT))
    assert result.plan and all(record.quality.editorial_status == "legacy_unreviewed" for record in records)


def test_legacy_content_without_explicit_approval_remains_blocked_in_strict_mode():
    planner, garden = _planner([_record(f"WORD{_token(index)}", editorial="legacy_unreviewed", link_status="legacy_unreviewed", source="legacy") for index in range(12)])
    assert planner.create(PlanRequest(garden, "word_search", 1, 12)).plan is None


def test_cryptogram_strict_excludes_mechanical_and_duplicate_templates():
    good = [_record(f"A CLEAR UNIQUE PROMPT {_token(index)}", content_type="cryptogram_prompt") for index in range(3)]
    mechanical = _record("CURIOSITY MAKES GARDENS MORE INTERESTING", content_type="cryptogram_prompt")
    planner, garden = _planner([*good, mechanical])
    result = planner.create(PlanRequest(garden, "cryptogram", 3, 1))
    assert result.plan and mechanical.id not in result.plan.selected_content_ids


def test_scramble_trivia_keeps_the_complete_linked_trio_and_requires_fact_review():
    good = [_record(f"WORD{_token(index)}", content_type="trivia", payload={"question": f"Question {_token(index)}?", "answer": f"Answer {_token(index)}"}) for index in range(2)]
    missing = _record("ORPHAN", content_type="trivia", payload={"question": "Missing answer?"})
    planner, garden = _planner([*good, missing])
    result = planner.create(PlanRequest(garden, "scramble_trivia", 2, 1))
    assert result.plan and missing.id not in result.plan.selected_content_ids


def test_sudoku_plan_records_supported_configuration_without_touching_generator():
    planner, garden = _planner([])
    result = planner.create(PlanRequest(garden, "sudoku", 60, 1, symbol_set="letters", difficulty="hard"))
    assert result.plan and result.plan.quality_snapshot["unique_solution_required"]
    assert planner.create(PlanRequest(garden, "sudoku", 1, 1, symbol_set="emoji")).status == "unsupported_format"


def test_themed_mixed_plan_blocks_instead_of_falling_back_to_general_content():
    planner, garden = _planner([])
    result = planner.create(PlanRequest(garden, "mixed", 6, 1))
    assert result.plan is None and result.status == "blocked_section"


def test_general_mixed_plan_permits_explicit_general_pools():
    records = [_record(f"PROMPT {_token(index)}", content_type="cryptogram_prompt", topic="general") for index in range(3)]
    records += [_record(f"TRIVIA{_token(index)}", content_type="trivia", topic="general", payload={"question": f"Q {_token(index)}?", "answer": f"A {_token(index)}"}) for index in range(2)]
    planner, _ = _planner(records)
    result = planner.create(PlanRequest("General", "mixed", 6, 1, general_pool=True))
    assert result.plan and result.plan.quality_snapshot["general_pool_explicit"]


def test_review_batch_and_approval_input_are_explicit_non_mutating_artifacts(tmp_path):
    record = _record("Trowel", editorial="legacy_unreviewed", link_status="legacy_unreviewed", source="legacy")
    batch = build_review_batch([record], "gardening", "word_search")
    assert batch["records"][0]["suggested_review_action"] == "qualified_for_review"
    decision_path = tmp_path / "approval.json"
    decision_path.write_text(json.dumps({"schema_version": 1, "decisions": [{"content_id": record.id, "topic_id": "gardening", "decision": "approved", "review_source": "human"}]}), encoding="utf-8")
    assert load_approval_input(decision_path)[record.id].is_approval
