"""Clear, platform-specific listing handoff documents.

These documents are deliberately human-readable.  They put the exact fields a
seller needs in one place, while the platform adapters continue to supply the
upload files beside them.
"""
from __future__ import annotations

from typing import Any

from .metadata_service import marketplace_content


PLATFORM_NAMES = {
    "amazon": "Amazon KDP",
    "etsy": "Etsy",
    "ingram": "IngramSpark",
    "website": "Direct Website",
    "lulu": "Lulu Direct",
    "bookvault": "BookVault",
    "barnes_noble": "Barnes & Noble Press",
    "payhip": "Payhip",
}


def _number(value: Any, default: int = 0) -> int:
    try:
        return int(value or default)
    except (TypeError, ValueError):
        return default


def _money(value: float) -> float:
    """Keep recommendations in familiar .99 retail increments."""
    return max(0.99, float(int(value)) + 0.99)


def kdp_us_large_trim_estimate(meta: dict) -> dict[str, float | str]:
    """Current planning estimate for US black-ink 8.5x11 paperbacks.

    KDP remains the final authority. Rates below reflect its September 2026
    published table: $2.84 through 110 pages, then $1.00 + $0.017/page, with
    the 60% Amazon.com royalty tier beginning at $9.99.
    """
    pages = _number(meta.get("page_count"))
    price = float(recommended_prices(meta)["amazon"])
    printing = 2.84 if 24 <= pages <= 110 else 1.00 + pages * 0.017 if pages > 110 else 0.0
    rate = 0.60 if price >= 9.99 else 0.50
    return {
        "basis": "Amazon.com, black ink, white paper, large trim; rates checked 2026-09-20",
        "estimated_printing_cost": round(printing, 2),
        "royalty_rate": rate,
        "estimated_royalty": round(max(0.0, price * rate - printing), 2),
    }


def recommended_prices(meta: dict) -> dict[str, float]:
    """Return conservative starting prices, not a promise of printer margin.

    Print costs and permitted price ranges change by trim, paper, page count,
    territory, discount and return choices.  The final price remains the
    platform calculator's decision.  This gives the seller a sensible first
    value without pretending a single price fits every printer.
    """
    pages = _number(meta.get("page_count"))
    puzzles = _number(meta.get("puzzle_count"))
    edition = " ".join(str(meta.get(key) or "") for key in ("title", "subtitle", "edition")).casefold()
    signature = "signature" in edition
    puzzle_type = str(meta.get("puzzle_type") or "")
    variety = any(term in edition for term in ("letter and shape", "letter, and shape", "symbols")) or puzzle_type == "Mixed Brain Games"

    if pages >= 240:
        paperback = 14.99
    elif pages >= 180:
        paperback = 13.99
    elif pages >= 120:
        paperback = 11.99
    else:
        paperback = 9.99
    if pages < 120 and puzzle_type == "Mixed Brain Games":
        paperback += 1.00
    if puzzles >= 100:
        paperback += 1.00
    if variety and pages < 180:
        paperback += 1.00
    if signature:
        paperback += 2.00

    # Direct downloads are a separate product: no print cost, but still a
    # complete, professionally formatted puzzle book.
    digital = 6.99 if puzzles >= 100 or pages >= 180 or variety else 4.99
    if signature:
        digital += 1.00
    print_plus_distribution = _money(paperback + 2.00)
    return {
        "amazon": _money(paperback),
        "etsy": _money(digital),
        "direct_digital": _money(digital),
        "direct_print": _money(paperback + 1.00),
        "ingram": print_plus_distribution,
        "lulu": print_plus_distribution,
        "bookvault": print_plus_distribution,
        # B&N Press requires a minimum $14.99 for print books listed for sale
        # as of April 2026.  Keep the suggestion safely at or above it.
        "barnes_noble": max(14.99, _money(paperback + 1.00)),
        "payhip": _money(digital),
    }


