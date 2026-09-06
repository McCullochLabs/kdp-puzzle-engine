"""Copy-ready, human-operated publishing sheets.

These sheets are deliberately generated from the same catalog record used by
the Publishing Center.  They are local handoff aids, never browser or API
automation, and do not alter the book record.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .listing_copy import listing_copy_text
from .metadata_service import marketplace_content


PLATFORM_NAMES = {
    "amazon": "Amazon KDP", "barnes_noble": "Barnes & Noble Press",
    "lulu": "Lulu", "ingram": "IngramSpark", "etsy": "Etsy",
    "payhip": "Payhip", "website": "Direct Website", "bookvault": "BookVault",
}


def sheet_filename(platform: str) -> str:
    return f"{str(platform).upper().replace('-', '_')}_PUBLISHING_SHEET.txt"


def _price(meta: dict, platform: str) -> str:
    prices = meta.get("price") if isinstance(meta.get("price"), dict) else {}
    value = prices.get(platform)
    if value is None and platform == "payhip":
        value = prices.get("direct_digital", prices.get("etsy"))
    if value is None:
        return "Set after reviewing the platform's current printing, tax, and fee terms."
    try:
        return f"${float(value):.2f} (editable recommendation)"
    except (TypeError, ValueError):
        return str(value)


def render_manual_sheet(book: dict, platform: str, handoff: Path | None = None,
                        extra_notes: list[str] | None = None) -> str:
    """Render one factual, copyable seller sheet from the canonical record."""
    meta = book.get("metadata") or {}
    platform = str(platform).strip().lower()
    if platform == "payhip":
        # Payhip uses one dedicated, form-ordered product sheet.  Its
        # store-wide receipt/branding instructions remain in the separate
        # one-time setup sheet, never repeated product by product.
        from .payhip_product import render_publishing_sheet
        return render_publishing_sheet(meta, {})
    name = PLATFORM_NAMES.get(platform, platform.replace("_", " ").title())
    content = marketplace_content(meta)
    description = (content.get("platform_descriptions") or {}).get(platform) or content.get("description") or ""
    keywords = content.get("amazon_keywords") or []
    tags = content.get("etsy_tags") or []
    category = "; ".join(content.get("ingram_subjects") or []) or "Choose the most specific current category in the portal."
    files = meta.get("files") if isinstance(meta.get("files"), dict) else {}
    location = str(handoff) if handoff else "Not prepared yet"
    notes = list(extra_notes or [])
    template_platforms = {"ingram", "lulu", "bookvault", "barnes_noble"}
    template_name = "B&N Press" if platform == "barnes_noble" else name
    if platform in template_platforms:
        notes += [
            f"Upload the finished interior PDF and a cover built on the current {template_name} template for this exact trim size and final page count.",
            f"The KDP cover is a visual reference only; do not upload it as a {template_name} final cover.",
            f"Confirm current print cost, royalty, territory, ISBN choice, and final proof inside {template_name} before publishing.",
        ]
    else:
        notes.append("Review the platform's current upload rules and final preview before publishing.")
    receipt_lines: list[str] = []
    lines = [
        f"{name.upper()} — MANUAL PUBLISHING SHEET",
        "=" * 68,
        "Generated locally: " + datetime.now().strftime("%Y-%m-%d %H:%M"),
        "This sheet prepares a manual listing only. Nothing has been uploaded or published.", "",
        "COPY THESE FIELDS", "-" * 68,
        f"TITLE\n{meta.get('title') or 'Untitled Puzzle Book'}", "",
        f"SUBTITLE\n{meta.get('subtitle') or ''}", "",
        f"CONTRIBUTOR / AUTHOR\n{meta.get('author') or ''}", "",
        f"SERIES\n{meta.get('series') or 'Not part of a named series'}", "",
        f"DESCRIPTION\n{description}", "",
        "KEYWORDS", *[str(item) for item in keywords], "",
        "TAGS / SEARCH TERMS", *[str(item) for item in tags], "",
        f"CATEGORY / SUBJECT\n{category}", "",
        f"RECOMMENDED STARTING PRICE\n{_price(meta, platform)}", "",
        "BOOK DETAILS", "-" * 68,
        f"Puzzle type: {content.get('puzzle_type') or meta.get('puzzle_type') or 'Puzzle Book'}",
        f"Topic: {meta.get('theme') or meta.get('detected_topic') or ''}",
        f"Puzzle count: {meta.get('puzzle_count') or 0}",
        f"Difficulty: {meta.get('difficulty') or meta.get('difficulty_label') or 'Standard'}",
        f"Page count: {meta.get('page_count') or 'Confirm from final interior PDF'}",
        f"Trim size: {meta.get('trim_size') or 'Confirm in final upload settings'}",
        f"ISBN: {meta.get('isbn') or 'Not assigned'}", "",
        "FILES TO USE", "-" * 68,
        f"Prepared folder: {location}",
        f"Interior {'starting file' if platform in template_platforms else 'upload file'}: {files.get('print_interior') or 'Not available'}",
        f"{'KDP visual reference — NOT a final upload cover' if platform in template_platforms else 'Cover upload file'}: {files.get('print_cover') or 'Not available'}",
        f"Front cover image: {files.get('front_cover') or 'Not available'}", "",
        *receipt_lines, "",
        "FINAL HUMAN CHECK", "-" * 68,
        *[f"• {note}" for note in notes], "",
        "FULL COPY-READY LISTING", "-" * 68,
        listing_copy_text(book, platform), "",
    ]
    return "\n".join(lines)


def write_manual_sheet(book: dict, platform: str, handoff: Path,
                       extra_notes: list[str] | None = None) -> Path:
    handoff.mkdir(parents=True, exist_ok=True)
    target = handoff / sheet_filename(platform)
    target.write_text(render_manual_sheet(book, platform, handoff, extra_notes), encoding="utf-8")
    return target
