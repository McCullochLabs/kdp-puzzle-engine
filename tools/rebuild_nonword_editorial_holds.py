"""Rebuild the active non-word packages affected by editorial source holds.

Old packages remain untouched.  This script creates fresh packages through
the same orchestrator used by the desktop studio and prepares local handoffs
only after each package passes its built-in release gates.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from puzzle_book_studio import create_package
from publishing import PublishingService
from publishing.database import MARKETPLACES

AUTHOR = "Jordan M. Slade"
PLANS = (
    ("Cryptogram", "Celestial Cipher Challenge", "60 Space and Astronomy Cryptograms with Complete Solutions", 60, "Mixed", 6203, "Space & Astronomy"),
    ("Cryptogram", "American Heritage Cipher Challenge", "60 History-Inspired Cryptograms with Complete Solutions", 60, "Mixed", 6204, "History & Heritage"),
    ("Cryptogram", "Faith and Encouragement Cipher Challenge", "60 Uplifting Faith-Inspired Cryptograms with Complete Solutions", 60, "Mixed", 10105, "Bible & Faith"),
    ("Word Scramble + Trivia", "Great American Road Trip Word Scrambles", "60 Road-Trip Word Scrambles with Fact Clues and Answers", 60, "Mixed", 6205, "Road Trips & Highways"),
    ("Word Scramble + Trivia", "Kitchen Table Word Scrambles", "60 Food and Home Word Scrambles with Fact Clues and Answers", 60, "Mixed", 6206, "Food & Home"),
    ("Word Scramble + Trivia", "Journeys Near and Far Word Scrambles", "60 Travel Word Scrambles with Fact Clues and Answers", 60, "Mixed", 6211, "Travel & Adventure"),
    ("Mixed Brain Games", "Wild Places Brain Games Collection", "60 Nature-Inspired Sudoku, Cryptograms, and Word Scrambles with Fact Clues", 60, "Mixed", 6207, "Nature & Outdoors"),
    ("Mixed Brain Games", "Study Break Brain Games Collection", "60 School-Themed Sudoku, Cryptograms, and Word Scrambles with Fact Clues", 60, "Mixed", 6208, "School & Vocabulary"),
)


def main() -> int:
    built: list[dict] = []
    for plan in PLANS:
        folder = create_package(*plan[:3], AUTHOR, *plan[3:], force_rebuild=True)
        built.append({"title": plan[1], "package": str(folder), "status": "package_passed"})

    service = PublishingService(PROJECT)
    service.sync_output_packages()
    books = service.db.list_books()
    for row in built:
        folder = Path(row["package"]).resolve()
        match = next((book for book in books if Path(str(book.get("package_path") or "")).resolve() == folder), None)
        if not match:
            raise RuntimeError(f"Publishing Manager did not register {row['title']} at {folder}")
        row["book_id"] = match["book_id"]
        row["handoffs"] = service.prepare_many([match["book_id"]], list(MARKETPLACES))

    target = PROJECT / "reports" / "NONWORD_EDITORIAL_REBUILD_MANIFEST.json"
    target.write_text(json.dumps({"packages": built}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"manifest": str(target), "packages": built}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
