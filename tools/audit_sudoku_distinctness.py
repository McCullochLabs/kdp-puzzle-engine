"""Reproduce recorded Sudoku seeds to detect exact grid reuse across books.

This audits the generator's deterministic output. It does not claim that text
extraction proves the printed PDF contains the same grid; proofing remains due.
"""
from __future__ import annotations

import json
import random
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import sudoku


def generated_grids(seed: int, count: int, difficulty: str):
    rng = random.Random(seed)
    profile = {"Easy": "easy", "Hard": "hard"}.get(difficulty, "mixed")
    if profile == "mixed":
        levels = (["easy"] * (count * 4 // 10) + ["medium"] * (count * 35 // 100) +
                  ["hard"] * (count - count * 4 // 10 - count * 35 // 100))
    else:
        levels = [profile] * count
    rng.shuffle(levels)
    for level in levels:
        solved = sudoku.make_solved(rng)
        puzzle = sudoku.make_puzzle(solved, level, rng)
        yield tuple(value for row in puzzle for value in row)


def main() -> None:
    rows = []
    all_grids: dict[tuple[int, ...], list[str]] = defaultdict(list)
    for path in sorted((ROOT / "out").glob("*/04_REVIEW_AND_RECORDS/PACKAGE_SOURCE_RECORD.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("puzzle_type") != "Sudoku":
            continue
        title = str(record.get("title") or path.parents[1].name)
        seed = record.get("puzzle_seed")
        count = int(record.get("puzzle_count") or 0)
        if seed is None:
            rows.append({"title": title, "status": "NOT REPRODUCIBLE", "reason": "Seed missing from package record."})
            continue
        grids = list(generated_grids(int(seed), count, str(record.get("difficulty") or "Mixed")))
        for number, grid in enumerate(grids, 1):
            all_grids[grid].append(f"{title} / puzzle {number}")
        rows.append({"title": title, "status": "RECONSTRUCTED", "seed": seed,
                     "puzzles": count, "unique_within_book": len(set(grids)) == count})
    duplicates = [places for places in all_grids.values() if len(places) > 1]
    result = {"generated": datetime.now().isoformat(timespec="seconds"),
              "scope": "Reconstructed generator grids from recorded Sudoku seeds; printed-grid visual correspondence not certified.",
              "books": rows, "exact_grid_duplicates": duplicates,
              "reconstructed_grids": sum(int(row.get("puzzles") or 0) for row in rows)}
    target = ROOT / "reports" / "SUDOKU_DISTINCTNESS.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Reconstructed {result['reconstructed_grids']} Sudoku grids across {sum(row['status'] == 'RECONSTRUCTED' for row in rows)} books; exact duplicates: {len(duplicates)}.")
    for row in rows:
        if row["status"] != "RECONSTRUCTED" or not row["unique_within_book"]:
            print(row)
    print(target)


if __name__ == "__main__":
    main()
