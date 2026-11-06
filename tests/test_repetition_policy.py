import copy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from publishing.repetition_policy import POLICY_ID, evaluate
from publishing.production_gate import book_gate
import word_search_creator as app


def source():
    def token(n):
        return "WORD" + chr(65 + n // 676) + chr(65 + n // 26 % 26) + chr(65 + n % 26)
    value = {"title": "Kitchen Table Memories", "author": "Jordan M. Slade",
             "subtitle": "80 large print puzzles", "collection_id": POLICY_ID,
             "collection_book_id": "kitchen_table_memories",
             "repetition_policy": {"id": POLICY_ID}, "no_repeat_words": False,
             "puzzles": [{"name": f"Topic {n}", "words": [token(n * 12 + k) for k in range(12)]}
                         for n in range(80)]}
    value["puzzles"][1]["words"][0] = value["puzzles"][0]["words"][0]
    return value


def test_scoped_repetition_passes_without_certifying_editorial_quality():
    report = evaluate(source())
    assert report["passed"] and report["total_targets"] == 960
    assert report["unique_targets"] == 959
    assert len(report["reused_words"]) == 1
    assert "human review" in report["scope"]


@pytest.mark.parametrize("field,value", [
    ("collection_id", "anything"), ("collection_book_id", "other_book"),
    ("no_repeat_words", True), ("no_repeat_words", "false"),
    ("repetition_policy", {"id": POLICY_ID, "min_unique": 0}),
    ("repetition_policy", None), ("repetition_policy", {"id": "unknown"}),
    ("cover_badge", "NO REPEATED WORDS"), ("subtitle", "A repeat-free collection"),
])
def test_unauthorized_or_misleading_policy_fails(field, value):
    data = source(); data[field] = value
    assert not evaluate(data)["passed"]


def test_normalization_collision_is_rejected():
    data = source(); data["puzzles"][0]["words"][:2] = ["Ice cream", "Ice-cream"]
    assert any("duplicate targets" in error for error in evaluate(data)["errors"])


def test_occurrence_limit_is_enforced():
    data = source()
    for puzzle in data["puzzles"][:4]:
        puzzle["words"][0] = "SPOON"
    assert "SPOON" in evaluate(data)["excessive_occurrences"]


def test_near_duplicate_word_groups_are_rejected():
    data = source()
    data["puzzles"][1]["words"][:7] = data["puzzles"][0]["words"][:7]
    assert evaluate(data)["near_duplicate_groups"]


def test_low_variety_is_rejected_even_when_frequency_limit_passes():
    data = source()
    # Deliberately repeat a whole half-book, so exactly half of targets are unique.
    for n in range(40):
        data["puzzles"][n + 40]["words"] = list(data["puzzles"][n]["words"])
    assert any("75%" in error for error in evaluate(data)["errors"])


def test_repeated_prompts_and_topics_fail():
    data = source()
    data["puzzles"][1]["name"] = data["puzzles"][0]["name"]
    for puzzle in data["puzzles"][:2]:
        puzzle["reflection_prompt"] = "What would you choose?"
    errors = evaluate(data)["errors"]
    assert any("distinct names" in error for error in errors)
    assert any("prompts" in error for error in errors)


def test_publishing_gate_reads_policy_and_still_blocks_bad_content(tmp_path):
    path = tmp_path / "theme.json"; data = source()
    path.write_text(json.dumps(data))
    book = {"source_key": str(path), "metadata": {}}
    assert book_gate(book)["ready"]
    data["puzzles"][0]["words"][0] = ""
    path.write_text(json.dumps(data))
    assert not book_gate(book)["ready"]


def test_theme_audit_keeps_legacy_no_repeat_behavior(tmp_path, monkeypatch):
    # Isolate repetition from generator/topic checks; real generation has its own suite.
    monkeypatch.setattr(app.puzzle_engine, "generate_puzzle", lambda words, N: ([], [], words))
    data = source()
    for puzzle in data["puzzles"]:
        puzzle["words"] = list(reversed(puzzle["words"]))
    path = tmp_path / "theme.json"; path.write_text(json.dumps(data))
    assert not app.audit_theme(path, 7)[0]
    del data["repetition_policy"]
    path.write_text(json.dumps(data))
    assert any("must have no repeated words" in error for error in app.audit_theme(path, 7)[0])


def test_policy_check_does_not_mutate_source():
    data = source(); before = copy.deepcopy(data)
    evaluate(data)
    assert data == before


def test_quick_readiness_and_metadata_retain_scoped_policy():
    from publishing.metadata_service import build_metadata
    data = source()
    for puzzle in data["puzzles"]:
        puzzle["words"] = list(reversed(puzzle["words"]))
    assert app.quick_theme_readiness(data)[0]
    meta = build_metadata(data)
    assert meta["repetition_policy"] == data["repetition_policy"]
    assert meta["no_repeat_words"] is False
    assert meta["collection_book_id"] == "kitchen_table_memories"
    data["no_repeat_words"] = True
    assert not app.quick_theme_readiness(data)[0]


def test_accessible_page_estimate_agrees_in_ui_and_catalog():
    from publishing.manager import PublishingService
    data = source(); data["interior_profile"] = "memories_large_print_v1"
    assert app.estimated_page_count(data) == 160
    assert PublishingService._estimate_wordsearch_pages(data) == 160
