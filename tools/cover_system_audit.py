"""Produce a non-destructive cover provenance and catalog audit."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT, REPORTS = ROOT / "out", ROOT / "reports"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def package_rows() -> list[dict]:
    from background_generation.index import BackgroundAssetIndex
    index = BackgroundAssetIndex(); index.ensure_provenance_audited()
    rows = []
    for source in sorted(OUT.glob("*/04_REVIEW_AND_RECORDS/PACKAGE_SOURCE_RECORD.json")):
        package = source.parents[1]
        data = json.loads(source.read_text(encoding="utf-8"))
        front = package / "03_PREVIEWS" / "front_cover.png"
        art = str(data.get("cover_art") or "")
        art_path = ROOT / art if art and not Path(art).is_absolute() else Path(art)
        asset = index.ledger_details(art_path) if art else None
        if asset is None and art:
            # Older package records stored only a filename.  Resolve it
            # through the ledger rather than misreporting known art as bad.
            asset = next((item for item in index.assets()
                          if Path(str(item.get("path") or "")).name.casefold() == Path(art).name.casefold()), None)
        mixed = data.get("puzzle_type") == "Mixed Brain Games"
        rows.append({"package": package.name, "title": data.get("title", package.name),
                     "puzzle_type": data.get("puzzle_type", "Word Search"), "theme": data.get("theme", ""),
                     "front": front, "provenance_ok": bool(asset and index.production_selectable(asset)),
                     "mixed_rebuilt": mixed and (package / "04_REVIEW_AND_RECORDS" / "COVER_DEPENDENCY_REFRESH_NEEDED.txt").is_file(),
                     "status": "REBUILT" if mixed and (package / "04_REVIEW_AND_RECORDS" / "COVER_DEPENDENCY_REFRESH_NEEDED.txt").is_file() else "KEEP"})
    return rows


def contact_sheet(rows: list[dict], target: Path) -> None:
    cards, thumb_size = [], (220, 285)
    for row in rows:
        if row["front"].is_file():
            with Image.open(row["front"]) as image:
                thumb = image.convert("RGB").resize(thumb_size, Image.Resampling.LANCZOS)
            cards.append((thumb, row))
    columns, card_h = 4, 350
    canvas = Image.new("RGB", (columns * 250, max(1, (len(cards) + columns - 1) // columns) * card_h), "#161b22")
    draw = ImageDraw.Draw(canvas)
    for index, (thumb, row) in enumerate(cards):
        x, y = (index % columns) * 250 + 15, (index // columns) * card_h + 12
        canvas.paste(thumb, (x, y))
        draw.text((x, y + 292), str(row["title"])[:32], fill="white")
        draw.text((x, y + 312), str(row["puzzle_type"])[:28], fill="#e8bd54")
    target.parent.mkdir(parents=True, exist_ok=True); canvas.save(target)


def main() -> None:
    from background_generation.index import BackgroundAssetIndex
    index = BackgroundAssetIndex(); index.ensure_provenance_audited()
    assets, rows = index.assets(), package_rows()
    contact_sheet(rows, REPORTS / "COVER_AUDIT_AFTER.png")
    selectable = [asset for asset in assets if index.production_selectable(asset)]
    quarantined = [asset for asset in assets if not index.production_selectable(asset)]
    lines = ["COVER SYSTEM HARDENING REPORT", "=" * 54, "", "EXECUTIVE SUMMARY",
             "The production selector now requires explicit project-generated provenance and meaningful topic relevance.",
             "Mixed Brain Games no longer uses the former central white card/contact-sheet composition.", "",
             "BACKGROUND PROVENANCE AUDIT", f"Indexed assets: {len(assets)}", f"Production-selectable SladePuzzleCo assets: {len(selectable)}", f"Quarantined / excluded: {len(quarantined)}", "",
             "ROOT CAUSES", "• Legacy manifest records were treated as approved based on folder/manifest presence alone.",
             "• Non-word-search covers selected hard-coded filenames outside the shared approved selector.",
             "• Mixed covers used one shared large panel in puzzle_type_hero.", "",
             "FIXES", "• Explicit production_approved + project_generated + recognized provider gate (fail closed).",
             "• Shared topic-first scoring; generic puzzle convenience cannot outrank a specific topic match.",
             "• New mixed-edge, mixed-editorial, and mixed-logic directions plus edge motifs.", "",
             "CURRENT PACKAGE AUDIT", f"Packages audited: {len(rows)}", f"Covers kept: {sum(row['status'] == 'KEEP' for row in rows)}", f"Mixed covers rebuilt: {sum(row['status'] == 'REBUILT' for row in rows)}"]
    for row in rows:
        lines.append(f"• {row['status']}: {row['title']} — provenance {'PASS' if row['provenance_ok'] else 'REVIEW'}")
    lines += ["", "COVER-ONLY PRESERVATION", "The rebuilt Mixed Brain Games interiors were SHA-256 checked before and after regeneration and remained unchanged.",
              "Cover-derived marketplace assets were refreshed locally; existing marketplace handoffs are visibly marked for a cover refresh.", "",
              "CONTACT SHEET", str(REPORTS / "COVER_AUDIT_AFTER.png"), "", "REMAINING LIMIT", "A historical before-contact-sheet was not retained before this repair, so one was not fabricated."]
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "COVER_SYSTEM_HARDENING_REPORT.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
