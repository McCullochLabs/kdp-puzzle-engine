"""Build a small, quality-gated 50-puzzle Word Search release batch.

This is intentionally a production utility, not a shortcut around Book Studio.
Each candidate is drawn from one named Master Library pool, is checked by the
same production stop used by the UI, and then uses the Studio package method
to create its complete package and Publishing Center record.  Failed candidates
are removed from this batch's own temporary folder; existing themes and output
packages are never touched.
"""
from __future__ import annotations

import json
import argparse
import random
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import word_search_creator as studio


STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
THEME_ROOT = ROOT / "themes" / "Trending 50 Puzzle Releases"
OUTPUT_ROOT = ROOT / "out" / f"Trending 50 Puzzle Releases {STAMP}"
MASTER = ROOT / "word_banks" / "Guided_Builder_Master_Word_Bank.json"
PUZZLE_COUNT = 50
WORDS_PER_PUZZLE = 12
REQUIRED_WORDS = PUZZLE_COUNT * WORDS_PER_PUZZLE


BOOKS = (
    {
        "slug": "garden_discovery",
        "title": "Garden Discovery Word Search",
        "subtitle": "50 large-print puzzles for flower, plant and homegrown fun",
        "topic": "Gardening",
        # The raw Gardening pool is correctly divided between these two
        # canonical profile labels. Record both rather than claiming the old
        # duplicate label is a sufficient source identity.
        "source_topics": ("Gardening and Garden Life", "Homesteading"),
        "detected_topic": "Gardening",
        "palette": "spring-meadow",
        "difficulty": "Relaxing",
        "series": "Slade Puzzle Co. Garden Discovery Series",
    },
    {
        "slug": "cosmic_discovery",
        "title": "Cosmic Discovery Word Search",
        "subtitle": "50 large-print puzzles about space, planets and stargazing",
        "topic": "Space & Astronomy",
        "detected_topic": "Space & Astronomy",
        "palette": "starlight-indigo",
        "difficulty": "Standard",
        "series": "Slade Puzzle Co. Cosmic Discovery Series",
    },
    {
        "slug": "faithful_words",
        "title": "Faithful Words Word Search",
        "subtitle": "50 large-print puzzles for Bible themes, hope and encouragement",
        "topic": "Bible and Faith",
        "detected_topic": "Bible and Faith",
        "palette": "bible",
        "difficulty": "Relaxing",
        "series": "Slade Puzzle Co. Faithful Words Series",
    },
    {
        "slug": "road_trip_classics",
        "title": "Road Trip Classics Word Search",
        "subtitle": "50 large-print puzzles about cars, highways and open-road adventures",
        "topic": "Vehicles & Automotive",
        "detected_topic": "Vehicles & Automotive",
        "palette": "retro-diner",
        "difficulty": "Standard",
        "series": "Slade Puzzle Co. Road Trip Classics Series",
    },
    {
        "slug": "american_moments",
        "title": "American Moments Word Search",
        "subtitle": "50 large-print puzzles about history, people and places",
        "topic": "American History",
        "detected_topic": "American History",
        "palette": "usa",
        "difficulty": "Standard",
        "series": "Slade Puzzle Co. American Moments Series",
    },
)


def normalized(value: object) -> str:
    return re.sub(r"[^A-Z]", "", str(value).upper())