def recommended_bundle_prices(books: list[dict]) -> dict[str, float]:
    """Give bundles a visible, conservative savings-based starting price."""
    metas = [book.get("metadata", book) if isinstance(book, dict) else {} for book in books]
    if not metas:
        return {"etsy": 0.0, "website": 0.0, "print_series": 0.0, "savings_percent": 0.0}
    digital_total = sum(float(recommended_prices(meta).get("etsy", 0.0)) for meta in metas)
    print_total = sum(float(recommended_prices(meta).get("amazon", 0.0)) for meta in metas)
    # Keep a bundle meaningfully better than individual checkout without
    # racing to the bottom. More books receive a modestly larger discount.
    discount = 0.15 if len(metas) == 2 else 0.20 if len(metas) <= 4 else 0.25
    def price(value: float) -> float:
        return max(2.99, float(int(max(0, value * (1 - discount)))) + 0.99)
    return {"etsy": price(digital_total), "website": price(digital_total), "print_series": price(print_total), "savings_percent": round(discount * 100)}


def _lines(values: list[str] | tuple[str, ...] | None) -> str:
    clean = [str(value).strip() for value in (values or []) if str(value).strip()]
    return "\n".join(f"• {value}" for value in clean) or "• Review and add a relevant value."


def _keywords_under_50(meta: dict) -> list[str]:
    values = list(meta.get("etsy_tags") or meta.get("website_tags") or [])
    return [str(value).strip()[:49] for value in values if str(value).strip()][:10]


def listing_copy_text(book: dict, platform: str) -> str:
    """Build one ready-to-copy listing sheet for the selected marketplace."""
    meta = book["metadata"]
    content = marketplace_content(meta)
    # Recalculate at handoff time. Existing catalog records may have been
    # created before the platform-specific price guide was added.
    prices = recommended_prices(meta)
    price = float(prices.get(platform, prices.get("direct_print", 0)) or 0)
    name = PLATFORM_NAMES.get(platform, platform.replace("_", " ").title())
    base = [
        f"{name.upper()} — READY-TO-COPY LISTING INFORMATION",
        "=" * 58,
        "",
        f"Title: {meta.get('title') or 'Untitled book'}",
        f"Subtitle: {meta.get('subtitle') or '—'}",
        f"Author / contributor: {meta.get('author') or '—'}",
        f"Series: {meta.get('series') or '—'}",
        f"Language: {meta.get('language') or 'English'}",
        f"Trim size: {meta.get('trim_size') or '—'}",
        f"Interior pages: {_number(meta.get('page_count')) or 'Confirm after final export'}",
        f"ISBN: {meta.get('isbn') or 'Not assigned'}",
        f"Suggested starting price: ${price:.2f}",
        "",
        "DESCRIPTION TO PASTE",
        "-" * 24,
        str((meta.get("platform_descriptions") or {}).get(platform) or content["platform_descriptions"].get(platform) or meta.get("description") or content["description"]),
        "",
    ]
    if platform == "amazon":
        estimate = kdp_us_large_trim_estimate(meta)
        base += ["KDP KEYWORDS (one per line)", "-" * 28, _lines(content["amazon_keywords"]), "", "KDP CATEGORY DIRECTIONS (choose the closest current paths in the KDP portal)", "-" * 74, _lines(content.get("amazon_category_directions") or []), "", "PRIMARY AUDIENCE / READING AGE", "-" * 31, f"Primary audience: {content.get('primary_audience') or 'Adult / General'}", f"Reading age: {content.get('reading_age') or 'Not required'}", "", "BISAC / DISTRIBUTION SUBJECT", "-" * 29, _lines(content["ingram_subjects"]), "", "CURRENT US PRICE CHECK", "-" * 22, f"Planning basis: {estimate['basis']}", f"Estimated printing cost: ${estimate['estimated_printing_cost']:.2f}", f"Estimated royalty at {int(float(estimate['royalty_rate']) * 100)}%: ${estimate['estimated_royalty']:.2f}"]
    elif platform == "etsy":
        base += ["ETSY TAGS (up to 13; one per line)", "-" * 35, _lines(content["etsy_tags"]), "", "DIGITAL DELIVERY", "-" * 20, "Instant download PDF. State clearly that this is a digital product if you list it as one."]
    elif platform == "payhip":
        base += ["DIGITAL DELIVERY", "-" * 20, "Use the dedicated PAYHIP_PUBLISHING_SHEET.txt in the Payhip handoff folder. It lists the customer PDF, preview PDF, images, collection, visibility, and supported form options without inventing search fields."]
    elif platform == "ingram":
        base += ["BISAC / SUBJECTS", "-" * 18, _lines(content["ingram_subjects"]), "", "DISTRIBUTION NOTE", "-" * 20, "Confirm discount, return policy, territory, print specifications, and the final printer-calculated price in the IngramSpark portal."]
    elif platform in {"lulu", "bookvault", "barnes_noble"}:
        base += ["KEYWORDS / SUBJECTS", "-" * 22, _lines(_keywords_under_50(content) if platform == "lulu" else content["website_tags"]), "", "PRINT SETUP NOTE", "-" * 22, "Use this information with the platform's own trim, page-count, paper, binding, and cover-template choices."]
    else:
        base += ["PRODUCT TAGS", "-" * 16, _lines(content["website_tags"]), "", "PRODUCT OPTIONS", "-" * 19, f"Printable PDF: ${float(prices.get('direct_digital', price)):.2f}", f"Paperback: ${float(prices.get('direct_print', price)):.2f}"]
    base += ["", "PRICE NOTE", "-" * 12, "This is a starting-price recommendation, not a guaranteed royalty or margin. Confirm the platform's live print-cost and price calculator before publishing.", ""]
    return "\n".join(base)


