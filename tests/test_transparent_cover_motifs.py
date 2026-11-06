from PIL import Image, ImageDraw

import cover


def _opaque_white_count(puzzle_type: str) -> int:
    prior = cover.COVER_PUZZLE_TYPE
    try:
        cover.COVER_PUZZLE_TYPE = puzzle_type
        image = Image.new("RGBA", (cover.W, cover.H), (0, 0, 0, 0))
        cover.puzzle_type_hero(ImageDraw.Draw(image), cover.W // 2, 2200, 94,
                               (66, 183, 176), (25, 40, 52), (255, 214, 92))
        return sum(pixel == (255, 255, 255, 255) for pixel in image.get_flattened_data())
    finally:
        cover.COVER_PUZZLE_TYPE = prior


def test_non_word_search_cover_motifs_have_no_opaque_white_panel():
    for puzzle_type in ("Sudoku", "Cryptogram", "Word Scramble + Trivia"):
        assert _opaque_white_count(puzzle_type) == 0
