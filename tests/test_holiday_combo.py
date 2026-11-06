from __future__ import annotations

import pytest

from holiday_combo import _front_pages, _listing_text, build_plan, load_source
from sudoku_symbols import PACKS, symbol_pack_for_theme


def test_reviewed_holiday_source_and_exact_200_puzzle_plan():
    holidays = load_source()
    words, sudokus = build_plan(holidays)
    assert len(holidays) == 10
    assert len(words) == len(sudokus) == 100
    assert [p.number for p in words[:10]] == list(range(1, 11))
    assert [p.number for p in sudokus[:10]] == list(range(11, 21))
    for holiday in holidays:
        name = holiday["name"]
        chapter_words = [word for puzzle in words if puzzle.holiday == name for word in puzzle.words]
        chapter_sudokus = [puzzle for puzzle in sudokus if puzzle.holiday == name]
        assert len(chapter_words) == len(set(chapter_words)) == 120
        assert all(len(puzzle.words) == 12 for puzzle in words if puzzle.holiday == name)
        assert sum(p.style == "numbers" for p in chapter_sudokus) == 5
        assert sum(p.style == "shapes" for p in chapter_sudokus) == 5
        assert all(p.symbol_pack == holiday["symbol_pack"] for p in chapter_sudokus)
        assert len(PACKS[holiday["symbol_pack"]]) == 9


def test_holiday_plan_is_deterministic_without_alphabetical_lists():
    holidays = load_source()
    a, _ = build_plan(holidays)
    b, _ = build_plan(holidays)
    assert a == b
    assert all(list(p.words) != sorted(p.words) for p in a)


def test_malformed_chapter_is_blocked_without_reducing_puzzle_count(tmp_path):
    import json
    source = load_source()
    source[0]["mini_themes"]["Midnight Countdown"] = "CLOCK|CLOCK"
    file = tmp_path / "bad.json"
    file.write_text(json.dumps({"holidays": source}), encoding="utf-8")
    with pytest.raises(ValueError, match="24 valid"):
        load_source(file)


def test_mothers_and_fathers_day_resolve_to_distinct_symbols():
    assert symbol_pack_for_theme("Mother's Day") == "mothers_day"
    assert symbol_pack_for_theme("Father's Day") == "fathers_day"


def test_holiday_title_page_names_the_real_book_and_12_word_promise(tmp_path):
    from pypdf import PdfReader
    from reportlab.pdfgen import canvas
    import wordsearch

    wordsearch.register_fonts()
    path = tmp_path / "opening.pdf"
    pdf = canvas.Canvas(str(path), pagesize=(612, 792))
    _front_pages(pdf, load_source())
    pdf.save()
    pages = PdfReader(str(path)).pages
    assert len(pages) == 3
    title_text = pages[0].extract_text()
    assert "CELEBRATE" in title_text and "ALL YEAR" in title_text
    assert "12-WORD SEARCHES" in title_text
    assert "HANUKKAH" in title_text
    welcome_text = pages[1].extract_text()
    assert "Copyright © 2026 Jordan M. Slade" in welcome_text
    assert "Published by Slade Puzzles" in welcome_text


def test_holiday_listing_is_copy_ready_truthful_and_search_complementary():
    listing = _listing_text(316)
    description = listing.split("DESCRIPTION — COPY\n", 1)[1].split("\nKEYWORD IDEAS", 1)[0]
    keyword_block = listing.split("KEYWORD IDEAS — ENTER IN AMAZON'S SEVEN KEYWORD FIELDS\n", 1)[1].split("\nCATEGORY", 1)[0]
    keywords = [line.split(". ", 1)[1] for line in keyword_block.splitlines() if ". " in line]
    assert "Ten celebrations. Two puzzle styles." in description
    assert "1,200 word-search entries" in description
    assert "Words do not repeat within the same holiday chapter" in description
    assert "<p>" not in description and "http" not in description.lower()
    assert len(keywords) == 7
    assert all(len(keyword) <= 50 for keyword in keywords)
    assert "AI-generated content disclosure: Yes — Text and Images." in listing