def upload_notes_text(book: dict, platform: str) -> str:
    """Give only the platform requirements that affect this handoff."""
    meta = book["metadata"]
    name = PLATFORM_NAMES.get(platform, platform.replace("_", " ").title())
    common = [
        f"{name.upper()} — UPLOAD NOTES",
        "=" * 42,
        f"Book: {meta.get('title') or 'Untitled book'}",
        "",
    ]
    notes = {
        "amazon": [
            "Upload interior.pdf and cover.pdf as separate files.",
            "Use KDP Print Previewer before publishing.",
            "The cover is a single back-spine-front PDF; keep the platform-generated template and final page count aligned.",
        ],
        "etsy": [
            "Upload printable.pdf as the customer download. The preview images are listing photos, not buyer files.",
            "Etsy instant-download listings allow up to five files, with a maximum of 20 MB per file.",
            "Check product type, taxes, and delivery wording in Etsy before publishing.",
        ],
        "ingram": [
            "Use interior.pdf as the starting interior file, then build a fresh cover on the current IngramSpark template.",
            "For the final printer files, confirm the platform's PDF/X, CMYK, bleed, safety, discount, returns, territory, and ISBN choices.",
            "Do not use a KDP-sized wrap as the final Ingram cover without rebuilding it on the Ingram template.",
        ],
        "lulu": [
            "Use interior.pdf as the starting interior file, then build a fresh cover on the current Lulu template.",
            "For global distribution, confirm ISBN, metadata, title/copyright page, and final cover/template requirements in Lulu.",
            "Lulu keywords must be under 50 characters each; the suggested set above is already shortened.",
        ],
        "bookvault": [
            "Use interior.pdf as the starting interior file, then build a fresh cover on the BookVault template for the selected specification.",
            "BookVault requires PDF files; use its template for the exact trim, page count, binding, and bleed.",
            "Confirm the platform's paper, binding, colour/mono pages, ISBN, and production cost before setting your final price.",
        ],
        "barnes_noble": [
            "Upload print-ready interior and cover PDFs created from the current B&N Press template and specifications.",
            "Books listed for sale need an ISBN; do not reuse an ISBN already in wide distribution.",
            "B&N Press print books listed for sale currently require a retail price of at least $14.99. Confirm the live calculator before publishing.",
        ],
        "payhip": [
            "Upload the customer ZIP or customer PDF; use the listing cover image and preview PDF if supplied.",
            "Payhip currently allows multiple product files up to 5 GB each. Recheck current limits, visibility, tax, and checkout settings before release.",
            "Use PAYHIP_STORE_SETUP_SHEET.txt once for the store-wide customer receipt, then use PAYHIP_PUBLISHING_SHEET.txt for product-specific copy.",
        ],
        "website": [
            "Upload printable.pdf as the digital customer download and product-cover.png as the product image.",
            "Use product.json or product.csv only if your store platform supports that import; otherwise copy the listing sheet into your store.",
        ],
    }
    common += [f"• {note}" for note in notes.get(platform, ["Review the marketplace's current upload rules before publishing."])]
    common += ["", "This folder prepares files and information only. It never uploads or publishes on your behalf.", ""]
    return "\n".join(common)
