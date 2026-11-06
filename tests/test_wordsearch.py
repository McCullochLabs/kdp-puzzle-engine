import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import wordsearch as ws
import word_search_creator as app


def test_educational_tracker_uses_real_mini_theme_name():
    puzzles = [{"name": "Reading Comprehension Strategies"}]
    label = ws.tracker_puzzle_name(puzzles, 1)
    assert label.startswith("Reading Comprehension")
    assert len(label) <= 28
    assert label.endswith("...")
    assert "Vocabulary Practice" not in label


def test_clean_words_uppercases_and_strips_non_alpha():
    assert ws.clean_words(["cat", "Dog-2", "  fish "]) == ["CAT", "DOG", "FISH"]


def test_clean_words_rejects_words_longer_than_largest_supported_grid():
    # Automatic sizing supports dense books up to the 21×21 grid limit.
    too_long = "X" * (ws.MAX_GRID_N + 1)
    import pytest
    with pytest.raises(ValueError,match='replace'):
        ws.clean_words([too_long, "OK"])


def test_clean_words_rejects_empty_results():
    import pytest
    with pytest.raises(ValueError,match='replace'):
        ws.clean_words(["123", "-- ", "cat"])


def test_interior_section_plan_adds_consistent_chapters_without_reordering_puzzles():
    puzzles = [{"name": f"Puzzle {number}", "words": ["CAT"], "mini_theme": "Planets" if number <= 5 else "Stars"}
               for number in range(1, 8)]
    plan = ws.interior_section_plan({"detected_topic": "Space", "interior_sections": {"group_size": 5, "divider_pages": True}}, puzzles)
    assert len(plan) == len(puzzles)
    assert [item["chapter"] for item in plan] == [1, 1, 1, 1, 1, 2, 2]
    assert [item["starts_section"] for item in plan] == [True, False, False, False, False, True, False]
    assert [item["title"] for item in plan[:5]] == ["Planets"] * 5
    assert ws.interior_divider_page_count({"interior_sections": {"group_size": 5, "divider_pages": True}}, puzzles) == 2


def test_direct_paste_kdp_description_contains_no_html_markup():
    data = {"title": "Garden Discovery Word Search", "detected_topic": "Gardening", "no_repeat_words": True,
            "puzzles": [{"words": ["ROSE"]} for _ in range(48)]}
    text = app.kdp_enhanced_description(data)
    assert "<p>" not in text and "<li>" not in text and "<b>" not in text
    assert "Inside this collection:" in text
    assert "- 48 themed word search puzzles" in text


def test_quick_readiness_does_not_call_a_protected_word_bank_ready():
    data = {
        "title": "Test Book",
        "puzzles": [{"name": f"Puzzle {number}", "words": [f"WORD{chr(65 + number // 26)}{chr(65 + number % 26)}{chr(65 + index)}" for index in range(12)]} for number in range(48)],
    }
    data["puzzles"][0]["words"][0] = "LEGO"
    ready, label = app.quick_theme_readiness(data)
    assert not ready
    assert "safe word" in label.lower()


def test_quick_readiness_blocks_dictionary_style_alphabetical_books():
    data = {
        "title": "Dictionary Looking Book",
        "puzzles": [
            {"name": f"Puzzle {number}",
             "words": [f"WORD{chr(65 + number // 26)}{chr(65 + number % 26)}{chr(65 + index)}" for index in range(12)]}
            for number in range(48)
        ],
    }
    ready, label = app.quick_theme_readiness(data)
    assert not ready
    assert "alphabetized" in label.lower()


def test_pdf_engine_uses_ascii_for_visible_separators():
    source = Path(ws.__file__).read_text(encoding="utf-8")
    assert "PUZZLE {idx} - {name.upper()}" in source
    assert '"• Pick any puzzle' not in source


def test_generate_puzzle_grid_is_square_and_fully_filled():
    random.seed(1)
    grid, placements, placed = ws.generate_puzzle(["CAT", "DOG", "BIRD", "FISH"])
    assert len(grid) == ws.GRID_N
    assert all(len(row) == ws.GRID_N for row in grid)
    assert all(cell != "" for row in grid for cell in row)


def test_generate_puzzle_placed_words_actually_read_off_the_grid():
    random.seed(1)
    grid, placements, placed = ws.generate_puzzle(["CAT", "DOG", "BIRD", "FISH"])
    assert placed, "expected at least one word to be placed in a 15x15 grid"
    for word, cells in zip(placed, placements):
        read_back = "".join(grid[r][c] for r, c in cells)
        assert read_back == word


def test_generate_puzzle_only_reports_words_it_was_given():
    random.seed(2)
    words = ["CAT", "DOG"]
    _, _, placed = ws.generate_puzzle(words)
    assert set(placed) <= set(words)


def test_standard_package_explicitly_disables_saved_signature_extras():
    theme = {"signature_edition": {"enabled": True, "passport_title": "Puzzle Passport"}}
    package = app.package_data_from_settings(theme, {"signature_edition": False})
    assert package["signature_edition"]["enabled"] is False


def test_only_intentionally_named_signature_themes_default_to_signature():
    signature = {"signature_edition": {"enabled": True}, "title": "Garden Word Search — Signature Edition"}
    standard = {"signature_edition": {"enabled": True}, "title": "Zion National Park Word Search"}
    assert app.theme_defaults_to_signature(Path("signature_garden.json"), signature)
    assert not app.theme_defaults_to_signature(Path("national_parks_02_zion.json"), standard)


def test_contributor_safety_rejects_brand_as_author():
    notes = app.contributor_safety_notes("Slade Puzzles")
    assert notes and notes[0].startswith("BLOCK")


def test_contributor_safety_accepts_pen_name():
    assert app.contributor_safety_notes("Jordan M. Slade") == []
