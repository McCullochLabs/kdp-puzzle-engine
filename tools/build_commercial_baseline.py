"""Build ten real commercial-release candidates through established creators.

This is deliberately a production script, not a sample generator.  It uses
the same Word Search and Puzzle Book package paths the desktop UI calls, then
registers and prepares local marketplace handoffs.  It never uploads or
publishes anything externally.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw


PROJECT = Path(__file__).resolve().parents[1]
OUT = PROJECT / "out"
AUTHOR = "Jordan M. Slade"
MARKETS = ("amazon", "barnes_noble", "payhip", "lulu")
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

WORD_SEARCHES = (
    {
        "theme": PROJECT / "themes" / "Launch Collection" / "Verified Release Candidates" / "classic_cars_road_trips.json",
        "title": "Classic Cars and Road Trips Word Search",
        "subtitle": "48 large-print puzzles for vintage vehicle fans and open-road dreamers",
        "seed": 6101,
    },
    {
        "theme": PROJECT / "themes" / "Vocabulary Ladder Collection" / "vocabulary_adventures_grade_school.json",
        "title": "Vocabulary Adventures: Grade School",
        "subtitle": "48 large-print vocabulary word searches for stronger reading and word confidence",
        "seed": 6102,
    },
)

PUZZLE_BOOKS = (
    ("Sudoku", "Stargazer Symbols Sudoku", "60 number, letter and shape logic puzzles for calm space lovers", 60, "Mixed", 6201, "Space & Astronomy"),
    ("Sudoku", "Garden Path Symbols Sudoku", "60 number, letter and shape logic puzzles for a quiet garden break", 60, "Mixed", 6202, "Garden & Growing"),
    ("Cryptogram", "Celestial Cipher Challenge", "60 space and astronomy code-breaking puzzles with complete solutions", 60, "Mixed", 6203, "Space & Astronomy"),
    ("Cryptogram", "American Heritage Cipher Challenge", "60 history-inspired cryptograms for thoughtful code breakers", 60, "Mixed", 6204, "History & Heritage"),
    ("Word Scramble + Trivia", "Great American Road Trip Scramble and Trivia", "60 travel word scrambles and quick facts for adventurous puzzle fans", 60, "Mixed", 6205, "Travel & Adventure"),
    ("Word Scramble + Trivia", "Kitchen Table Scramble and Trivia", "60 food and home word games with friendly trivia", 60, "Mixed", 6206, "Food & Home"),
    ("Mixed Brain Games", "Wild Places Brain Games Collection", "60 nature-inspired Sudoku, codes, scrambles and trivia challenges", 60, "Mixed", 6207, "Nature & Outdoors"),
    ("Mixed Brain Games", "Study Break Brain Games Collection", "60 school and vocabulary Sudoku, codes, scrambles and trivia challenges", 60, "Mixed", 6208, "School & Vocabulary"),
)


class _Value:
    def set(self, _value):
        return None


class _Button:
    def configure(self, **_kwargs):
        return None


def build_word_search(plan: dict) -> Path:
    import word_search_creator as studio
    errors, _warnings, _notes = studio.quality_gate(plan["theme"], plan["seed"])
    if errors:
        raise RuntimeError(f"{plan['theme'].name} is no longer eligible: {' | '.join(errors)}")
    data = json.loads(plan["theme"].read_text(encoding="utf-8-sig"))
    folder = OUT / f"commercial_baseline_{plan['seed']}_{studio.WordSearchCreator._safe_filename(plan['title']).lower()}"
    from background_generation.index import BackgroundAssetIndex
    cover_data = {**data, "title": plan["title"], "subtitle": plan["subtitle"],
                  "_theme_path": str(plan["theme"]), "_creation_route": "Word Search"}
    # The shared router chooses only among the strongest equally relevant
    # assets.  Indexing the entire candidate list by seed could select a
    # much weaker, unrelated image even though a perfect topic match existed.
    choice = studio.recommend_background_photo(cover_data)
    # A correctly indexed file is still visually checked for this flagship
    # vehicle title.  Keep the explicit road-trip asset rather than allowing
    # a broad topic match to select an unrelated ocean image.
    if plan["title"] == "Classic Cars and Road Trips Word Search":
        choices = BackgroundAssetIndex().approved_choices(" ".join((plan["title"], str(data.get("detected_topic") or ""))))
        choice = next((item for item in choices if str(item.get("file") or "").endswith("vehicles_vintage_v3.png")), choice)
    art = PROJECT / str(choice.get("file") or "") if choice else None
    if not art or not art.is_file():
        raise RuntimeError(f"No approved matched cover image is available for {plan['title']}.")
    settings = {
        "theme": str(plan["theme"]), "title": plan["title"], "subtitle": plan["subtitle"], "author": AUTHOR,
        "badge": f"INCLUDES {len(data.get('puzzles') or [])} PUZZLES",
        "puzzle_count": len(data.get("puzzles") or []), "difficulty": studio.puzzle_difficulty_label(data),
        "format_label": "LARGE PRINT" if studio.book_format_label(data) == "LARGE PRINT PUZZLES" else "WORD SEARCH",
        "palette": studio.photo_choice_palette(choice, str(data.get("palette") or "nature")), "style": "photo",
        "art": str(art), "art_focus": str(choice.get("focus") or "center"), "signature_edition": False,
        "archive_after_package": False,
    }
    outcome: dict = {}
    runner = object.__new__(studio.WordSearchCreator)
    runner.status = _Value(); runner.generate_button = _Button(); runner.open_button = _Button()
    runner.after = lambda _delay, callback, *args: callback(*args)
    runner._write_proof_bundle = studio.WordSearchCreator._write_proof_bundle
    runner._studio_package_finished = lambda success, target, message: outcome.update(success=success, target=target, message=message)
    runner._load_theme_list = lambda: None
    runner._run_studio_package(settings, plan["seed"], folder)
    if not outcome.get("success"):
        raise RuntimeError(outcome.get("message") or f"Word Search build failed for {plan['title']}")
    return folder


def build_puzzle_book(plan: tuple) -> Path:
    import puzzle_book_studio as studio
    kind, title, subtitle, count, difficulty, seed, theme = plan
    return studio.create_package(kind, title, subtitle, AUTHOR, count, difficulty, seed, theme)


def build_contact_sheet(folders: list[Path]) -> Path:
    cells = []
    for folder in folders:
        from publishing.package_layout import package_file
        cover = package_file(folder, "front_cover.png")
        if cover.is_file():
            with Image.open(cover).convert("RGB") as image:
                image.thumbnail((290, 420), Image.Resampling.LANCZOS)
                cells.append((folder.name, image.copy()))
    width, cell_h = 960, 500
    sheet = Image.new("RGB", (width, ((len(cells) + 2) // 3) * cell_h + 90), "#101418")
    draw = ImageDraw.Draw(sheet)
    draw.text((28, 24), "NEW COMMERCIAL BASELINE — COVER CONTACT SHEET", fill="white")
    for index, (name, cover) in enumerate(cells):
        x, y = 25 + (index % 3) * 315, 75 + (index // 3) * cell_h
        sheet.paste(cover, (x + (290 - cover.width) // 2, y))
        draw.text((x, y + 430), name[:44], fill="#d9f5ee")
    target = PROJECT / "reports" / "NEW_COMMERCIAL_BASELINE_COVER_CONTACT_SHEET.png"
    target.parent.mkdir(exist_ok=True)
    sheet.save(target)
    return target


def main() -> None:
    OUT.mkdir(exist_ok=True)
    built: list[Path] = []
    for plan in WORD_SEARCHES:
        built.append(build_word_search(plan))
    for plan in PUZZLE_BOOKS:
        built.append(build_puzzle_book(plan))

    from publishing import PublishingService
    service = PublishingService(PROJECT)
    service.sync_output_packages()
    records = []
    for folder in built:
        matches = [book for book in service.db.list_books() if Path(str(book.get("package_path") or "")).resolve() == folder.resolve()]
        if not matches:
            raise RuntimeError(f"Publishing Center did not register {folder.name}.")
        book = matches[0]
        report_path = service.write_commercial_assessment(book["book_id"])
        handoffs = service.prepare_many([book["book_id"]], list(MARKETS))
        records.append({"title": book["metadata"].get("title"), "book_id": book["book_id"], "package": str(folder), "commercial_report": str(report_path), "handoffs": handoffs})
    contact = build_contact_sheet(built)
    matrix = PROJECT / "reports" / "NEW_PRODUCTION_CATALOG_MATRIX.txt"
    manifest = PROJECT / "reports" / "COMMERCIAL_BASELINE_MANIFEST.json"
    lines = ["NEW PRODUCTION CATALOG MATRIX", "=" * 72, ""]
    for row in records:
        lines += [row["title"], f"  Package: {row['package']}", f"  Commercial review: {row['commercial_report']}", "  Local marketplace handoffs:"]
        lines += [f"    - {market}: {result}" for _book, market, result in row["handoffs"]]
    matrix.write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest.write_text(json.dumps({"created_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"), "packages": records}, indent=2), encoding="utf-8")
    print(json.dumps({"built": records, "contact_sheet": str(contact), "matrix": str(matrix), "manifest": str(manifest)}, indent=2))


if __name__ == "__main__":
    main()
