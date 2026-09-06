"""Read-only strategy stress and scale checks for Commercial Intelligence."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from publishing.commercial_intelligence import commercial_assessment


def record(title: str, kind: str = "Word Search", count: int = 100, **extra: object) -> dict:
    base = {"title": title, "subtitle": f"{count} {kind} puzzles with solutions", "theme": "National Parks", "puzzle_type": kind, "puzzle_count": count, "difficulty": "Mixed", "files": {"print_interior": "present", "print_cover": "present", "printable_pdf": "present"}}
    base.update(extra)
    return {"metadata": base}


def main() -> None:
    scenarios = {
        "100_puzzle_sudoku": record("Calm Number Sudoku", "Sudoku", 100),
        "high_count_sudoku": record("Calm Number Sudoku: Extended", "Sudoku", 500),
        "themed_word_search": record("National Parks Word Search", "Word Search", 100),
        "generic_word_search": record("Word Search for Adults", "Word Search", 100, theme="General"),
        "niche_word_search": record("National Parks Trail Word Search", "Word Search", 100),
        "low_value_bn": record("Mini Garden Puzzles", "Word Search", 24, theme="Gardening"),
        "payhip_without_preview": record("Garden Digital Puzzles", "Word Search", 60, theme="Gardening", files={"printable_pdf": "present"}),
        "lulu_distribution_overlap": record("Park Paths Word Search", "Word Search", 100, distribution_plan="KDP Expanded Distribution and Lulu Global Distribution"),
    }
    results = {name: commercial_assessment(value) for name, value in scenarios.items()}
    scales: dict[str, float] = {}
    for size in (100, 250, 500, 1000):
        t0 = time.perf_counter()
        for index in range(size):
            commercial_assessment(record(f"Scale Park Puzzle {index}", "Word Search", 100))
        scales[str(size)] = round(time.perf_counter() - t0, 3)
    report = {
        "scenario_scores": {name: value["commercial_value_score"] for name, value in results.items()},
        "generic_improvement": results["generic_word_search"]["improvements"],
        "lulu_overlap_warning": results["lulu_distribution_overlap"]["marketplaces"]["lulu"]["overlap_warning"],
        "scale_seconds": scales,
        "note": "Local deterministic heuristic test. Scores are not forecasts and do not change catalog data.",
    }
    target = PROJECT / "reports" / "COMMERCIAL_STRESS_AND_SCALE_REPORT.json"
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    text = PROJECT / "reports" / "COMMERCIAL_STRESS_AND_SCALE_REPORT.txt"
    text.write_text("COMMERCIAL STRESS AND SCALE REPORT\n\n" + "\n".join(f"{name}: {score}/100" for name, score in report["scenario_scores"].items()) + "\n\nScale timing (seconds):\n" + "\n".join(f"{size} records: {seconds}" for size, seconds in scales.items()) + "\n\nGeneric-title warning: " + "; ".join(report["generic_improvement"]) + "\nLulu overlap warning: " + report["lulu_overlap_warning"] + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