def clean_pool(values: list[object]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in values:
        word = normalized(raw)
        if not 3 <= len(word) <= 21 or word in seen:
            continue
        seen.add(word)
        result.append(word)
    return result


def candidate_theme(book: dict, master: dict) -> Path:
    topics = master.get("topics") if isinstance(master, dict) else {}
    pool = clean_pool(list((topics or {}).get(book["topic"], [])))
    if len(pool) < REQUIRED_WORDS:
        raise RuntimeError(f"{book['title']} has {len(pool)} usable words in its named source pool; {REQUIRED_WORDS} are required.")
    choice = studio.recommend_background_photo({"title": book["title"], "detected_topic": book["detected_topic"], "series": book["series"]})
    art = ROOT / str(choice.get("file") or "") if choice else None
    use_photo = bool(art and art.is_file() and studio.BackgroundAssetIndex().ledger_details(art))
    source = {
        "title": book["title"], "subtitle": book["subtitle"], "author": "Jordan M. Slade",
        "series": book["series"], "audience": "Adults and Teens",
        "palette": book["palette"], "recommended_palette": book["palette"],
        "cover_style": "photo" if use_photo else "retro",
        "recommended_cover_style": "photo" if use_photo else "retro",
        "cover_badge": "50 LARGE-PRINT PUZZLES • NO REPEATED WORDS",
        "cover_imprint": "Slade Puzzle Co.", "no_repeat_words": True,
        "difficulty_label": book["difficulty"], "detected_topic": book["detected_topic"],
        "source_word_bank": {"name": "Guided Builder Master Word Bank", "topics": list(book.get("source_topics") or [book["topic"]]), "selection_policy": "Direct named-topic pool; normalized, unique, 3–21 letters"},
        "clipart_search_terms": book["detected_topic"], "puzzles": [],
        "market_research_note": "Selected from current market research and only built after the existing named Master Library pool cleared the full 50 × 12 no-repeat requirement. Market interest is not a sales guarantee.",
    }
    if use_photo:
        source["cover_art_path"] = str(art.relative_to(ROOT))
        source["cover_art_focus"] = str(choice.get("focus") or "center")
    THEME_ROOT.mkdir(parents=True, exist_ok=True)
    path = THEME_ROOT / f"{book['slug']}_{STAMP}.json"
    for attempt in range(1, 51):
        ordered = list(pool)
        random.Random(f"trending-50|{book['slug']}|{STAMP}|{attempt}").shuffle(ordered)
        source["puzzles"] = [
            {"name": f"{book['detected_topic']} Puzzle {number:02d}", "words": ordered[(number - 1) * WORDS_PER_PUZZLE:number * WORDS_PER_PUZZLE]}
            for number in range(1, PUZZLE_COUNT + 1)
        ]
        path.write_text(json.dumps(source, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        errors, _warnings, _notes = studio.audit_theme(path, 881000 + attempt)
        if not errors:
            return path
    path.unlink(missing_ok=True)
    raise RuntimeError(f"{book['title']} could not produce a fully placeable 50-puzzle arrangement after 50 checked attempts.")


class _Status:
    def set(self, _message: str) -> None:
        pass


class _Button:
    def configure(self, **_kwargs) -> None:
        pass


class HeadlessStudioRunner:
    """Small adapter that invokes the exact UI package method without Tk."""
    _write_proof_bundle = staticmethod(studio.WordSearchCreator._write_proof_bundle)

    def __init__(self) -> None:
        self.status = _Status()
        self.generate_button = _Button()
        self.last_output = None
        self.last_wrap_preview = None
        self.result: tuple[bool, Path | None, str] | None = None

    def after(self, _delay: int, callback, *args) -> None:
        callback(*args)

    def _studio_package_finished(self, success: bool, target: Path | None, message: str) -> None:
        self.result = (success, target, message)


def build_package(theme: Path, book: dict, sequence: int) -> Path:
    data = json.loads(theme.read_text(encoding="utf-8-sig"))
    art = ROOT / str(data.get("cover_art_path") or "")
    use_photo = art.is_file() and studio.BackgroundAssetIndex().ledger_details(art)
    settings = {
        "theme": str(theme), "title": book["title"], "subtitle": book["subtitle"],
        "author": "Jordan M. Slade", "imprint": "Slade Puzzle Co.",
        "badge": "50 LARGE-PRINT PUZZLES • NO REPEATED WORDS", "difficulty": book["difficulty"],
        "palette": book["palette"], "style": "photo" if use_photo else "retro",
        "art": str(art) if use_photo else "", "art_focus": str(data.get("cover_art_focus") or "center"),
        "format_label": "LARGE PRINT", "signature_edition": False, "puzzle_count": PUZZLE_COUNT,
    }
    errors, warnings, _notes = studio.production_stop_errors(theme, 881100 + sequence, settings)
    if errors:
        raise RuntimeError("Production stop: " + " | ".join(errors))
    folder = OUTPUT_ROOT / f"{sequence:02d}_{book['slug']}"
    runner = HeadlessStudioRunner()
    studio.WordSearchCreator._run_studio_package(runner, settings, 881100 + sequence, folder, warnings)
    if not runner.result or not runner.result[0] or not folder.is_dir():
        raise RuntimeError((runner.result or (False, None, "No package result"))[2])
    return folder


def main() -> int:
    parser = argparse.ArgumentParser(description="Build one or all checked Trending 50 Puzzle releases.")
    parser.add_argument("--only", choices=tuple(book["slug"] for book in BOOKS), help="Build one named release only.")
    args = parser.parse_args()
    master = json.loads(MASTER.read_text(encoding="utf-8-sig"))
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=False)
    results: list[dict] = []
    selected = [book for book in BOOKS if not args.only or book["slug"] == args.only]
    for index, book in enumerate(selected, 1):
        theme = None
        folder = OUTPUT_ROOT / f"{index:02d}_{book['slug']}"
        try:
            theme = candidate_theme(book, master)
            package = build_package(theme, book, index)
            results.append({"title": book["title"], "theme": str(theme), "package": str(package), "status": "PASS"})
        except Exception as exc:
            # The folder is newly created by this utility and always lies under
            # this batch root.  Remove only its incomplete attempt.
            if folder.is_dir() and folder.resolve().is_relative_to(OUTPUT_ROOT.resolve()):
                shutil.rmtree(folder)
            if theme and theme.is_file():
                theme.unlink()
            results.append({"title": book["title"], "status": "BLOCKED", "reason": str(exc)})
    report = OUTPUT_ROOT / "BATCH_RESULT.json"
    report.write_text(json.dumps({"created_at": STAMP, "results": results}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(results, indent=2, ensure_ascii=False))
    return 0 if all(item["status"] == "PASS" for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
