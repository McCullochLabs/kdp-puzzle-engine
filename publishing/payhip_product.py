"""Truthful Payhip product defaults and its one human publishing sheet."""
from __future__ import annotations

from .metadata_service import marketplace_content, puzzle_type_for

COLLECTIONS = ("Word Searches", "Sudoku", "Cryptograms", "Brain Games")
# "Education" is the currently verified Marketplace Category from the seller's
# Payhip product form.  Keeping the approved values separate from collections
# makes a future category expansion a small data update instead of a rewrite.
VERIFIED_MARKETPLACE_CATEGORIES = ("Education",)


def product_config(metadata: dict) -> dict:
    value = metadata.get("payhip")
    return dict(value) if isinstance(value, dict) else {}


def collection_for(metadata: dict) -> str:
    configured = str(product_config(metadata).get("collection") or "").strip()
    if configured in COLLECTIONS:
        return configured
    return {"Word Search": "Word Searches", "Sudoku": "Sudoku", "Cryptogram": "Cryptograms", "Mixed Brain Games": "Brain Games"}.get(puzzle_type_for(metadata), "Brain Games")


def marketplace_category_for(metadata: dict) -> str:
    configured = str(product_config(metadata).get("marketplace_category") or "").strip()
    if configured in VERIFIED_MARKETPLACE_CATEGORIES:
        return configured
    # Puzzle books are currently most accurately placed in the verified
    # Education category.  This is deliberately separate from storefront
    # collections and can be extended as Payhip's verified list grows.
    return "Education"


def tags_for(metadata: dict) -> list[str]:
    """Return product-specific Payhip Tags as separate, human-entered values.

    Payhip's current tag limit has not been encoded because it has not been
    independently verified here.  The curated source list is intentionally
    compact rather than pretending a limit exists.
    """
    configured = product_config(metadata).get("tags")
    values = list(configured) if isinstance(configured, (list, tuple)) else []
    kind = puzzle_type_for(metadata)
    topic = str(metadata.get("theme") or metadata.get("detected_topic") or "").strip().casefold()
    if topic in {"", "general", "general interest", "general starter", "starter", "mixed"}:
        topic = ""
    difficulty = str(metadata.get("difficulty") or metadata.get("difficulty_label") or "").strip().casefold()
    type_tags = {
        "Word Search": ["printable word searches", "word search puzzles for adults", "themed word search book"],
        "Sudoku": ["printable sudoku", "sudoku puzzles for adults", "logic puzzle book"],
        "Cryptogram": ["printable cryptograms", "cryptogram puzzles for adults", "code breaking puzzles"],
        "Word Scramble + Trivia": ["word scramble clues", "printable word games", "word puzzles for adults"],
        "Mixed Brain Games": ["brain games for adults", "printable brain games", "mixed puzzle book", "sudoku puzzles", "cryptogram puzzles", "word scrambles with clues"],
    }
    if not values:
        public_kind = "word scrambles with fact clues" if kind == "Word Scramble + Trivia" else kind.casefold()
        values = [f"{topic} {public_kind}" if topic else "", topic, *type_tags.get(kind, ["printable puzzle collection"])]
        if difficulty and difficulty not in {"standard", "normal"}:
            values.append(f"{difficulty} {public_kind} challenges")
        if "signature" in " ".join(str(metadata.get(key) or "") for key in ("title", "subtitle", "edition")).casefold():
            values.append("signature puzzle collection")
        values.append("printable puzzles for adults")
    clean: list[str] = []
    seen: set[str] = set()
    for value in values:
        tag = " ".join(str(value).split()).strip()
        key = tag.casefold()
        if tag and key not in seen:
            clean.append(tag); seen.add(key)
    return clean


def advanced_options(metadata: dict) -> dict[str, bool]:
    overrides = product_config(metadata).get("advanced_options")
    overrides = overrides if isinstance(overrides, dict) else {}
    defaults = {"different_variations": False, "tax_exempt_eu_uk": False, "is_ebook": False,
                "custom_tax_category": False, "upload_preview": True, "limit_sales": False,
                "mailing_list_subscription": False, "license_keys": False}
    return {key: bool(overrides.get(key, value)) for key, value in defaults.items()}


def visibility_for(metadata: dict) -> str:
    value = str(product_config(metadata).get("visibility") or "Visible").strip().title()
    return value if value in {"Visible", "Invisible", "Unlisted"} else "Visible"


def price_for(metadata: dict) -> float:
    # A value in the dedicated Payhip settings is a deliberate seller choice.
    # Older catalog records may contain an inherited Payhip price, so otherwise
    # calculate from the current product rather than preserving that stale value.
    value = product_config(metadata).get("price")
    try:
        if value is not None:
            return float(value)
    except (TypeError, ValueError):
        pass
    count = int(metadata.get("puzzle_count") or 0)
    return 7.99 if count >= 100 else 6.49 if count >= 60 else 5.99 if count >= 48 else 3.99


