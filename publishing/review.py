"""Read-only final review summaries for the Publishing Manager."""
from __future__ import annotations

from pathlib import Path

from .listing_copy import listing_copy_text
from .marketplaces import PUBLISHERS
from .package_layout import package_file, proof_folder
from .editorial_readiness import nonword_package_issues, source_editorial_issues


def build_proof_contact_sheet(folder: Path) -> Path | None:
    """Create one easy visual review sheet from the package's existing previews."""
    from PIL import Image, ImageDraw
    candidates = (package_file(folder, "front_cover.png"), package_file(folder, "kdp_full_wrap_preview.png"), proof_folder(folder) / "buyer_thumbnail.png")
    images = []
    for path in candidates:
        if not path.is_file():
            continue
        try:
            image = Image.open(path).convert("RGB"); image.thumbnail((420, 520), Image.Resampling.LANCZOS); images.append((path.name, image.copy()))
        except OSError:
            continue
    if not images:
        return None
    sheet = Image.new("RGB", (460 * len(images), 600), "#101418"); draw = ImageDraw.Draw(sheet)
    for index, (label, image) in enumerate(images):
        x = index * 460 + (460 - image.width) // 2
        sheet.paste(image, (x, 50)); draw.text((index * 460 + 20, 550), label, fill="#f4f7f8")
    output = proof_folder(folder, create=True) / "PROOF_CONTACT_SHEET.png"; output.parent.mkdir(exist_ok=True); sheet.save(output)
    return output


def series_consistency_report(books: list[dict]) -> list[str]:
    """Plain-English consistency checks for a selected series before release."""
    if len(books) < 2:
        return ["Choose at least two books to compare a series."]
    metas = [book.get("metadata") or {} for book in books]
    checks = {"Author": "author", "Series": "series", "Puzzle count": "puzzle_count", "Difficulty": "difficulty_label", "Trim": "trim_size"}
    lines: list[str] = []
    for label, key in checks.items():
        values = {str(meta.get(key) or "—") for meta in metas}
        lines.append(f"PASS — {label} is consistent ({next(iter(values))})." if len(values) == 1 else f"CHECK — {label} varies: {', '.join(sorted(values))}.")
    palettes = {str(meta.get("palette") or "—") for meta in metas}
    lines.append("PASS — Cover palette direction is consistent." if len(palettes) == 1 else "NOTE — Cover palettes vary; confirm this is intentional for the series.")
    return lines


def review_result(book: dict, marketplace: str = "amazon") -> dict:
    """Return a buyer-facing listing and print-proof review without writing files."""
    meta = book.get("metadata") or {}; files = meta.get("files") if isinstance(meta.get("files"), dict) else {}
    blockers = list(PUBLISHERS[marketplace].blocking_issues(PUBLISHERS[marketplace].validate(book)))
    blockers.extend(source_editorial_issues(book))
    blockers.extend(nonword_package_issues(book))
    checks: list[str] = []
    interior = Path(str(files.get("print_interior") or "")); cover = Path(str(files.get("print_cover") or "")); front = Path(str(files.get("front_cover") or ""))
    checks.append("Interior PDF is present." if interior.is_file() else "Interior PDF is missing.")
    checks.append("Print cover PDF is present." if cover.is_file() else "Print cover PDF is missing.")
    if front.is_file():
        try:
            from PIL import Image
            with Image.open(front) as image:
                checks.append(f"Front cover is {image.width} × {image.height} pixels." if image.width >= 2550 and image.height >= 3300 else f"Front cover is only {image.width} × {image.height} pixels; re-export at print size.")
        except Exception:
            checks.append("Front-cover image is present but could not be inspected.")
    else:
        checks.append("Front-cover image is missing.")
    pages = int(meta.get("page_count") or 0)
    checks.append(f"Interior page count: {pages}." if pages else "Confirm the final interior page count.")
    if pages and pages % 2: checks.append("Page count is odd; confirm the final export has an even page count before cover creation.")
    return {"ready": not blockers, "blockers": blockers, "checks": checks, "listing": listing_copy_text(book, marketplace)}


def review_text(book: dict, marketplace: str = "amazon") -> str:
    result = review_result(book, marketplace)
    title = str((book.get("metadata") or {}).get("title") or "Untitled book")
    from .production_gate import book_gate
    gate = book_gate(book)
    lines = [f"FINAL REVIEW — {title}", "=" * 52, "", "RESULT: " + ("READY FOR HANDOFF REVIEW" if result["ready"] else "NEEDS ATTENTION"), "", "PRODUCTION GATE", f"• {gate['stage']}"]
    lines += [f"• {item}" for item in gate["blockers"]] or ["• No source-level hard stops found."]
    lines += ["", "FILE & PROOF CHECKS"]
    lines += [f"• {item}" for item in result["checks"]]
    if result["blockers"]:
        lines += ["", "FIX BEFORE PREPARING"] + [f"• {item}" for item in result["blockers"]]
    lines += ["", result["listing"]]
    return "\n".join(lines)
