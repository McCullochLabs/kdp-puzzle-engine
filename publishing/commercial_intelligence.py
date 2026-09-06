"""Explainable commercial planning built on the canonical product metadata.

This layer intentionally answers a different question from the production
gate: *does this completed product have a clear, platform-appropriate buyer
offer?*  It never predicts sales, uploads products, or treats an estimate as a
marketplace rule.  Technical readiness remains owned by ``production_gate``.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .listing_copy import recommended_prices
from .metadata_service import marketplace_content, marketplace_copy_quality, puzzle_type_for
from .commercial_profiles import (
    PROFILE_VERSION,
    PUZZLE_PROFILES,
    MARKETPLACE_PROFILES,
    commercial_warnings,
    infer_archetypes,
    marketplace_fit,
    mini_theme_capacity,
    normalize_puzzle_type,
    puzzle_format_fit,
)


RULE_VERSION = "commercial-rules-2026.08"
MARKETPLACES = ("amazon", "barnes_noble", "payhip", "lulu")
MARKET_LABELS = {
    "amazon": "Amazon KDP",
    "barnes_noble": "Barnes & Noble Press",
    "payhip": "Payhip",
    "lulu": "Lulu",
}


@dataclass(frozen=True)
class CommercialProfile:
    marketplace: str
    format: str
    value_focus: str
    pricing_note: str
    route_note: str


PROFILES = {
    "amazon": CommercialProfile(
        "amazon", "print paperback", "clear front-cover promise, specific search phrases, and a complete answer section",
        "Suggested KDP price is a starting point. Confirm the live KDP calculator because printing cost and royalty depend on page count, ink, and marketplace.",
        "Prepare KDP paperback files. A+ content is a post-publication detail-page asset, not a substitute for the cover or description.",
    ),
    "barnes_noble": CommercialProfile(
        "barnes_noble", "print paperback", "premium perceived value, an ISBN, and a printer-specific final cover",
        "B&N Press print listings currently require at least $14.99; confirm the live calculator and your exact print specification before publication.",
        "Use a B&N Press cover template for the final trim and page count; a KDP full wrap is reference-only.",
    ),
    "payhip": CommercialProfile(
        "payhip", "digital download", "a buyer-safe PDF, useful preview, clear digital-delivery wording, and a related collection",
        "Suggested digital price is a starting point. Keep the digital offer distinct from print and show exactly what the download contains.",
        "Use the Payhip product and store setup sheets. Collections are useful for related products and cross-sells.",
    ),
    "lulu": CommercialProfile(
        "lulu", "print / direct fulfillment", "printer-specific cover dimensions, clear product metadata, and deliberate distribution choices",
        "Suggested Lulu price is a starting point. Confirm current print cost, territory, tax, and distribution settings in Lulu before publication.",
        "Build a Lulu-specific cover from its current template. If Lulu Global Distribution overlaps with KDP Expanded Distribution, choose a deliberate channel strategy first.",
    ),
}


def _text(meta: dict) -> str:
    return " ".join(str(meta.get(key) or "") for key in (
        "title", "subtitle", "theme", "detected_topic", "series", "description", "buyer_angle",
    )).casefold()


def _clean(values: list[str], limit: int) -> list[str]:
    seen: set[str] = set(); result: list[str] = []
    for value in values:
        phrase = " ".join(str(value).split()).strip()
        key = phrase.casefold()
        if phrase and key not in seen:
            result.append(phrase); seen.add(key)
        if len(result) == limit:
            break
    return result


def _value_signals(meta: dict) -> tuple[int, list[str], list[str]]:
    """Return an explainable buyer-value score, never a sales forecast."""
    score = 30; strengths: list[str] = []; improvements: list[str] = []
    title = str(meta.get("title") or "").strip()
    subtitle = str(meta.get("subtitle") or "").strip()
    topic = str(meta.get("theme") or meta.get("detected_topic") or "").strip()
    count = int(meta.get("puzzle_count") or 0)
    kind = puzzle_type_for(meta)
    if title and 8 <= len(title) <= 80:
        score += 12; strengths.append("clear buyer-facing title")
    else:
        improvements.append("Use a concise title that states the topic or activity clearly.")
    if topic and topic.casefold() not in {"general", "puzzle book", "themed puzzles"}:
        score += 14; strengths.append("specific topic")
    else:
        improvements.append("Name a specific buyer topic instead of a broad placeholder.")
    if subtitle and any(token in subtitle.casefold() for token in ("puzzle", "sudoku", "cryptogram", "trivia", "scramble", "brain game")):
        score += 9; strengths.append("format stated in subtitle")
    else:
        improvements.append("Make the subtitle say what type of puzzles buyers receive.")
    if count >= 100:
        score += 15; strengths.append("100-puzzle Signature-scale collection")
    elif count >= 48:
        score += 12; strengths.append("full-length puzzle count")
    else:
        improvements.append("Increase the puzzle count or position this honestly as a smaller product.")
    if str(meta.get("difficulty") or meta.get("difficulty_label") or "").strip():
        score += 5; strengths.append("difficulty stated")
    if kind != "Word Search" or "answer" in _text(meta) or "solution" in _text(meta):
        score += 5; strengths.append("solution expectation is covered")
    if str(meta.get("series") or "").strip():
        score += 5; strengths.append("series connection")
    return min(score, 100), strengths, improvements


def _a_plus_plan(meta: dict) -> dict[str, Any]:
    kind = puzzle_type_for(meta)
    topic = str(meta.get("theme") or meta.get("detected_topic") or "this topic")
    count = int(meta.get("puzzle_count") or 0)
    return {
        "eligible_after_publication": True,
        "modules": [
            {"name": "Hero", "copy": f"{count} {kind} challenges centered on {topic}.".strip()},
            {"name": "What is inside", "copy": f"Show a real interior puzzle page, answer-page sample, and the verified difficulty level."},
            {"name": "Series / next read", "copy": "Use only verified companion titles from the same series; do not invent future books."},
        ],
        "note": "Amazon KDP A+ Content is created for published books in the KDP A+ Content Manager. Review the current A+ guidelines before submission.",
    }


def _category_suggestions(meta: dict, kind: str) -> list[str]:
    topic = str(meta.get("theme") or meta.get("detected_topic") or meta.get("topic") or "").casefold()
    base = {
        "word_search": ["Games & Activities / Word & Word Search", "Games & Activities / Puzzles", "Games & Activities / General"],
        "sudoku": ["Games & Activities / Sudoku", "Games & Activities / Logic & Brain Teasers", "Games & Activities / Puzzles"],
        "cryptogram": ["Games & Activities / Logic & Brain Teasers", "Games & Activities / Puzzles", "Games & Activities / General"],
        "scramble_trivia": ["Games & Activities / Trivia", "Games & Activities / Word & Word Search", "Games & Activities / Puzzles"],
        "mixed": ["Games & Activities / Puzzles", "Games & Activities / Logic & Brain Teasers", "Games & Activities / General"],
    }[kind]
    if "history" in topic:
        base[-1] = "History / General"
    elif any(word in topic for word in ("school", "grade", "vocabulary")):
        base[-1] = "Study Aids / General"
    elif any(word in topic for word in ("faith", "bible", "scripture")):
        base[-1] = "Religion / Christian Living / General"
    return base


def commercial_assessment(book: dict, marketplace: str | None = None) -> dict[str, Any]:
    """Assess buyer-value and marketplace route from verified local facts only."""
    meta = dict(book.get("metadata") or book or {})
    selected = (marketplace,) if marketplace else MARKETPLACES
    content = marketplace_content(meta)
    value_score, strengths, improvements = _value_signals(meta)
    prices = recommended_prices(meta)
    files = meta.get("files") if isinstance(meta.get("files"), dict) else {}
    results: dict[str, Any] = {}
    for key in selected:
        if key not in PROFILES:
            raise ValueError(f"Unknown commercial marketplace: {key}")
        profile = PROFILES[key]
        quality_platform = "etsy" if key == "payhip" else "amazon" if key == "amazon" else "ingram"
        quality = marketplace_copy_quality(meta, quality_platform)
        notes = list(quality["notes"])
        required_files = ["print_interior", "print_cover"] if key in {"amazon", "barnes_noble", "lulu"} else ["printable_pdf"]
        missing_files = [name for name in required_files if not files.get(name)]
        if missing_files:
            notes.append("Commercial preparation cannot be completed until the package supplies: " + ", ".join(missing_files) + ".")
        overlap_warning = ""
        distribution = " ".join(str(meta.get(name) or "") for name in ("distribution", "distribution_plan", "marketplaces", "expanded_distribution"))
        if key == "lulu" and ("expanded" in distribution.casefold() or "kdp" in distribution.casefold()):
            overlap_warning = "Possible distribution overlap: compare Lulu Global Distribution with any KDP Expanded Distribution plan before enabling both."
        results[key] = {
            "marketplace": MARKET_LABELS[key],
            "format": profile.format,
            "buyer_value_focus": profile.value_focus,
            "suggested_price": prices.get(key),
            "pricing_note": profile.pricing_note,
            "route_note": profile.route_note,
            "listing_quality": quality,
            "missing_file_facts": missing_files,
            "overlap_warning": overlap_warning,
            "keywords": _clean(list(content.get("amazon_keywords") or []), 7) if key == "amazon" else _clean(list(content.get("website_tags") or []), 10),
            "a_plus_plan": _a_plus_plan(meta) if key == "amazon" else None,
        }
    profile_key = normalize_puzzle_type(meta.get("puzzle_type_id") or meta.get("puzzle_type"))
    archetypes = infer_archetypes(meta)
    all_marketplace_fit = marketplace_fit(meta)
    amazon_keywords = _clean(list(content.get("amazon_keywords") or []), 7)
    etsy_tags = _clean(list(content.get("etsy_tags") or content.get("website_tags") or []), 13)
    marketplace_strategies = {}
    for key, profile in MARKETPLACE_PROFILES.items():
        marketplace_strategies[key] = {
            "marketplace": profile["label"],
            "fit": all_marketplace_fit[key],
            "title_strategy": profile["title"],
            "description_strategy": profile["description"],
            "keyword_strategy": profile["keywords"],
            "image_plan": profile["images"],
            "bundle_strategy": profile["bundles"],
            "required_assets": list(profile["assets"]),
            "amazon_keyword_phrases": amazon_keywords if key == "amazon" else [],
            "etsy_tags": etsy_tags if key == "etsy" else [],
            "digital_disclosure": "DIGITAL DOWNLOAD — NO PHYSICAL PRODUCT" if key in {"etsy", "payhip"} else "",
        }
    marketplace_strategies["amazon"].update({
        "category_suggestions": _category_suggestions(meta, profile_key),
        "feature_concepts": [f"{int(meta.get('puzzle_count') or 0)} verified puzzles", "Complete solutions", "Topic-specific content"],
        "interior_preview_recommendations": ["Show one real puzzle page", "Show one real solution page", "Show actual large-print/readability detail when claimed"],
        "series_cross_sell": "Recommend only real published titles from the same verified series.",
    })
    marketplace_strategies["etsy"].update({
        "attributes": ["Digital download", "Printable PDF", PUZZLE_PROFILES[profile_key].puzzle_type],
        "conversion_opening": f"A printable {str(meta.get('theme') or meta.get('detected_topic') or 'themed')} puzzle collection with real previews and complete solutions.",
        "use_cases": ["screen-free puzzle break", "travel or waiting-room activity", "thoughtful printable gift"],
        "download_instructions": "Download the PDF after purchase and print with your preferred PDF viewer. No physical product is shipped.",
        "promotional_pricing_note": "Use the calculated digital starting price and verify current Etsy fees before listing.",
    })
    marketplace_strategies["payhip"].update({
        "seo_title": str(meta.get("title") or "Puzzle Collection")[:60],
        "seo_description": f"Printable {PUZZLE_PROFILES[profile_key].puzzle_type} collection focused on {str(meta.get('theme') or meta.get('detected_topic') or 'a clear theme')}."[:155],
        "gallery_plan": ["approved cover", "what is included", "real puzzle preview", "real solution preview", "digital-format disclosure"],
        "cross_sells": "Use only real related products or verified series members.",
        "lead_magnet_idea": "Offer a small real-page sampler only when the digital mini-pack validator passes.",
    })
    for key in ("barnes_noble", "ingram"):
        marketplace_strategies[key].update({"subject_suggestions": _category_suggestions(meta, profile_key), "edition_information": str(meta.get("edition") or "1"), "audience": str(meta.get("audience") or "General")})
    warnings = commercial_warnings(meta)
    if warnings:
        improvements.extend(warnings)
    return {
        "rule_version": RULE_VERSION,
        "commercial_profile_version": PROFILE_VERSION,
        "assessed_at": datetime.now().isoformat(timespec="seconds"),
        "book_title": str(meta.get("title") or "Untitled Puzzle Book"),
        "puzzle_type": puzzle_type_for(meta),
        "topic": str(meta.get("theme") or meta.get("detected_topic") or ""),
        "commercial_value_score": value_score,
        "score_definition": "Local buyer-value clarity score; it is not a sales, ranking, or profitability prediction.",
        "strengths": strengths,
        "improvements": improvements,
        "commercial_archetypes": archetypes,
        "puzzle_commercial_profile": PUZZLE_PROFILES[profile_key].to_dict(),
        "puzzle_format_fit": puzzle_format_fit(meta),
        "marketplace_fit": all_marketplace_fit,
        "marketplace_breadth": {
            "strong": [value["marketplace"] for value in all_marketplace_fit.values() if value["fit"] == "Strong Fit"],
            "moderate": [value["marketplace"] for value in all_marketplace_fit.values() if value["fit"] == "Moderate Fit"],
        },
        "micro_theme_capacity": mini_theme_capacity(meta) if profile_key == "word_search" else None,
        "marketplace_strategies": marketplace_strategies,
        "commercial_warnings": warnings,
        "metrics_notice": "Fit points are internal planning heuristics only. No demand, search-volume, competition, sales, rank, or profit metric is claimed.",
        "marketplaces": results,
    }


def render_commercial_report(assessment: dict[str, Any]) -> str:
    lines = [
        "MARKETPLACE COMMERCIAL INTELLIGENCE REVIEW",
        "=" * 64,
        f"Rule version: {assessment['rule_version']}",
        f"Book: {assessment['book_title']}",
        f"Puzzle type: {assessment['puzzle_type']}",
        f"Topic: {assessment['topic'] or 'Needs a verified topic'}",
        "Archetype: " + " + ".join(item["label"] for item in assessment.get("commercial_archetypes", [])),
        f"Buyer-value clarity: {assessment['commercial_value_score']}/100",
        assessment["score_definition"], "",
        "STRENGTHS",
    ]
    lines += [f"- {value}" for value in assessment["strengths"]] or ["- Add verified product details before review."]
    lines += ["", "IMPROVEMENTS"]
    lines += [f"- {value}" for value in assessment["improvements"]] or ["- No additional local buyer-value improvement is required."]
    lines += ["", "MARKETPLACE FIT (INTERNAL HEURISTIC — NOT SALES DATA)"]
    for item in assessment.get("marketplace_fit", {}).values():
        lines.append(f"- {item['marketplace']}: {item['fit']} — {'; '.join(item['reasons'])}")
    for key, item in assessment["marketplaces"].items():
        lines += ["", MARKET_LABELS[key].upper(), "-" * 64,
                  f"Format: {item['format']}", f"Buyer value focus: {item['buyer_value_focus']}",
                  f"Suggested starting price: ${float(item['suggested_price'] or 0):.2f}",
                  f"Price note: {item['pricing_note']}", f"Route: {item['route_note']}",
                  f"Listing quality: {item['listing_quality']['score']}/100 — {item['listing_quality']['label']}",
                  "Keywords / discovery terms:"]
        lines += [f"- {value}" for value in item["keywords"]]
        lines += ["Commercial review notes:"] + [f"- {value}" for value in item["listing_quality"]["notes"]]
        if item["missing_file_facts"]:
            lines.append("- Missing package facts: " + ", ".join(item["missing_file_facts"]))
        if item["overlap_warning"]:
            lines.append("- " + item["overlap_warning"])
        if item["a_plus_plan"]:
            lines += ["A+ content direction (after publication):"] + [f"- {module['name']}: {module['copy']}" for module in item["a_plus_plan"]["modules"]]
    lines += ["", "This review creates local planning guidance only. It does not upload, publish, change a price, or guarantee commercial performance.", ""]
    return "\n".join(lines)


def write_commercial_report(book: dict, target: Path, marketplace: str | None = None) -> Path:
    target.mkdir(parents=True, exist_ok=True)
    assessment = commercial_assessment(book, marketplace)
    (target / "MARKETPLACE_COMMERCIAL_INTELLIGENCE.json").write_text(json.dumps(assessment, indent=2), encoding="utf-8")
    text = target / "MARKETPLACE_COMMERCIAL_INTELLIGENCE.txt"
    text.write_text(render_commercial_report(assessment), encoding="utf-8")
    return text


def write_a_plus_asset_kit(book: dict, package: Path) -> Path:
    """Create a local KDP A+ planning kit from verified package files.

    These are upload-ready *creative assets*, not a claim that Amazon has
    approved or published them.  The source cover and a real interior page are
    used so the kit cannot accidentally promise something not in the book.
    """
    from PIL import Image, ImageDraw, ImageFont
    import pypdfium2 as pdfium

    meta = dict(book.get("metadata") or book or {})
    title = str(meta.get("title") or "Puzzle Book")
    kind = puzzle_type_for(meta)
    topic = str(meta.get("theme") or meta.get("detected_topic") or "themed")
    count = int(meta.get("puzzle_count") or 0)
    root = package / "06_KDP_A_PLUS"
    root.mkdir(parents=True, exist_ok=True)
    cover_path = package / "03_PREVIEWS" / "front_cover.png"
    if not cover_path.is_file():
        raise FileNotFoundError(f"A+ kit needs the completed front cover: {cover_path}")
    interior = package / "01_PRINT_UPLOADS" / "interior.pdf"
    if not interior.is_file():
        raise FileNotFoundError(f"A+ kit needs the completed interior: {interior}")

    canvas_size = (1500, 900)
    background, ink, accent = "#f7f2e9", "#19242d", "#137c74"
    try:
        title_font = ImageFont.truetype("arialbd.ttf", 62)
        body_font = ImageFont.truetype("arial.ttf", 34)
        small_font = ImageFont.truetype("arialbd.ttf", 27)
    except OSError:
        title_font = body_font = small_font = ImageFont.load_default()

    def base() -> tuple[Image.Image, ImageDraw.ImageDraw]:
        image = Image.new("RGB", canvas_size, background)
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, canvas_size[0], 20), fill=accent)
        return image, draw

    def text_block(draw: ImageDraw.ImageDraw, heading: str, lines: list[str], x: int = 80, y: int = 85) -> None:
        draw.text((x, y), heading, fill=ink, font=title_font)
        offset = y + 110
        for line in lines:
            draw.text((x, offset), line, fill=ink, font=body_font)
            offset += 55

    cover = Image.open(cover_path).convert("RGB")
    cover.thumbnail((600, 760))
    hero, draw = base()
    hero.paste(cover, (820, 85))
    text_block(draw, title, [f"{count} {kind} challenges", f"A focused {topic} collection", "Solutions included"], 80, 150)
    hero.save(root / "whats_inside.png")

    pdf = pdfium.PdfDocument(str(interior))
    page = pdf[1 if len(pdf) > 1 else 0]
    rendered = page.render(scale=1.5).to_pil().convert("RGB")
    rendered.thumbnail((760, 720))
    sample, draw = base()
    text_block(draw, "A real page from inside", ["A clear sample from the completed book", "Review every page before publishing"], 70, 105)
    sample.paste(rendered, (700, 150))
    sample.save(root / "sample_puzzles.png")
    pdf.close()

    features, draw = base()
    text_block(draw, "Made for an enjoyable puzzle break", [f"• {count} {kind} puzzles", "• Clear, reader-friendly layout", "• Verified solutions included", "• A focused theme, not generic filler"], 100, 145)
    features.save(root / "features.png")

    series, draw = base()
    draw.text((80, 110), "More from Slade Puzzles", fill=ink, font=title_font)
    draw.text((80, 235), "Pair this title with a complementary themed puzzle book.", fill=ink, font=body_font)
    draw.text((80, 295), "Only add actual, published companion titles in KDP A+ Content.", fill=ink, font=body_font)
    thumb = cover.copy(); thumb.thumbnail((360, 455)); series.paste(thumb, (1010, 190))
    series.save(root / "series_comparison.png")

    assessment = commercial_assessment(book, "amazon")
    sheet = root / "KDP_A_PLUS_PUBLISHING_SHEET.txt"
    sheet.write_text(
        "KDP A+ CONTENT — LOCAL ASSET KIT\n\n"
        f"Book: {title}\n"
        "Status: Local assets prepared. Upload only after the paperback is published and eligible in KDP.\n\n"
        "USE THESE ASSETS\n"
        "1. whats_inside.png — cover plus verified book features\n"
        "2. sample_puzzles.png — real completed interior page\n"
        "3. features.png — reader benefits drawn from verified package facts\n"
        "4. series_comparison.png — replace the generic companion direction with real published titles only\n\n"
        "COPY DIRECTION\n"
        + "\n".join(f"- {module['name']}: {module['copy']}" for module in assessment["marketplaces"]["amazon"]["a_plus_plan"]["modules"])
        + "\n\nFinal check: confirm current KDP A+ requirements, product eligibility, and image specifications before upload. This kit does not publish or submit anything.\n",
        encoding="utf-8",
    )
    manifest = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_cover": str(cover_path),
        "source_interior": str(interior),
        "assets": ["whats_inside.png", "sample_puzzles.png", "features.png", "series_comparison.png"],
        "status": "LOCAL_ASSETS_READY_FOR_HUMAN_KDP_A_PLUS_REVIEW",
    }
    (root / "a_plus_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return root
