"""Reusable validation and book-format helpers for Word Search Creator."""
from __future__ import annotations

import json
import random
from pathlib import Path

import wordsearch as puzzle_engine
from cover import PALETTES


VALID_COVER_STYLES = {"playful", "sunburst", "classic", "bold", "retro", "minimal", "gallery", "colorblock", "ticket", "halo", "stripe", "photo"}
# Themes created in earlier versions can store the friendly UI wording instead
# of the compact renderer key.  Both are supported by the live cover workflow,
# so the library audit must recognise both forms rather than reporting a false
# production stop.
COVER_STYLE_LABELS = {
    "Playful Illustrated": "playful", "Sunburst Poster": "sunburst",
    "Classic": "classic", "Bold Spotlight": "bold", "Retro Pop": "retro",
    "Minimal": "minimal", "Gallery Frame": "gallery", "Color Block": "colorblock",
    "Ticket Stub": "ticket", "Halo Spotlight": "halo", "Diagonal Stripe": "stripe",
    "Photo Hero": "photo",
}


def canonical_cover_style(value: object) -> str:
    """Return the renderer key for either a saved key or a friendly UI label."""
    style = str(value or "").strip()
    return COVER_STYLE_LABELS.get(style, style.casefold())


def recommended_us_paperback_price(page_count: int) -> tuple[float, float]:
    if page_count <= 90:
        price = 8.99
    elif page_count <= 130:
        price = 9.99
    elif page_count <= 180:
        price = 10.99
    else:
        price = 11.99
    print_cost = 1.00 + (page_count * 0.012)
    return price, max(0.0, (price * (0.60 if price >= 9.99 else 0.50)) - print_cost)


def book_format_label(data: dict) -> str:
    puzzles = data.get("puzzles", []) if isinstance(data, dict) else []
    largest = max((len(item.get("words", [])) for item in puzzles if isinstance(item, dict)), default=0)
    return "LARGE PRINT PUZZLES" if largest <= 12 else "WORD SEARCH PUZZLES"


def book_description(count: int, data: dict) -> str:
    if book_format_label(data) == "LARGE PRINT PUZZLES":
        return (f"Relax with {count} large print word search puzzles in a theme you'll love. "
                "Big, easy-to-read letters and complete solutions make every puzzle a pleasure to solve.")
    return (f"Relax with {count} themed word search puzzles in a collection you'll love. "
            "Clear grids and complete solutions make every puzzle a pleasure to solve.")


def audit_theme(path: Path, seed: int) -> tuple[list[str], list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    notes: list[str] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"Cannot read {path.name}: {exc}"], warnings, notes
    puzzles = data.get("puzzles") if isinstance(data, dict) else None
    if not isinstance(puzzles, list) or not puzzles:
        return ["This theme does not contain any puzzles."], warnings, notes
    random.seed(seed)
    names: set[str] = set()
    for number, puzzle in enumerate(puzzles, start=1):
        if not isinstance(puzzle, dict):
            errors.append(f"Puzzle {number} is not in the expected format."); continue
        name = str(puzzle.get("name", "")).strip() or f"Puzzle {number}"
        key = " ".join(name.upper().split())
        if key in names: errors.append(f"Puzzle {number} repeats the name '{name}'.")
        names.add(key)
        source = puzzle.get("words")
        if not isinstance(source, list) or not source:
            errors.append(f"{name}: it has no words."); continue
        if len(source) > 25: errors.append(f"{name}: it has {len(source)} words; the maximum is 25.")
        cleaned = puzzle_engine.clean_words(source)
        if len(cleaned) != len(source): errors.append(f"{name}: one or more words are blank or longer than 21 letters.")
        if len(cleaned) != len(set(cleaned)): errors.append(f"{name}: a word appears more than once.")
        if cleaned:
            _grid, _placements, placed = puzzle_engine.generate_puzzle(cleaned, N=puzzle_engine.grid_size_for(cleaned))
            if len(placed) != len(cleaned): errors.append(f"{name}: only {len(placed)} of {len(cleaned)} words could be placed.")
    notes.append(f"Checked {len(puzzles)} puzzle(s) using random seed {seed}.")
    return errors, warnings, notes


def _word_intelligence_notes(project_root: Path) -> list[str]:
    """Optional status notes for the word-intelligence layer.

    Reads only the small curated files so project checks stay instant even
    when the full word store is large. A missing layer is a gentle note,
    never a problem: the feature is additive and every other check stands
    on its own.
    """
    notes: list[str] = []
    state_dir = project_root / "word_banks" / "word_intelligence"
    if not state_dir.exists():
        notes.append("Word Intelligence: not built yet; open the Word Intelligence Center to start matching words to topics.")
        return notes
    links_path = state_dir / "approved_topic_links.json"
    try:
        payload = json.loads(links_path.read_text(encoding="utf-8-sig"))
        approved = sum(
            1 for topics in (payload.get("links") or {}).values()
            for info in topics.values()
            if isinstance(info, dict) and info.get("status") == "approved")
        if approved:
            notes.append(f"Word Intelligence: {approved} human-approved topic match(es) will be reused by bank rebuilds.")
        else:
            notes.append("Word Intelligence: no approved links saved yet.")
    except (OSError, json.JSONDecodeError):
        notes.append("Word Intelligence: approved-links file not written yet (dry runs and classifier suggestions are unaffected).")
    queue_path = state_dir / "review_queue.json"
    try:
        queue = json.loads(queue_path.read_text(encoding="utf-8-sig"))
        open_items = [i for i in (queue.get("items") or []) if isinstance(i, dict) and i.get("status") == "open"]
        if open_items:
            notes.append(f"Word Intelligence: {len(open_items)} suggestion(s) waiting in the review queue.")
    except (OSError, json.JSONDecodeError):
        pass
    return notes


