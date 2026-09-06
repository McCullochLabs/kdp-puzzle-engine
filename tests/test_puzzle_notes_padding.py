from pypdf import PdfReader

from puzzle_book_studio import make_interior


def test_small_scramble_book_uses_helpful_notes_instead_of_blank_padding(tmp_path):
    target = tmp_path / "scramble.pdf"
    make_interior(
        "Word Scramble + Trivia",
        "Acceptance Scramble",
        "24 word games with answers",
        "Jordan M. Slade",
        24,
        "Standard",
        8113,
        target,
    )
    reader = PdfReader(str(target))
    assert len(reader.pages) == 24
    assert all((page.extract_text() or "").strip() for page in reader.pages)
    assert "PUZZLE NOTES" in (reader.pages[-1].extract_text() or "")


def test_odd_mixed_book_uses_final_notes_instead_of_blank_parity_page(tmp_path):
    target = tmp_path / "mixed.pdf"
    make_interior(
        "Mixed Brain Games",
        "Acceptance Mixed",
        "Sudoku, codes, and word games",
        "Jordan M. Slade",
        24,
        "Mixed",
        9127,
        target,
    )
    reader = PdfReader(str(target))
    assert len(reader.pages) % 2 == 0
    assert all((page.extract_text() or "").strip() for page in reader.pages)
