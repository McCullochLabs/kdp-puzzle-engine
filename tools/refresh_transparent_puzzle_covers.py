"""Audit every active output cover and refresh card-free puzzle motifs.

Word Search covers are audited but left unchanged because their renderer does
not use the opaque non-word-search sample card. All other package covers,
wraps, proofs, master files, and marketplace handoffs are refreshed in place.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

from PIL import Image, ImageDraw
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
sys.path.insert(0, str(ROOT))

from background_generation.index import BackgroundAssetIndex
from publishing import PublishingService
from publishing.package_layout import package_file, release_contract
from publishing.production_intelligence import finalize_package

MARKETS = ("amazon", "etsy", "payhip", "website", "lulu", "bookvault", "barnes_noble", "ingram")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def back_copy(kind: str, count: int, theme: str) -> tuple[str, str]:
    if kind == "Sudoku":
        return "A QUIET PUZZLE RITUAL", f"Settle in with {count} number, letter, and shape Sudoku puzzles. Every grid has one verified solution, clear large-format pages, and a complete answer section for relaxing, satisfying solving."
    if kind == "Cryptogram":
        return "A SATISFYING CODE BREAK", f"Decode {count} themed cryptograms inspired by {theme}. Clear pages and complete solutions make every solved message a rewarding screen-free break."
    if kind == "Word Scramble + Trivia":
        return "A CURIOUS BRAIN BREAK", f"Enjoy {count} lively word scrambles paired with approachable themed trivia. Clear pages and a complete answer key make it easy to play for a few minutes or settle in longer."
    return "A VARIETY OF GOOD PUZZLES", f"Enjoy {count} satisfying Sudoku, Cryptogram, and word-scramble challenges with fact clues, organized in clear sections with complete answers for every game type."


def active_packages() -> list[Path]:
    return sorted({path.parent.parent for path in OUT.rglob("PACKAGE_SOURCE_RECORD.json")
                   if "_recovery_archive" not in {part.casefold() for part in path.parts}
                   and path.parent.name == "04_REVIEW_AND_RECORDS"})


def refresh(folder: Path, backup_root: Path, *, art_override: str = "", force: bool = False) -> dict:
    record_path = package_file(folder, "PACKAGE_SOURCE_RECORD.json")
    record = json.loads(record_path.read_text(encoding="utf-8"))
    kind = str(record.get("puzzle_type") or record.get("cover_puzzle_type") or "Word Search")
    front = package_file(folder, "front_cover.png")
    wrap = package_file(folder, "kdp_full_wrap.pdf")
    preview = package_file(folder, "kdp_full_wrap_preview.png")
    interior = package_file(folder, "interior.pdf")
    row = {"title": str(record.get("title") or folder.name), "puzzle_type": kind, "package": str(folder)}
    if not all(path.is_file() for path in (front, wrap, interior)):
        return {**row, "status": "BLOCKED", "reason": "A required cover, wrap, or interior file is missing."}
    row["interior_sha256_before"] = sha256(interior)
    if kind.casefold().replace("_", " ") == "word search":
        with Image.open(front) as image:
            row.update({"status": "AUDITED - NO OPAQUE SAMPLE CARD ROUTE", "dimensions": list(image.size)})
        return row
    if record.get("cover_visual_revision") == "transparent-puzzle-motif-v1" and not force and not art_override:
        contract = release_contract(folder)
        return {**row, "status": "PASS" if contract["ready"] else "BLOCKED",
                "release_ready": contract["ready"], "blockers": contract["missing"],
                "already_refreshed": True, "interior_unchanged": True}

    if art_override:
        if Path(art_override).name != art_override:
            return {**row, "status": "BLOCKED", "reason": "Art override must be an approved background filename, not a path."}
        art = ROOT / "cover_assets" / "background_photos" / art_override
    else:
        art_raw = str(record.get("cover_art") or record.get("cover_art_name") or "")
        art = Path(art_raw)
        if not art.is_absolute():
            art = ROOT / art
    index = BackgroundAssetIndex()
    asset = index.ledger_details(art)
    if not asset:
        return {**row, "status": "BLOCKED", "reason": "Recorded background is not production-approved."}

    backup = backup_root / folder.name
    backup.mkdir(parents=True, exist_ok=True)
    for source in (front, wrap, preview, record_path):
        if source.is_file():
            shutil.copy2(source, backup / source.name)

    title, subtitle = row["title"], str(record.get("subtitle") or "")
    author = str(record.get("author") or "Jordan M. Slade")
    count = int(record.get("puzzle_count") or 0)
    pages = len(PdfReader(str(interior)).pages)
    palette = str(record.get("palette") or asset.get("palette") or "midnight-gold")
    style = "photo"
    badge = "NUMBER • LETTER • SHAPE GAMES" if kind == "Sudoku" else "SUDOKU • CODES • WORD GAMES" if kind == "Mixed Brain Games" else f"INCLUDES {count} PUZZLES"
    subprocess.run([
        sys.executable, str(ROOT / "cover.py"), "--title", title, "--subtitle", subtitle,
        "--author", author, "--badge", badge, "--puzzle-count", str(count),
        "--difficulty", str(record.get("difficulty") or "Standard"), "--format-label", kind.upper(),
        "--puzzle-type", kind, "--palette", palette, "--style", style, "--art", str(art),
        "--art-focus", str(asset.get("focus") or "center"),
        "--puzzle-preview-position", str(asset.get("puzzle_preview_position") or "center"),
        "--out", str(front),
    ], check=True, cwd=ROOT)
    heading, paragraph = back_copy(kind, count, str(record.get("theme") or "the selected theme"))
    subprocess.run([
        sys.executable, str(ROOT / "wrap_cover.py"), "--front", str(front), "--pages", str(pages),
        "--palette", palette, "--title", title, "--author", author, "--back", paragraph,
        "--back-heading", heading, "--puzzle-type", kind, "--puzzle-count", str(count),
        "--theme", str(record.get("theme") or ""), "--out", str(wrap),
        "--preview-out", str(preview),
    ], check=True, cwd=ROOT)
    relative_art = str(art.relative_to(ROOT))
    record.update({"cover_style": style, "cover_visual_revision": "transparent-puzzle-motif-v1",
                   "cover_refreshed": datetime.now().isoformat(timespec="seconds"),
                   "cover_art": str(art), "cover_art_name": relative_art,
                   "cover_art_id": asset.get("asset_id", ""),
                   "cover_art_sha256": asset.get("sha256", ""),
                   "cover_art_approval_revision": asset.get("approval_revision") or asset.get("updated_at") or "",
                   "cover_art_approval_state": asset.get("approval_state") or "approved",
                   "cover_art_provenance": asset.get("provenance") or {}})
    record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    source = {**record, "detected_topic": record.get("theme"), "puzzles": []}
    final = finalize_package(ROOT, folder, source, title, subtitle, pages)
    row.update({"status": "PASS" if final["ready"] else "BLOCKED", "release_ready": final["ready"],
                "blockers": final["blockers"], "attention": final["attention_required"],
                "interior_sha256_after": sha256(interior),
                "interior_unchanged": row["interior_sha256_before"] == sha256(interior)})
    return row


def contact_sheet(packages: list[Path], filename: str, *, wraps: bool = False) -> Path:
    cells = []
    for folder in packages:
        front = package_file(folder, "kdp_full_wrap_preview.png" if wraps else "front_cover.png")
        if front.is_file():
            with Image.open(front).convert("RGB") as image:
                image.thumbnail((220, 285), Image.Resampling.LANCZOS)
                cells.append((folder.name, image.copy()))
    columns, cell_w, cell_h = 5, 240, 340
    rows = (len(cells) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * cell_w + 30, rows * cell_h + 70), "#101418")
    draw = ImageDraw.Draw(sheet)
    draw.text((20, 20), "ACTIVE OUT FOLDER - " + ("FULL WRAP" if wraps else "FRONT COVER") + " AUDIT", fill="white")
    for index, (name, cover) in enumerate(cells):
        x, y = 15 + (index % columns) * cell_w, 58 + (index // columns) * cell_h
        sheet.paste(cover, (x + (220 - cover.width) // 2, y))
        draw.text((x, y + 290), name[:34], fill="#d9f5ee")
    target = ROOT / "reports" / filename
    sheet.save(target)
    return target


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", default="", help="Optional active package-folder fragment.")
    parser.add_argument("--art", default="", help="Approved background filename for one targeted package.")
    parser.add_argument("--force", action="store_true", help="Refresh even when the transparent-motif revision is current.")
    args = parser.parse_args(argv)
    packages = [path for path in active_packages() if args.package.casefold() in path.name.casefold()]
    if args.art and len(packages) != 1:
        raise SystemExit("--art requires --package to match exactly one active package.")
    backup = ROOT / "backups" / f"cover_refresh_{datetime.now():%Y%m%d_%H%M%S}"
    results = [refresh(folder, backup, art_override=args.art, force=args.force) for folder in packages]
    if not backup.is_dir() or not any(backup.iterdir()):
        if backup.is_dir():
            backup.rmdir()
        prior_backups = [path for path in (ROOT / "backups").glob("cover_refresh_*") if path.is_dir() and any(path.iterdir())]
        if prior_backups:
            backup = max(prior_backups, key=lambda path: path.stat().st_mtime)
    service = PublishingService(ROOT)
    service.sync_output_packages()
    by_path = {Path(str(book.get("package_path") or "")).resolve(): book for book in service.db.list_books()}
    for result in results:
        if result["status"] != "PASS":
            continue
        book = by_path.get(Path(result["package"]).resolve())
        if not book:
            result["status"] = "BLOCKED"; result["reason"] = "Publishing Manager did not recognize refreshed package."
            continue
        # Finalize_package already refreshes the shared buyer-facing image set
        # and MASTER_RELEASE_PACKAGE. Avoid re-running unrelated listing AI or
        # recopying large interiors merely because the cover styling changed.
        result["cover_dependent_assets"] = "Refreshed in previews and master release package"
    sheet = contact_sheet(packages, "ACTIVE_OUT_COVER_AUDIT_CONTACT_SHEET.png")
    wrap_sheet = contact_sheet(packages, "ACTIVE_OUT_WRAP_AUDIT_CONTACT_SHEET.png", wraps=True)
    failures = [row for row in results if row["status"] == "BLOCKED"]
    report = ROOT / "reports" / "ACTIVE_OUT_COVER_AUDIT.json"
    report.write_text(json.dumps({"created_at": datetime.now().isoformat(timespec="seconds"),
                                  "packages_audited": len(results),
                                  "packages_refreshed": sum(row["status"] == "PASS" for row in results),
                                  "word_search_covers_audited": sum(row["status"].startswith("AUDITED") for row in results),
                                  "failures": failures, "results": results,
                                  "contact_sheet": str(sheet), "wrap_contact_sheet": str(wrap_sheet),
                                  "backup": str(backup)}, indent=2), encoding="utf-8")
    print(json.dumps({"audited": len(results), "refreshed": sum(row["status"] == "PASS" for row in results),
                      "word_search_audited": sum(row["status"].startswith("AUDITED") for row in results),
                      "failures": len(failures), "report": str(report), "contact_sheet": str(sheet), "wrap_contact_sheet": str(wrap_sheet),
                      "backup": str(backup)}, indent=2))
    if failures:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
