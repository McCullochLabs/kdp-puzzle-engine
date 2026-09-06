from __future__ import annotations

import pytest

from publishing.capability_audit import ProductionCapabilityAudit
from publishing.puzzle_types import PuzzleTypeCapability, PuzzleTypeRegistry, REGISTRY, resolve_puzzle_type
from word_intelligence.capacity import CapacityRequest

from test_business_automation import _Service
from test_content_capacity_engine import _engine


def _planned_crossword() -> PuzzleTypeCapability:
    return PuzzleTypeCapability(
        "crossword_test", "Crossword Test", "word_logic", "planned",
        aliases=("test crossword",), content_requirements=("answers", "clues", "grid"),
        known_limitations=("No generator is registered.",),
    )


def test_registry_resolves_ids_display_names_and_aliases_without_loading_services():
    registry = PuzzleTypeRegistry((_planned_crossword(),))
    assert registry.resolve("crossword_test").display_name == "Crossword Test"
    assert registry.resolve("Crossword Test").type_id == "crossword_test"
    assert registry.resolve("test crossword").type_id == "crossword_test"
    assert not registry.resolve("not a real format")
    with pytest.raises(ValueError, match="Unknown puzzle type"):
        registry.require("not a real format")


def test_current_readiness_discovery_contains_only_existing_production_types():
    values = REGISTRY.ids_for_readiness_ui()
    assert values == ("word_search", "sudoku", "cryptogram", "scramble_trivia", "mixed")
    assert "crossword" not in values
    assert resolve_puzzle_type("Word Search").type_id == "word_search"


def test_planned_type_is_visible_to_audit_but_never_claimed_as_available(tmp_path):
    registry = PuzzleTypeRegistry((_planned_crossword(),))
    row = ProductionCapabilityAudit(_Service(tmp_path, []), registry=registry).evaluate()[0]
    assert row.name == "Crossword Test"
    assert row.status == "RED"
    assert row.confidence == "declared"
    assert "generator" in row.next_action


def test_capacity_rejects_unknown_and_planned_formats_before_content_allocation():
    engine, garden, _ = _engine([])
    unknown = engine.evaluate(CapacityRequest(garden, "made_up_puzzle", 1, 1))
    planned = engine.evaluate(CapacityRequest(garden, "crossword", 1, 1))
    assert unknown.status == "unsupported_format"
    assert "registered puzzle type" in unknown.blockers[0]
    assert planned.status == "unsupported_format"
    assert "planned" in planned.blockers[0]
