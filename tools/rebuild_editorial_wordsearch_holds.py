"""Replace active legacy Word Search holds with promoted editorial sources."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from publishing import PublishingService
from tools.build_commercial_baseline import build_word_search


STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
THEMES = ROOT / "themes" / "Editorial Rebuilds"
MANIFEST = ROOT / "reports" / "EDITORIAL_WORDSEARCH_PACKAGE_REBUILDS.json"


PLANS = (
    ("classic_cars_and_road_trips_editorial_v2.json", "Classic Cars and Road Trips Word Search",
     "48 large-print puzzles for vintage vehicle fans and open-road dreamers", 6101),
    ("advanced_vocabulary_challenge_editorial_v2.json", "Advanced Vocabulary Challenge Word Search",
     "48 large-print word searches for stronger vocabulary and confident word lovers", 6103),
    ("faithful_words_50_editorial_v2.json", "Faithful Words Word Search",
     "50 large-print puzzles for Bible themes, hope and encouragement", 6113),
    ("road_trip_classics_editorial_v2.json", "Road Trip Classics Word Search",
     "50 large-print puzzles about highways, scenic stops and open-road adventures", 6114),
    ("american_moments_editorial_v2.json", "American Moments Word Search",
     "50 large-print puzzles about United States history, civics and daily life", 6115),
    ("faithful_words_signature_100_editorial_v2.json", "Faithful Words: Large-Print Bible Word Search for Adults",
     "100 faith-inspired puzzles for peaceful quiet-time solving", 731001),
    ("vocabulary_ladder_grade_5_editorial_v2.json", "Vocabulary Ladder: Grade 5 Word Quest",
     "48 themed vocabulary word searches for Grade 5 reading, spelling and word confidence", 731105),
)


OLD_FOLDERS = (
    "commercial_baseline_6101_classic_cars_and_road_trips_word_search",
    "commercial_baseline_6102_vocabulary_adventures_grade_school",
    "commercial_baseline_6103_advanced_vocabulary_challenge_word_search",
    "commercial_baseline_6113_faithful_words_word_search",
    "commercial_baseline_6114_road_trip_classics_word_search",
    "commercial_baseline_6115_american_moments_word_search",
    "commercial_baseline_731001_faithful_words_large-print_bible_word_search_for_adults",
    "commercial_baseline_731105_vocabulary_ladder_grade_5_word_quest",
)

OLD_THEME_FILES = (
    "themes/Launch Collection/Verified Release Candidates/classic_cars_road_trips.json",
    "themes/Vocabulary Ladder Collection/vocabulary_adventures_grade_school.json",
    "themes/Launch Collection/Verified Release Candidates/advanced_vocabulary_challenge.json",
    "themes/Trending 50 Puzzle Releases/faithful_words_20260828_203806.json",
    "themes/Trending 50 Puzzle Releases/road_trip_classics_20260828_203806.json",
    "themes/Trending 50 Puzzle Releases/american_moments_20260828_203806.json",
    "themes/Faithful Words Series/faithful_words_large_print_signature_100.json",
    "themes/Vocabulary Ladder Collection/Grades 5 to 12/vocabulary_ladder_grade_5.json",
)


def archive_legacy() -> list[dict]:
    out = (ROOT / "out").resolve()
    archive = (ROOT / "archive" / "replaced_packages").resolve()
    archive.mkdir(parents=True, exist_ok=True)
    rows = []
    for name in OLD_FOLDERS:
        source = (out / name).resolve()
        if source.parent != out or not source.is_dir():
            continue
        target = archive / f"{name}_legacy_{STAMP}"
        if target.exists():
            raise RuntimeError(f"Archive target already exists: {target}")
        shutil.move(str(source), str(target))
        rows.append({"source": str(source), "archive": str(target)})
    return rows


def archive_legacy_sources() -> list[dict]:
    theme_root = (ROOT / "themes").resolve()
    archive = (ROOT / "archive" / "replaced_themes" / f"editorial_legacy_{STAMP}").resolve()
    rows = []
    for relative in OLD_THEME_FILES:
        source = (ROOT / relative).resolve()
        if theme_root not in source.parents or not source.is_file():
            continue
        archive.mkdir(parents=True, exist_ok=True)
        target = archive / source.name
        if target.exists():
            raise RuntimeError(f"Theme archive target already exists: {target}")
        shutil.move(str(source), str(target))
        rows.append({"source": str(source), "archive": str(target)})
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in-place", action="store_true",
                        help="Regenerate verified package folders without moving locked marketplace reference copies.")
    parser.add_argument("--only", action="append", default=[],
                        help="Rebuild only the plan with this numeric seed; may be supplied more than once.")
    args = parser.parse_args(argv)
    archived = [] if args.in_place else archive_legacy()
    archived_sources = [] if args.in_place else archive_legacy_sources()
    selected = [plan for plan in PLANS if not args.only or str(plan[3]) in set(args.only)]
    if not selected:
        raise SystemExit("No rebuild plans matched --only.")
    built = []
    for filename, title, subtitle, seed in selected:
        theme = THEMES / filename
        folder = build_word_search({"theme": theme, "title": title, "subtitle": subtitle, "seed": seed})
        built.append({"title": title, "theme": str(theme), "package": str(folder), "seed": seed})
    service = PublishingService(ROOT)
    service.sync_output_packages()
    for row in built:
        folder = Path(row["package"]).resolve()
        matches = [book for book in service.db.list_books()
                   if Path(str(book.get("package_path") or "")).resolve() == folder]
        if not matches:
            raise RuntimeError(f"Publishing Manager did not register {folder.name}")
        book = matches[0]
        row["book_id"] = book["book_id"]
        row["commercial_assessment"] = str(service.write_commercial_assessment(book["book_id"]))
        row["handoffs"] = []
        for marketplace in ("amazon", "etsy", "payhip", "barnes_noble", "website", "lulu", "ingram", "bookvault"):
            try:
                row["handoffs"].extend(service.prepare_many([book["book_id"]], [marketplace]))
            except (OSError, PermissionError) as exc:
                # A preview app can temporarily lock a copied reference PDF.
                # Do not lose the successful print build or other handoffs.
                row["handoffs"].append([book["book_id"], marketplace,
                                        f"Needs retry after closing the locked file: {exc}"])
    payload = {"created_at": datetime.now().isoformat(timespec="seconds"), "mode": "in_place" if args.in_place else "archive_and_replace",
               "archived_legacy": archived,
               "archived_legacy_sources": archived_sources,
               "retired_without_replacement": ["Vocabulary Adventures: Grade School"], "built": built}
    MANIFEST.parent.mkdir(exist_ok=True)
    MANIFEST.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
