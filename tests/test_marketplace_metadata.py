import json

from publishing.metadata_service import build_metadata, marketplace_content, puzzle_type_for
from publishing.manager import PublishingService


def test_each_supported_puzzle_type_gets_its_own_listing_language_and_keywords():
    cases = {"Sudoku": "logic puzzles", "Cryptogram": "code-breaking", "Word Scramble + Trivia": "word scrambles with fact clues", "Mixed Brain Games": "variety brain games"}
    for puzzle_type, expected_phrase in cases.items():
        metadata = build_metadata({"title": f"{puzzle_type} Collection", "puzzle_type": puzzle_type, "theme": "Space & Astronomy", "puzzle_count": 60})
        assert metadata["puzzle_type"] == puzzle_type
        assert expected_phrase in metadata["description"].casefold()
        assert len(metadata["amazon_keywords"]) == 7
        assert len(metadata["etsy_tags"]) <= 13
        assert all(len(tag) <= 20 for tag in metadata["etsy_tags"])


def test_word_search_is_the_safe_default_and_has_word_search_subject():
    metadata = build_metadata({"title": "Garden Word Search", "theme": "Gardening", "puzzle_count": 48})
    assert puzzle_type_for(metadata) == "Word Search"
    assert metadata["ingram_subjects"] == ["Games & Activities / Word & Word Search"]
    assert "garden" in " ".join(metadata["amazon_keywords"]).casefold()


def test_existing_metadata_gets_platform_specific_copy_without_losing_puzzle_type():
    content = marketplace_content({"title": "Cosmic Sudoku", "theme": "Space & Astronomy", "puzzle_type": "Sudoku", "puzzle_count": 100})
    assert "Sudoku" in content["platform_descriptions"]["amazon"]
    assert "printable download" in content["platform_descriptions"]["etsy"].casefold()
    assert content["puzzle_type"] == "Sudoku"


def test_non_word_package_keeps_its_type_through_catalog_and_kdp_handoff(tmp_path):
    package = tmp_path / "out" / "cosmic_sudoku"; package.mkdir(parents=True)
    for name in ("interior.pdf", "kdp_full_wrap.pdf", "front_cover.png"):
        (package / name).write_bytes(b"placeholder")
    (package / "PACKAGE_SOURCE_RECORD.json").write_text(json.dumps({
        "title": "Cosmic Sudoku", "subtitle": "100 Stellar Logic Puzzles", "author": "Jordan M. Slade",
        "puzzle_type": "Sudoku", "theme": "Space & Astronomy", "puzzle_count": 100, "pages": 180,
    }), encoding="utf-8")
    service = PublishingService(tmp_path)
    assert service.sync_output_packages() == 1
    book = service.db.list_books()[0]
    assert book["metadata"]["puzzle_type"] == "Sudoku"
    target, issues = service.prepare(book["book_id"], "amazon")
    assert not issues
    handoff = (target / "description.txt").read_text(encoding="utf-8")
    assert "Sudoku" in handoff and "word-search" not in handoff.casefold()