def run_project_check(themes_dir: Path) -> tuple[list[str], list[str]]:
    problems: list[str] = []
    notes: list[str] = []
    # The library supports organized subfolders (for example States and Decades),
    # so a real project check must cover those too.  Archived books remain part of
    # the duplicate-safety history but are clearly identified in the report.
    files = sorted(themes_dir.rglob("*.json"))
    project_root = themes_dir.parent
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            problems.append(f"{path.name}: invalid JSON ({exc})."); continue
        if not isinstance(data.get("puzzles"), list):
            notes.append(f"{path.name}: series/setup file skipped."); continue
        if not str(data.get("title", "")).strip(): problems.append(f"{path.name}: missing title.")
        if not str(data.get("author", "")).strip(): problems.append(f"{path.name}: missing author.")
        palette = str(data.get("palette") or "")
        style = canonical_cover_style(data.get("cover_style"))
        if palette not in PALETTES: problems.append(f"{path.name}: unknown cover color family '{palette}'.")
        if style not in VALID_COVER_STYLES: problems.append(f"{path.name}: unknown cover layout '{style}'.")
        signature = data.get("signature_edition")
        if isinstance(signature, dict) and signature.get("enabled") and len(data["puzzles"]) < 100:
            notes.append(f"{path.name}: legacy Signature setting is treated as a standard edition because it has fewer than 100 puzzles.")
        book_words: set[str] = set()
        repeats: set[str] = set()
        for puzzle in data["puzzles"]:
            if not isinstance(puzzle, dict) or not puzzle.get("name") or not puzzle.get("words"):
                problems.append(f"{path.name}: incomplete puzzle data."); break
            for word in puzzle.get("words", []):
                clean = "".join(char for char in str(word).upper() if char.isalpha())
                if clean in book_words: repeats.add(clean)
                book_words.add(clean)
        if repeats:
            examples = ", ".join(sorted(repeats)[:5])
            problems.append(f"{path.name}: repeats {len(repeats)} word(s) across puzzles ({examples}).")
    active = sum(1 for path in files if "Used Themes" not in path.parts)
    archived = len(files) - active
    master = project_root / "word_banks" / "Guided_Builder_Master_Word_Bank.json"
    try:
        library = json.loads(master.read_text(encoding="utf-8-sig"))
        if not isinstance(library.get("topics"), dict) or not isinstance(library.get("word_profiles"), dict):
            problems.append("Master Library: missing topics or word cross-links.")
        else:
            notes.append(f"Master Library: {library.get('total_unique_words', 0)} clean words across {len(library['topics'])} topic choices.")
    except (OSError, json.JSONDecodeError) as exc:
        problems.append(f"Master Library: cannot be read ({exc}).")
    photo_library = project_root / "cover_assets" / "background_photo_library.json"
    try:
        photo_data = json.loads(photo_library.read_text(encoding="utf-8-sig"))
        missing_photos: list[str] = []
        for item in photo_data.get("items", []) if isinstance(photo_data, dict) else []:
            paths = [item.get("file")] if isinstance(item, dict) and item.get("file") else item.get("files", []) if isinstance(item, dict) else []
            for asset in paths:
                if asset and not (project_root / str(asset)).exists(): missing_photos.append(str(asset))
        if missing_photos: problems.append("Photo Library: missing " + ", ".join(missing_photos[:5]) + ("…" if len(missing_photos) > 5 else ""))
        else: notes.append(f"Photo Library: {len(photo_data.get('items', []))} cover-background choices verified.")
    except (OSError, json.JSONDecodeError) as exc:
        problems.append(f"Photo Library: cannot be read ({exc}).")
    for required in ("Start Word Search Creator.bat", "launch_word_search_creator.py", "word_search_creator.py", "wordsearch.py", "cover.py", "wrap_cover.py"):
        if not (project_root / required).exists(): problems.append(f"Required app file is missing: {required}.")
    try:
        recent = json.loads((project_root / "recent_themes.json").read_text(encoding="utf-8-sig"))
        stale_recent = [str(item) for item in recent if not (project_root / str(item)).exists()] if isinstance(recent, list) else []
        if stale_recent: notes.append(f"Recent books list: {len(stale_recent)} old shortcut(s) will be ignored until those themes are opened again.")
    except (OSError, json.JSONDecodeError):
        notes.append("Recent books list is unavailable; the app will rebuild it as you open themes.")
    notes.extend(_word_intelligence_notes(project_root))
    notes.insert(0, f"Checked {len(files)} JSON file(s): {active} active and {archived} archived.")
    return problems, notes