def description_for(metadata: dict) -> str:
    configured = str(product_config(metadata).get("description") or "").strip()
    intelligent = str((metadata.get("platform_descriptions") or {}).get("payhip") or "").strip()
    if not configured and intelligent:
        configured = intelligent
    if configured:
        disclosure = "\n\nDIGITAL PRODUCT: This purchase includes a downloadable PDF. No physical product will be shipped."
        return configured if "downloadable" in configured.casefold() and "physical" in configured.casefold() else configured + disclosure
    content = marketplace_content(metadata); kind = content.get("puzzle_type") or puzzle_type_for(metadata)
    count = int(metadata.get("puzzle_count") or 0); topic = str(metadata.get("theme") or metadata.get("detected_topic") or "a relaxing variety of puzzles").strip()
    difficulty = str(metadata.get("difficulty") or metadata.get("difficulty_label") or "Standard").lower()
    types = {"Mixed Brain Games": "a variety of Sudoku, cryptograms, and word scrambles with fact clues", "Sudoku": "verified Sudoku challenges", "Cryptogram": "code-breaking cryptogram challenges", "Word Search": "themed word-search puzzles", "Word Scramble + Trivia": "word scrambles guided by approachable fact clues"}
    title = str(metadata.get("title") or "This puzzle collection")
    return (f"{title} is a printable collection of {count} {types.get(kind, 'printable puzzle challenges')} for adults and teens. "
            f"The book has a {difficulty} feel, clear full-size pages, and complete solutions so you can enjoy {topic} at your own pace.\n\n"
            "DIGITAL PRODUCT: This purchase includes a downloadable PDF that you can print at home or enjoy on-screen. No physical product will be shipped.\n\n"
            f"What you receive:\n• {count} clearly organized {types.get(kind, kind.lower())}\n• Complete solutions\n• A clean printable PDF in an easy-to-use layout\n\n"
            "Download your file after purchase, choose a puzzle that fits your mood, and enjoy a satisfying screen-free break.")


def render_publishing_sheet(metadata: dict, artifact_names: dict[str, object]) -> str:
    """The sole product-level human document; follows Payhip's form order."""
    options = advanced_options(metadata); images = [str(name) for name in artifact_names.get("images", [])]
    preview = str(artifact_names.get("preview") or "preview.pdf"); customer = str(artifact_names.get("customer_pdf") or "customer_product.pdf")
    option = lambda value: "TURN ON" if value else "LEAVE OFF"
    tags = tags_for(metadata)
    lines = ["PAYHIP — PUBLISHING SHEET", "=" * 62, "PRODUCT STATUS: READY FOR ASSISTED PUBLISHING", "This sheet and the named files are all you need for the Payhip product form. Nothing has been uploaded or published.", "",
             "PRODUCT TYPE", "-" * 62, "Digital Product / Printable PDF", "", "1. PRODUCT FILE", "-" * 62, f"UPLOAD: {customer}", "FILE TYPE: Printable PDF", "",
             "2. TITLE", "-" * 62, "COPY:", str(metadata.get("title") or "Untitled Puzzle Book"), "", "3. PRICE", "-" * 62, f"ENTER: ${price_for(metadata):.2f}", "PRICE STRATEGY: Editable starting price for a complete digital puzzle collection; review before publishing.", "",
             "4. COVER / PRODUCT IMAGES", "-" * 62, f"UPLOAD FIRST: {images[0] if images else 'product_cover.png'}", "OPTIONAL ADDITIONAL IMAGES:", *[f"• {name}" for name in images[1:]], "",
             "5. DESCRIPTION", "-" * 62, "COPY:", description_for(metadata), "", "6. VISIBILITY", "-" * 62, f"SELECT: {visibility_for(metadata)}", "", "7. COLLECTION", "-" * 62, f"SELECT: {collection_for(metadata)}", "", "8. MARKETPLACE CATEGORY", "-" * 62, f"SELECT: {marketplace_category_for(metadata)}", "", "9. TAGS", "-" * 62, "ADD THESE TAGS ONE AT A TIME:", *[f"{index}. {tag}" for index, tag in enumerate(tags, 1)], "",
             "10. ADVANCED OPTIONS", "-" * 62, f"This product has different variations: {option(options['different_variations'])}", f"Tax exempt in EU/UK: {option(options['tax_exempt_eu_uk'])}", f"Product is an ebook: {option(options['is_ebook'])}", f"Customize product tax category: {option(options['custom_tax_category'])}", f"Upload a preview file for customers: {option(options['upload_preview'])}", f"PREVIEW FILE — UPLOAD: {preview}", f"Limit number of sales: {option(options['limit_sales'])}", f"Automatically subscribe customers to mailing list: {option(options['mailing_list_subscription'])}", f"Generate unique license keys: {option(options['license_keys'])}", "",
             "11. DIGITAL PRODUCT NOTICE", "-" * 62, "Ensure the description makes clear: This is a downloadable PDF. No physical product will be shipped.", "",
             "12. FINAL CHECKLIST", "-" * 62, "[ ] Customer PDF uploaded", "[ ] Title entered", "[ ] Price entered", "[ ] Main product image uploaded", "[ ] Additional product images uploaded as desired", "[ ] Description copied", "[ ] Visibility selected", "[ ] Collection selected", "[ ] Marketplace Category selected", "[ ] Tags added ONE AT A TIME", "[ ] Preview option enabled", "[ ] preview.pdf uploaded", "[ ] ebook option configured correctly", "[ ] license-key option configured correctly", "[ ] Digital product disclosure verified", "[ ] Product reviewed", "[ ] Product published manually", "[ ] Publication marked in Publishing Center", "",
             "STORE-WIDE NOTE", "-" * 62, "Use PAYHIP_STORE_SETUP_SHEET.txt once for receipt email, branding, policies, and other Payhip-wide settings.", ""]
    return "\n".join(lines)
