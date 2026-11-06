from reportlab.pdfgen import canvas

import sudoku
from sudoku_symbols import PACKS, pack_label, symbol_pack_for_theme


def test_every_symbol_pack_contains_nine_distinct_symbols():
    assert PACKS
    for name, symbols in PACKS.items():
        assert len(symbols) == 9, name
        assert len(set(symbols)) == 9, name
        assert pack_label(name).endswith("SUDOKU")


def test_topic_mapping_selects_expected_pack():
    assert symbol_pack_for_theme("Christmas & Winter") == "winter_holiday"
    assert symbol_pack_for_theme("National Parks") == "nature"
    assert symbol_pack_for_theme("Sports & Hobbies") == "sports"
    assert symbol_pack_for_theme("Space & Astronomy") == "space"
    assert symbol_pack_for_theme("Ocean Life") == "ocean"
    assert symbol_pack_for_theme("Cats & Pets") == "pets"
    assert symbol_pack_for_theme("Baking & Food") == "kitchen"
    assert symbol_pack_for_theme("Road Trip Adventure") == "travel"


def test_shape_puzzle_and_solution_render_with_same_pack(tmp_path):
    target = tmp_path / "symbols.pdf"
    c = canvas.Canvas(str(target))
    solved = [row[:] for row in sudoku.BASE]
    puzzle = [row[:] for row in solved]
    puzzle[0][0] = 0
    sudoku.draw_sudoku(c, puzzle, 60, 720, 40, "Helvetica", 20,
                       display_style="shapes", symbol_pack="nature")
    c.showPage()
    sudoku.draw_sudoku(c, puzzle, 60, 720, 40, "Helvetica", 20,
                       solution_overlay=solved, display_style="shapes",
                       symbol_pack="nature")
    c.save()
    assert target.stat().st_size > 1000
