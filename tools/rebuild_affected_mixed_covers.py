"""Regenerate only Mixed Brain Games covers after a layout-engine repair.

This intentionally leaves interiors, puzzle data, answers, identities, and
listing copy untouched.  It records hashes before/after so a cover-only run
can be audited rather than assumed safe.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def rebuild(folder: Path, force: bool = False) -> dict:
    from background_generation.index import BackgroundAssetIndex
    from publishing.production_intelligence import marketplace_assets, mark_cover_dependents_stale
    from puzzle_book_studio import cover_spec

    record_path = folder / "04_REVIEW_AND_RECORDS" / "PACKAGE_SOURCE_RECORD.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    if record.get("puzzle_type") != "Mixed Brain Games":
        return {"package": str(folder), "status": "SKIPPED"}
    if not force and (folder / "04_REVIEW_AND_RECORDS" / "COVER_DEPENDENCY_REFRESH_NEEDED.txt").is_file():
        return {"package": str(folder), "status": "ALREADY_REBUILT"}
    interior = folder / "01_PRINT_UPLOADS" / "interior.pdf"
    before_hash = sha256(interior)
    title = str(record["title"])
    seed = int(hashlib.sha1(title.encode("utf-8")).hexdigest()[:8], 16)
    art_rel, palette, style = cover_spec("Mixed Brain Games", str(record.get("theme") or "General Starter"), seed)
    if not art_rel:
        return {"package": str(folder), "status": "BLOCKED", "reason": "No approved topic-matched background exists."}
    art = ROOT / art_rel
    asset = BackgroundAssetIndex().ledger_details(art)
    if not asset or not BackgroundAssetIndex().production_selectable(asset):
        return {"package": str(folder), "status": "BLOCKED", "reason": "Background provenance is not production-approved."}
    front = folder / "03_PREVIEWS" / "front_cover.png"
    wrap = folder / "01_PRINT_UPLOADS" / "kdp_full_wrap.pdf"
    preview = folder / "03_PREVIEWS" / "kdp_full_wrap_preview.png"
    count, pages = int(record.get("puzzle_count") or 0), int(record.get("pages") or 0)
    badge = "SUDOKU • CODES • WORD GAMES"
    subprocess.run([
        sys.executable, str(ROOT / "cover.py"), "--title", title,
        "--subtitle", str(record.get("subtitle") or ""), "--author", str(record.get("author") or ""),
        "--badge", badge, "--puzzle-count", str(count), "--difficulty", str(record.get("difficulty") or "Mixed"),
        "--format-label", "MIXED BRAIN GAMES", "--puzzle-type", "Mixed Brain Games",
        "--palette", palette, "--style", style, "--art", str(art), "--out", str(front),
    ], check=True, cwd=ROOT)
    back = (f"Enjoy {count} satisfying Sudoku, Cryptogram, and word-and-trivia challenges, "
            "organized in clear sections with complete answers for every game type.")
    subprocess.run([
        sys.executable, str(ROOT / "wrap_cover.py"), "--front", str(front), "--pages", str(pages),
        "--palette", palette, "--title", title, "--author", str(record.get("author") or ""),
        "--back", back, "--back-heading", "A VARIETY OF GOOD PUZZLES", "--out", str(wrap),
        "--preview-out", str(preview),
    ], check=True, cwd=ROOT)
    marketplace_assets(front)
    record.update({"palette": palette, "cover_style": style, "cover_art": art_rel})
    record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    mark_cover_dependents_stale(folder, "Mixed Brain Games cover was regenerated after the central-panel layout was retired.")
    after_hash = sha256(interior)
    return {"package": str(folder), "status": "REBUILT", "style": style, "art": art_rel,
            "interior_hash_before": before_hash, "interior_hash_after": after_hash,
            "interior_unchanged": before_hash == after_hash}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", default="", help="optional folder-name fragment for a targeted retry")
    parser.add_argument("--force", action="store_true", help="rebuild a previously marked cover after changing cover logic")
    args = parser.parse_args()
    rows = [rebuild(path, args.force) for path in sorted(OUT.iterdir()) if path.is_dir()
            and args.package.casefold() in path.name.casefold()
            and (path / "04_REVIEW_AND_RECORDS" / "PACKAGE_SOURCE_RECORD.json").is_file()]
    report = ROOT / "reports" / "COVER_ONLY_MIXED_REBUILD_REPORT.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
