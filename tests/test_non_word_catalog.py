from collections import Counter
import json

import pytest

from publishing.non_word_catalog import (
    READINESS, TARGETS, capacity_evidence, deterministic_mixed_allocation,
    non_word_catalog_plan,
)


def test_mixed_allocation_is_deterministic_and_complete():
    first = deterministic_mixed_allocation(101, "balanced")
    assert first == deterministic_mixed_allocation(101, "balanced")
    assert sum(first.values()) == 101
    assert set(first) == {"word_search", "sudoku", "cryptogram", "scramble_trivia"}


def test_mixed_allocation_never_uses_silent_fallback():
    with pytest.raises(ValueError, match="Generic fallback is not allowed"):
        deterministic_mixed_allocation(48, capacities={"word_search": 48, "sudoku": 48, "cryptogram": 0, "scramble_trivia": 48})


def test_capacity_requires_format_specific_review_evidence(tmp_path):
    folder = tmp_path / "word_banks"; folder.mkdir()
    (folder / "puzzle_content_library.json").write_text(json.dumps({"packs": {"Travel": {
        "cryptograms": ["LEGACY TEXT", {"text": "ORIGINAL", "review_state": "approved", "rights_status": "original", "source": "editorial"}],
        "trivia": [["ROAD", "A question?", "Answer"], {"answer_word": "MAPS", "question": "Verified?", "answer": "Yes", "review_state": "approved", "factual_verification_status": "verified", "source": "reference"}],
        "scrambles": [{"display": "TRAIL", "review_state": "approved"}],
    }}}), encoding="utf-8")
    result = capacity_evidence(tmp_path, "Travel")
    assert result["cryptogram"] == {"source": 2, "verified": 1, "rights_safe": 1}
    assert result["trivia"] == {"source": 2, "verified": 1, "fact_checked": 1}
    assert result["scramble"]["verified"] == 1


def test_plan_has_required_waves_topic_audit_and_no_fake_readiness(tmp_path):
    plan = non_word_catalog_plan(tmp_path, [{"puzzle_type": "word_search"}] * 170)
    assert plan["catalog_balance"]["word_search"] == 170
    assert len(plan["topic_audit"]) >= 30
    assert {key: tuple(value["target_range"]) for key, value in plan["formats"].items()} == TARGETS
    assert len(plan["formats"]["mixed"]["first_wave"]) == 5
    assert len(plan["formats"]["scramble_trivia"]["first_wave"]) == 5
    assert len(plan["formats"]["cryptogram"]["first_wave"]) == 4
    assert len(plan["formats"]["sudoku"]["first_wave"]) == 4
    assert all(len(section["second_wave"]) >= 10 for section in plan["formats"].values())
    assert all(item["readiness"] in READINESS for section in plan["formats"].values() for item in section["top_20"])
    assert all(item["readiness"] != "Ready Now" for key in ("mixed", "scramble_trivia", "cryptogram") for item in plan["formats"][key]["top_20"])


def test_sudoku_topic_theme_is_not_overvalued(tmp_path):
    plan = non_word_catalog_plan(tmp_path)
    holiday = next(item for item in plan["formats"]["sudoku"]["all_opportunities"] if "Holiday" in item["topic"])
    assert holiday["readiness"] == "Not Recommended"
    assert "cosmetic" in holiday["blockers"][0]
