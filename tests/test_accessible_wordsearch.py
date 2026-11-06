import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import wordsearch
from publishing.accessible_wordsearch import EASY_DIRECTIONS, occurrences, verify_grid, _text, compile_editorial_source

WORDS = ["PENCIL", "RULER", "CHALK", "ERASER", "PAPER", "BOOK", "DESK", "LESSON", "READER", "RECESS", "LUNCH", "CLASS"]


def test_easy_generation_is_local_deterministic_and_restricts_directions():
    random.seed(999); before = random.getstate()
    first = wordsearch.generate_puzzle(WORDS, 12, directions=EASY_DIRECTIONS, rng=random.Random(101))
    assert random.getstate() == before
    assert first == wordsearch.generate_puzzle(WORDS, 12, directions=EASY_DIRECTIONS, rng=random.Random(101))
    grid, placements, words = first
    assert sorted(words) == sorted(WORDS)
    for word, cells in zip(words, placements):
        assert "".join(grid[r][c] for r, c in cells) == word
        assert (cells[1][0] - cells[0][0], cells[1][1] - cells[0][1]) in EASY_DIRECTIONS


def test_occurrence_scan_finds_forward_and_backward():
    grid = [list("CATXXX"), list("XXXTAC")] + [list("XXXXXX") for _ in range(4)]
    assert len(occurrences(grid, "CAT")) == 2


def test_palindrome_is_one_physical_answer():
    grid = [list("EYEX"), list("XXXX"), list("XXXX"), list("XXXX")]
    assert len(occurrences(grid, "EYE")) == 1


def test_collection_sources_retain_format_and_cross_book_diversity():
    from itertools import combinations
    from publishing.memories_collection import compile_source
    from publishing.repetition_policy import evaluate, normalize
    root = Path(__file__).resolve().parents[1] / "word_banks" / "older_adult_memories"
    sources = [compile_source(path) for path in sorted(root.glob("*.json"))]
    assert len(sources) == 3
    pools = []
    for source in sources:
        assert evaluate(source)["passed"]
        assert len(source["puzzles"]) == 80
        assert all(len(p["words"]) == 12 for p in source["puzzles"])
        pool = {normalize(w) for p in source["puzzles"] for w in p["words"]}
        assert all(3 <= len(word) <= 12 for word in pool)
        pools.append(pool)
    for left, right in combinations(pools, 2):
        assert len(left & right) / min(len(left), len(right)) <= .25


def test_independent_validator_detects_corruption():
    grid, cells, words = wordsearch.generate_puzzle(WORDS, 12, directions=EASY_DIRECTIONS, rng=random.Random(101))
    r, c = cells[0][0]; grid[r][c] = "Z"
    assert verify_grid(grid, cells, words)


def test_invalid_direction_configuration_rejected():
    with pytest.raises(ValueError):
        wordsearch.generate_puzzle(WORDS, directions=[])
    with pytest.raises(ValueError):
        wordsearch.generate_puzzle(WORDS, directions=[(0, 0)])


def test_layout_refuses_to_shrink_or_clip_text():
    import io
    from reportlab.pdfgen.canvas import Canvas
    wordsearch.register_fonts()
    c = Canvas(io.BytesIO())
    with pytest.raises(ValueError, match="overflow"):
        _text(c, "A long text that must wrap over several lines", 54, 60, width=80, bottom=54)


def test_policy_change_invalidates_generation_fingerprint():
    from publishing.production_orchestrator import component_fingerprints
    before = component_fingerprints({"book_id": "test"})
    after = component_fingerprints({"book_id": "test", "repetition_policy": {"id": "older_adult_memories_v1"}})
    assert before["generation"] != after["generation"]
    assert before["listing"] != after["listing"]


def test_controlled_repetition_cannot_inherit_stale_listing_promise():
    from publishing.listing_intelligence import verified_facts, validate_output
    facts = verified_facts({"metadata": {"unique_words_verified": True, "repetition_policy": {"id": "older_adult_memories_v1"}}}, "amazon")
    assert "verified no-repeat word promise" not in facts["meaningful_features"]
    assert not validate_output({"description": "No repeated words!"}, facts)[0]


def test_editorial_compiler_preserves_all_words_titles_and_prompts():
    import json
    raw = json.loads((Path(__file__).resolve().parents[1] / "word_banks/older_adult_memories/kitchen_table_memories.json").read_text(encoding="utf-8-sig"))
    compiled = compile_editorial_source(raw)
    assert len(compiled["puzzles"]) == 80
    assert [p["section"] for p in compiled["puzzles"][:8]] == [raw["sections"][0]["title"]] * 8
    assert compiled["puzzles"][0]["words"][0] == "Placemat"
    assert compiled["puzzles"][0]["reflection_prompt"] == raw["sections"][0]["puzzles"][0][2]
    assert compiled["no_repeat_words"] is False
    assert compiled["cover_badge"] == "80 PUZZLES"
