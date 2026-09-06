"""Create protected, full KDP-ready packages for the discussed collections.

Output folders are new and one package per theme.  Existing packages are
never replaced: if a destination exists, this program reports it and moves on.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from pypdf import PdfReader

import word_search_creator as studio


APP_DIR = Path(__file__).resolve().parent
OUT_DIR = APP_DIR / "out" / "Discussed Book Packages"
THEME_GROUPS = [
    ("Market Opportunity Collection", APP_DIR / "themes" / "Market Opportunity Collection"),
    ("Vocabulary Ladder Collection", APP_DIR / "themes" / "Vocabulary Ladder Collection"),
    ("National Parks Collection", APP_DIR / "themes", "national_parks_*.json"),
]
ALLOWED_STYLES = {"classic", "photo", "playful", "sunburst", "bold", "retro", "minimal", "gallery", "colorblock", "ticket", "halo", "stripe"}


def slug(value: str) -> str:
    return "".join(character.lower() if character.isalnum() else "_" for character in value).strip("_")


def run(args: list[str]) -> None:
    subprocess.run([sys.executable, *args], cwd=APP_DIR, check=True)


def listing_text(data: dict[str, object], pages: int) -> str:
    title = str(data["title"])
    subtitle = str(data.get("subtitle", ""))
    puzzle_count = len(data.get("puzzles", []))
    difficulty = str(data.get("difficulty_label", "Standard"))
    return f"""# {title}

**Title:** {title}
**Subtitle:** {subtitle}
**Author:** Slade Puzzles
**Puzzles:** {puzzle_count}
**Difficulty:** {difficulty}
**Interior pages:** {pages}
**Trim:** 8.5 × 11 in · black and white · white paper · no bleed

## Files

- `interior.pdf` — KDP manuscript
- `cover.png` — front-cover image
- `wrap.pdf` — KDP full-cover wrap
- `PRECHECK.txt` — package quality report

## Suggested listing notes

Large-print word searches with clear grids, complete solutions, and no repeated words within this book.
Review the title, cover, metadata, keywords, categories, and price in KDP before publishing.
"""


def build(theme_path: Path, series_name: str, number: int) -> tuple[bool, str]:
    data = json.loads(theme_path.read_text(encoding="utf-8-sig"))
    title = str(data["title"])
    destination = OUT_DIR / series_name / f"{number:02d}_{slug(title)}"
    if destination.exists():
        return False, f"SKIPPED existing package: {destination.name}"
    destination.mkdir(parents=True, exist_ok=False)
    interior = destination / "interior.pdf"
    front = destination / "cover.png"
    wrap = destination / "wrap.pdf"
    try:
        run(["wordsearch.py", "--themes", str(theme_path), "--out", str(interior), "--seed", str(240100 + number)])
        pages = len(PdfReader(interior).pages)
        # Route cover art through the same approved asset pipeline used by the
        # GUI and other batch builders.  This selects the best eligible
        # generated/approved background for the book's topic, or reports why a
        # fallback is needed.
        choice = studio.recommend_background_photo(data)
        if choice:
            art = APP_DIR / str(choice["file"])
            style = "photo"
            cover_art = str(art)
            art_focus = str(choice.get("focus") or "center")
        else:
            raise RuntimeError(
                "COVER ART REQUIRED - no approved topic-matched background is available. "
                "Approve a suitable asset before building this book."
            )
        cover_command = [
            "cover.py", "--title", title, "--subtitle", str(data.get("subtitle", "")),
            "--author", "Slade Puzzles", "--badge", str(data.get("cover_badge", f"{len(data.get('puzzles', []))} LARGE-PRINT PUZZLES")),
            "--difficulty", str(data.get("difficulty_label", "Standard")),
            "--palette", str(data.get("palette", "ocean-breeze")), "--style", style,
            "--theme-file", str(theme_path), "--out", str(front),
        ]
        cover_command.extend(["--art", cover_art, "--art-focus", art_focus])
        run(cover_command)
        back = (f"Relax with {len(data.get('puzzles', []))} large-print word search puzzles in a theme you will love.\n\n"
                "Clear grids, complete solutions, and no repeated words within this book make every puzzle a fresh challenge.")
        run(["wrap_cover.py", "--front", str(front), "--pages", str(pages), "--palette", str(data.get("palette", "ocean-breeze")),
             "--title", title, "--author", "Slade Puzzles", "--back", back, "--out", str(wrap)])
        (destination / "LISTING.md").write_text(listing_text(data, pages), encoding="utf-8")
        import preflight
        ok, report = preflight.preflight(str(destination))
        (destination / "PRECHECK.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
        if not ok:
            return False, f"FAILED preflight: {destination.name}"
        return True, f"READY: {destination.name}"
    except Exception as error:
        (destination / "BUILD_ERROR.txt").write_text(str(error) + "\n", encoding="utf-8")
        return False, f"FAILED build: {destination.name} ({error})"


def files_for(group: tuple[object, ...]) -> list[Path]:
    _, folder, *pattern = group
    return sorted(Path(folder).rglob(pattern[0] if pattern else "*.json"))


def main() -> None:
    ready = failed = skipped = 0
    for group in THEME_GROUPS:
        name = str(group[0])
        files = files_for(group)
        print(f"\n== {name}: {len(files)} package(s) ==")
        for number, path in enumerate(files, start=1):
            ok, message = build(path, name, number)
            print(message)
            if message.startswith("SKIPPED"):
                skipped += 1
            elif ok:
                ready += 1
            else:
                failed += 1
    print(f"\nFinished — ready: {ready}; skipped: {skipped}; failed: {failed}")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
