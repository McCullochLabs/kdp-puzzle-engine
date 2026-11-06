"""Cover examples must remain unsolved and match Sudoku's seeded first page."""

import random

import cover
import puzzle_book_studio as studio
import sudoku


def test_sudoku_cover_uses_unsolved_unique_first_puzzle():
    count, seed = 60, 91004
    sample = studio.sudoku_cover_sample(count, "Mixed", seed)
    assert len(sample) == 81
    assert "." in sample
    assert sudoku.count_solutions([
        [int(value) if value != "." else 0 for value in sample[row * 9:(row + 1) * 9]]
        for row in range(9)
    ]) == 1

    rng = random.Random(seed)
    difficulties = ["easy"] * (count * 4 // 10) + ["medium"] * (count * 35 // 100)
    difficulties += ["hard"] * (count - len(difficulties))
    rng.shuffle(difficulties)
    expected, _rating = sudoku.make_rated_puzzle(sudoku.make_solved(rng), difficulties[0], rng)
    assert sample == "".join(str(value) if value else "." for row in expected for value in row)


def test_standalone_sudoku_cover_fallback_is_unsolved():
    assert len(cover.DEFAULT_SUDOKU_COVER_SAMPLE) == 81
    assert "." in cover.DEFAULT_SUDOKU_COVER_SAMPLE
