"""Versioned, local-only commercial planning profiles.

These profiles describe product coherence and marketplace merchandising fit.
They do not contain demand, sales, competition, or profitability metrics and
they never override production/content gates.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any


PROFILE_VERSION = "marketplace-commercial-v2-2026.09"


@dataclass(frozen=True)
class PuzzleCommercialProfile:
    puzzle_type: str
    primary_buying_triggers: tuple[str, ...]
    secondary_triggers: tuple[str, ...]
    strong_directions: tuple[str, ...]
    weak_patterns: tuple[str, ...]
    content_requirements: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


PUZZLE_PROFILES = {
    "word_search": PuzzleCommercialProfile(
        "Word Search", ("theme_specificity", "audience_fit", "use_case"),
        ("large_print", "puzzle_count", "giftability"),
        ("nostalgia", "hobbies", "travel", "history", "seasonal", "seniors", "relaxation"),
        ("generic_adults_positioning", "theme_only_cover_without_content_depth"),
        ("topic-relevant word pool", "grounded mini-themes", "repeat-free allocation", "complete solutions"),
    ),
    "sudoku": PuzzleCommercialProfile(
        "Sudoku", ("quantity", "difficulty", "readability", "variant"),
        ("large_print", "progression", "device_fit"),
        ("progressive difficulty", "large print", "numbers", "letters", "shapes", "mixed variants"),
        ("cosmetic_theme_only", "unstated_difficulty", "ordinary_undifferentiated_sudoku"),
        ("unique solutions", "truthful variant", "readable grids", "difficulty progression"),
    ),
    "cryptogram": PuzzleCommercialProfile(
        "Cryptogram", ("content_identity", "theme"),
        ("large_print", "audience", "puzzle_count"),
        ("mystery", "inspiration", "public-domain sayings", "original sayings", "nostalgia", "history", "faith"),
        ("unclear_quote_rights", "generic_unrelated_messages", "weak_content_identity"),
        ("rights-safe text", "cohesive messages", "accurate solutions", "source provenance"),
    ),
    "scramble_trivia": PuzzleCommercialProfile(
        "Word Scramble + Trivia", ("occasion", "theme", "social_memory_experience"),
        ("group_use", "fact_quality", "bonus_rounds"),
        ("decades", "birthdays", "holidays", "travel", "history", "classic cars", "camping", "road trips"),
        ("generic_scramble_positioning", "unverified_trivia", "weak_experience_identity"),
        ("verified facts", "cohesive theme", "varied prompts", "accurate solutions"),
    ),
    "mixed": PuzzleCommercialProfile(
        "Mixed Brain Games", ("variety", "value", "strong_concept"),
        ("audience", "screen_free_use", "section_transitions"),
        ("nostalgia", "travel", "seniors", "hobbies", "holidays", "family activities", "relaxation"),
        ("random_assortment", "generic_starter_content", "unbalanced_sections"),
        ("thematic cohesion", "balanced puzzle types", "section title pages", "cross-format content capacity"),
    ),
}


ARCHETYPES = {
    "nostalgia": {"label": "Nostalgia", "signals": ("nostalgia", "retro", "vintage", "1950", "1960", "1970", "1980", "1990", "decade"), "preferred": ("word_search", "mixed", "scramble_trivia", "cryptogram"), "audience": "adults and seniors", "visual": "era-specific color, type, and rights-safe cultural cues", "content": "era-grounded vocabulary or messages", "marketplaces": ("amazon", "etsy", "payhip"), "listing": "memory, era identity, giftability", "merchandising": "era cues plus real puzzle previews", "risks": "brands, celebrities, franchises, or cosmetic-only nostalgia", "format": "large print when promised"},
    "senior_large_print": {"label": "Senior Large Print", "signals": ("senior", "large print", "easy read", "older adult"), "preferred": ("word_search", "sudoku", "cryptogram", "mixed"), "audience": "seniors and readers seeking comfortable print", "visual": "high contrast, clean hierarchy, low clutter", "content": "comfortable navigation and appropriate progression", "marketplaces": ("amazon", "barnes_noble", "lulu"), "listing": "readability backed by real typography", "merchandising": "large-print close-up from a real page", "risks": "unsubstantiated senior or large-print claim", "format": "large type, generous spacing, strong contrast"},
    "hobby": {"label": "Hobby Enthusiast", "signals": ("garden", "car", "bird", "camp", "hiking", "craft", "cooking", "baking", "pet", "sport"), "preferred": ("word_search", "scramble_trivia", "mixed"), "audience": "enthusiasts and gift buyers", "visual": "recognizable topic-specific approved art", "content": "credible hobby vocabulary and subtopics", "marketplaces": ("amazon", "etsy", "payhip"), "listing": "enthusiast identity and screen-free use", "merchandising": "topic-specific cover and interior examples", "risks": "generic filler or unrelated clipart", "format": "match complexity to audience"},
    "travel": {"label": "Travel", "signals": ("travel", "road trip", "national park", "city", "state", "country", "adventure"), "preferred": ("word_search", "scramble_trivia", "mixed"), "audience": "travelers, families, and armchair explorers", "visual": "place-specific approved imagery", "content": "geography, culture, nature, and travel experience", "marketplaces": ("amazon", "etsy", "payhip"), "listing": "destination and travel use case", "merchandising": "destination cover plus portable activity angle", "risks": "place-name repetition or generic travel content", "format": "portable or full-size according to plan"},
    "seasonal": {"label": "Seasonal", "signals": ("christmas", "holiday", "halloween", "thanksgiving", "summer", "winter", "spring", "autumn", "fall"), "preferred": ("word_search", "scramble_trivia", "mixed"), "audience": "seasonal activity and gift buyers", "visual": "seasonally recognizable, non-infringing imagery", "content": "traditions, weather, food, activities, and occasion-specific vocabulary", "marketplaces": ("amazon", "etsy", "payhip"), "listing": "occasion, gathering, gift, and activity use", "merchandising": "seasonal thumbnail and printable-use graphics", "risks": "late timing or thin repetitive vocabulary", "format": "clear seasonal promise"},
    "history": {"label": "History", "signals": ("history", "war", "heritage", "historic", "american moments"), "preferred": ("word_search", "cryptogram", "scramble_trivia", "mixed"), "audience": "history readers and learners", "visual": "period-appropriate rights-safe imagery", "content": "fact-checked historical terms or public-domain/original messages", "marketplaces": ("amazon", "barnes_noble", "ingram"), "listing": "specific period, learning, and challenge", "merchandising": "period identity plus real content sample", "risks": "rights, factual errors, or overbroad periods", "format": "professional reference-friendly layout"},
    "giftable": {"label": "Giftable", "signals": ("gift", "birthday", "mom", "dad", "grandma", "grandpa"), "preferred": ("word_search", "sudoku", "cryptogram", "scramble_trivia", "mixed"), "audience": "gift buyers and puzzle fans", "visual": "clear recipient and occasion at thumbnail size", "content": "complete, polished experience", "marketplaces": ("amazon", "etsy", "payhip"), "listing": "recipient, occasion, and value", "merchandising": "gift-ready benefits without unsupported claims", "risks": "generic recipient label without product substance", "format": "finished-book presentation"},
    "relaxation": {"label": "Relaxation", "signals": ("relax", "calm", "mindful", "cozy", "stress", "quiet"), "preferred": ("word_search", "sudoku", "mixed"), "audience": "adults seeking screen-free downtime", "visual": "calm, readable, uncluttered", "content": "consistent pacing and comfortable progression", "marketplaces": ("amazon", "etsy", "payhip"), "listing": "screen-free routine and enjoyable pace", "merchandising": "readability and calm-use scenes", "risks": "medical or therapeutic claims", "format": "comfortable spacing"},
    "family_group": {"label": "Family / Group Activity", "signals": ("family", "group", "party", "classroom", "road trip", "social", "team"), "preferred": ("scramble_trivia", "mixed", "word_search"), "audience": "families, groups, and hosts", "visual": "lively, inclusive, occasion-led", "content": "shared-play prompts and appropriate difficulty", "marketplaces": ("etsy", "payhip", "amazon"), "listing": "occasion and shared experience", "merchandising": "what-you-get and group-use graphics", "risks": "age mismatch or solitary content sold as group play", "format": "easy navigation and reproducible pages for licensed digital use"},
    "educational": {"label": "Educational", "signals": ("grade", "school", "student", "vocabulary", "learn", "education", "classroom"), "preferred": ("word_search", "scramble_trivia", "cryptogram", "mixed"), "audience": "students, families, and educators", "visual": "age-appropriate academic cues", "content": "grade/topic alignment and accurate supporting facts", "marketplaces": ("amazon", "etsy", "payhip"), "listing": "skill, grade, and use setting", "merchandising": "real worksheet/puzzle samples", "risks": "unsupported curriculum or grade claims", "format": "age-appropriate typography and instructions"},
    "challenge": {"label": "Challenge / Expert", "signals": ("expert", "hard", "challenge", "advanced", "difficult"), "preferred": ("sudoku", "cryptogram", "mixed", "word_search"), "audience": "experienced solvers", "visual": "confident, focused, uncluttered", "content": "verified challenge progression", "marketplaces": ("amazon", "barnes_noble", "payhip"), "listing": "difficulty and progression", "merchandising": "sample challenge and solution proof", "risks": "difficulty claim without measurement", "format": "readable despite higher complexity"},
    "device_friendly": {"label": "Device-Friendly Digital", "signals": ("digital", "tablet", "device", "download", "printable"), "preferred": ("sudoku", "word_search", "mixed"), "audience": "digital-download customers", "visual": "clear digital disclosure and legible previews", "content": "customer-safe PDF and device/print instructions", "marketplaces": ("etsy", "payhip", "direct"), "listing": "file format, delivery, printing, and use", "merchandising": "digital badge and actual downloadable pages", "risks": "implying physical shipment", "format": "screen and home-printer legibility"},
    "faith_inspiration": {"label": "Faith / Inspiration", "signals": ("faith", "bible", "scripture", "inspiration", "gratitude"), "preferred": ("word_search", "cryptogram", "mixed"), "audience": "faith-centered puzzle readers and gift buyers", "visual": "respectful, calm, topic-appropriate", "content": "rights-safe scripture or original inspirational content", "marketplaces": ("amazon", "etsy", "payhip"), "listing": "faith identity, reflection, and gift use", "merchandising": "respectful cover and real page samples", "risks": "translation rights or unsupported attribution", "format": "readable, reflective presentation"},
}


MARKETPLACE_PROFILES = {
    "amazon": {"label": "Amazon KDP", "discovery": "search and detail-page conversion", "title": "accurate, specific title and subtitle", "description": "buyer-facing physical-book description", "keywords": "seven distinct backend keyword phrases", "images": "cover, Look Inside, and eligible A+ plan", "fit": "physical paperback", "pricing": "confirm live print cost and royalty", "bundles": "series cross-sell rather than digital ZIP bundle", "assets": ("print interior", "printer-specific full wrap", "listing kit")},
    "etsy": {"label": "Etsy", "discovery": "visual merchandising, tags, occasions, and buyer intent", "title": "readable product title; avoid keyword stuffing", "description": "conversion opening, contents, use cases, and download instructions", "keywords": "13 concise tags plus relevant attributes", "images": "ten-image real-product merchandising plan", "fit": "digital printable or clearly disclosed physical item", "pricing": "digital promotional starting point; verify fees", "bundles": "strong when files and license are clear", "assets": ("customer-safe PDF", "real previews", "digital disclosure", "publishing sheet")},
    "payhip": {"label": "Payhip", "discovery": "seller-led branded direct traffic", "title": "clear branded product identity", "description": "landing-page copy distinct from marketplace copy", "keywords": "SEO title/description and storefront tags", "images": "cover, gallery, contents, and real previews", "fit": "digital direct sale, collection, bundle, or lead magnet", "pricing": "direct digital starting point; verify fees and tax settings", "bundles": "strong for related collections and cross-sells", "assets": ("customer-safe PDF", "gallery plan", "store/product setup sheets")},
    "barnes_noble": {"label": "Barnes & Noble Press", "discovery": "professional book metadata and retailer presentation", "title": "bibliographic title/subtitle", "description": "professional bookstore description", "keywords": "accurate subject and audience terms", "images": "printer-ready cover built from current template", "fit": "physical paperback", "pricing": "confirm current calculator and minimums", "bundles": "series metadata rather than digital bundle", "assets": ("print interior", "B&N-specific cover", "metadata sheet")},
    "ingram": {"label": "IngramSpark", "discovery": "distribution metadata and bookseller/library channels", "title": "bibliographic consistency", "description": "professional distribution copy", "keywords": "BISAC/Thema and accurate keywords", "images": "printer-specific cover", "fit": "physical distribution", "pricing": "confirm print cost, wholesale discount, and returns choices", "bundles": "series metadata", "assets": ("print interior", "Ingram-specific cover", "distribution metadata")},
    "lulu": {"label": "Lulu", "discovery": "fulfillment and direct-commerce infrastructure", "title": "accurate product metadata", "description": "direct-sale product description", "keywords": "storefront metadata where supported", "images": "Lulu-template cover and product preview", "fit": "print/direct fulfillment", "pricing": "confirm live print cost, taxes, and distribution", "bundles": "direct-sale collections where supported", "assets": ("print interior", "Lulu-specific cover", "fulfillment notes")},
    "bookvault": {"label": "Bookvault", "discovery": "print fulfillment rather than assumed organic discovery", "title": "accurate product metadata", "description": "direct-sale product description", "keywords": "storefront metadata where applicable", "images": "Bookvault-template cover", "fit": "print/direct fulfillment", "pricing": "confirm live manufacturing and shipping costs", "bundles": "storefront cross-sells", "assets": ("print interior", "Bookvault-specific cover", "fulfillment notes")},
    "direct": {"label": "Direct Storefront", "discovery": "seller-owned traffic, collections, and cross-sells", "title": "brand-consistent product name", "description": "landing-page copy and product specifications", "keywords": "SEO metadata without stuffing", "images": "hero, gallery, real previews, and clear format disclosure", "fit": "digital or physical according to fulfillment", "pricing": "confirm store fees, fulfillment, and taxes", "bundles": "strong for coherent product families", "assets": ("product files", "gallery", "specifications", "support instructions")},
}


def normalize_puzzle_type(value: object) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", str(value or "word_search").casefold()).strip("_")
    aliases = {"wordsearch": "word_search", "word_search_puzzle": "word_search", "word_scramble_trivia": "scramble_trivia", "word_scramble_and_trivia": "scramble_trivia", "scramble": "scramble_trivia", "mixed_brain_games": "mixed", "mixed_brain_game": "mixed", "sudoku_book": "sudoku", "cryptograms": "cryptogram"}
    return aliases.get(text, text if text in PUZZLE_PROFILES else "word_search")


def product_text(meta: dict) -> str:
    return " ".join(str(meta.get(key) or "") for key in ("title", "subtitle", "theme", "detected_topic", "topic", "audience", "series", "description", "buyer_angle")).casefold()


def infer_archetypes(meta: dict, limit: int = 3) -> list[dict[str, Any]]:
    text = product_text(meta)
    kind = normalize_puzzle_type(meta.get("puzzle_type_id") or meta.get("puzzle_type"))
    ranked = []
    for key, profile in ARCHETYPES.items():
        matched = [signal for signal in profile["signals"] if signal in text]
        points = len(matched) * 3 + (2 if kind in profile["preferred"] else 0)
        if key == "senior_large_print" and bool(meta.get("large_print")): points += 4
        if key == "device_friendly" and bool(meta.get("digital") or meta.get("printable_pdf")): points += 3
        if matched or points >= 4:
            ranked.append({"id": key, "label": profile["label"], "internal_heuristic_points": points, "matched_signals": matched, "profile": {k: v for k, v in profile.items() if k != "signals"}})
    if not ranked:
        ranked.append({"id": "giftable", "label": ARCHETYPES["giftable"]["label"], "internal_heuristic_points": 1, "matched_signals": [], "profile": {k: v for k, v in ARCHETYPES["giftable"].items() if k != "signals"}})
    return sorted(ranked, key=lambda row: (-row["internal_heuristic_points"], row["label"]))[:limit]


def puzzle_format_fit(meta: dict) -> dict[str, Any]:
    archetypes = infer_archetypes(meta, 5)
    scores = {key: 0 for key in PUZZLE_PROFILES}
    reasons = {key: [] for key in PUZZLE_PROFILES}
    for archetype in archetypes:
        preferred = ARCHETYPES[archetype["id"]]["preferred"]
        for position, kind in enumerate(preferred):
            scores[kind] += max(1, 5 - position)
            reasons[kind].append(f"Fits the {archetype['label']} archetype")
    ranked = sorted(scores, key=lambda key: (-scores[key], key))
    return {"recommended": [{"puzzle_type": key, "label": PUZZLE_PROFILES[key].puzzle_type, "internal_heuristic_points": scores[key], "reasons": reasons[key]} for key in ranked], "notice": "These are local product-fit heuristics, not demand or sales predictions."}


def commercial_warnings(meta: dict) -> list[str]:
    text = product_text(meta); kind = normalize_puzzle_type(meta.get("puzzle_type_id") or meta.get("puzzle_type")); warnings = []
    topic = str(meta.get("theme") or meta.get("detected_topic") or meta.get("topic") or "").strip().casefold()
    if kind == "word_search" and (not topic or topic in {"general", "adults", "general interest"}): warnings.append("Weak Differentiation: add a specific theme, audience, use case, or series identity.")
    if kind == "sudoku" and any(term in text for term in ("space", "holiday", "travel", "garden")) and not any(term in text for term in ("letter", "shape", "symbol", "progressive", "variant")): warnings.append("Sudoku Theme Risk: the theme appears cosmetic unless the solving variant, progression, or audience experience is meaningfully different.")
    if kind == "cryptogram" and not any(meta.get(key) for key in ("quote_source", "content_source", "rights_status", "source_provenance")): warnings.append("Cryptogram Rights Review: verify that every message is original, public domain, or properly licensed.")
    if kind == "scramble_trivia" and not any(meta.get(key) for key in ("facts_verified", "trivia_sources", "source_provenance")): warnings.append("Trivia Verification: confirm facts and sources before final approval.")
    if kind == "mixed" and not bool(meta.get("section_theme_cohesion") or meta.get("content_plan") or meta.get("book_plan")): warnings.append("Mixed Book Cohesion Risk: verify that every puzzle section supports the same product promise.")
    if "senior" in text and not bool(meta.get("large_print")): warnings.append("Senior Claim Review: the product is positioned for seniors but large-print/readability evidence is not recorded.")
    return warnings


def marketplace_fit(meta: dict) -> dict[str, dict[str, Any]]:
    text = product_text(meta); archetypes = infer_archetypes(meta, 5); kind = normalize_puzzle_type(meta.get("puzzle_type_id") or meta.get("puzzle_type"))
    files = meta.get("files") if isinstance(meta.get("files"), dict) else {}
    digital = bool(meta.get("digital") or files.get("printable_pdf") or files.get("digital_pdf")); print_ready = bool(files.get("print_interior") and files.get("print_cover"))
    topic_specific = bool(str(meta.get("theme") or meta.get("detected_topic") or meta.get("topic") or "").strip().casefold() not in {"", "general", "general interest"})
    output = {}
    for market, profile in MARKETPLACE_PROFILES.items():
        points = 2 + int(topic_specific) + int(bool(meta.get("puzzle_count")))
        reasons = [f"{PUZZLE_PROFILES[kind].puzzle_type} format is clearly identified"]
        preferred_by = [a["label"] for a in archetypes if market in ARCHETYPES[a["id"]]["marketplaces"]]
        if preferred_by: points += 2; reasons.append("Fits " + ", ".join(preferred_by[:2]))
        if market in {"etsy", "payhip", "direct"}:
            points += 2 if digital else 0; reasons.append("A customer-safe digital file is recorded" if digital else "A customer-safe digital file is still needed")
        else:
            points += 2 if print_ready else 0; reasons.append("Print files are recorded" if print_ready else "Printer-ready files are still needed")
        if market == "etsy" and kind in {"scramble_trivia", "mixed", "word_search"}: points += 1
        if market in {"barnes_noble", "ingram"} and not str(meta.get("isbn") or "").strip(): reasons.append("ISBN/edition metadata needs review")
        label = "Strong Fit" if points >= 7 else "Moderate Fit" if points >= 4 else "Limited Fit"
        output[market] = {"marketplace": profile["label"], "fit": label, "internal_heuristic_points": points, "reasons": reasons, "profile": profile}
    return output


def mini_theme_capacity(meta: dict) -> dict[str, Any]:
    raw = meta.get("mini_themes") or meta.get("micro_themes") or meta.get("mini_theme_map") or []
    rows = []
    if isinstance(raw, dict):
        iterable = raw.items()
    elif isinstance(raw, list):
        iterable = [(str(item.get("name") or item.get("title") or f"Theme {index + 1}"), item) if isinstance(item, dict) else (str(item), {}) for index, item in enumerate(raw)]
    else:
        iterable = []
    words_per = max(1, int(meta.get("words_per_puzzle") or 12))
    for name, value in iterable:
        if isinstance(value, dict): count = int(value.get("eligible_words") or value.get("word_count") or len(value.get("words") or []))
        elif isinstance(value, list): count = len(value)
        else: count = 0
        rows.append({"mini_theme": str(name), "eligible_words": count, "supportable_puzzles": count // words_per, "weak": count < words_per})
    total = sum(row["eligible_words"] for row in rows); largest = max((row["eligible_words"] for row in rows), default=0)
    return {"breadth": len(rows), "eligible_words": total, "mini_themes": rows, "weak_mini_themes": [row["mini_theme"] for row in rows if row["weak"]], "fallback_concentration_risk": bool(total and largest / total > .40), "repeat_pressure": "high" if total and total < int(meta.get("puzzle_count") or 0) * words_per else "unknown" if not total else "controlled", "notice": "Capacity reflects only the mini-theme evidence supplied by Content Intelligence."}


FIRST_PARTY_PERFORMANCE_FIELDS = {
    "marketplace": "optional text", "listing_date": "optional ISO date", "price": "optional decimal",
    "promotion": "optional text", "views": "optional integer", "clicks": "optional integer",
    "favorites": "optional integer", "units": "optional integer", "revenue": "optional decimal",
    "reviews": "optional integer", "conversion_rate": "optional decimal when supplied",
    "listing_version": "optional text", "cover_version": "optional text",
}

UNSUPPORTED_METRIC_KEYS = {
    "search_volume", "monthly_sales", "competition_score", "rank_probability",
    "guaranteed_profit", "projected_bestseller", "competitor_revenue",
}


def unsupported_metric_keys(payload: Any) -> list[str]:
    """Return fabricated-market field names, while allowing truthful disclaimers."""
    found: set[str] = set()
    if isinstance(payload, dict):
        for key, value in payload.items():
            normalized = re.sub(r"[^a-z0-9]+", "_", str(key).casefold()).strip("_")
            if normalized in UNSUPPORTED_METRIC_KEYS:
                found.add(normalized)
            found.update(unsupported_metric_keys(value))
    elif isinstance(payload, (list, tuple, set)):
        for value in payload:
            found.update(unsupported_metric_keys(value))
    return sorted(found)


def profile_snapshot() -> dict[str, Any]:
    return {"version": PROFILE_VERSION, "puzzle_profiles": {key: value.to_dict() for key, value in PUZZLE_PROFILES.items()}, "archetypes": ARCHETYPES, "marketplaces": MARKETPLACE_PROFILES, "first_party_performance_schema": FIRST_PARTY_PERFORMANCE_FIELDS, "notice": "All fit points are transparent internal heuristics. No external demand, sales, competition, ranking, or profit metric is present."}


def idea_commercial_guidance(idea: str) -> dict[str, Any]:
    """Explain a plain-English idea without creating or claiming demand."""
    text = " ".join(str(idea or "").split()).strip()
    lowered = text.casefold()
    explicit = "mixed" if "mixed" in lowered or "brain game" in lowered else "scramble_trivia" if "scramble" in lowered or "trivia" in lowered else "cryptogram" if "cryptogram" in lowered or "cipher" in lowered else "sudoku" if "sudoku" in lowered else "word_search" if "word search" in lowered or "word find" in lowered else ""
    meta = {"title": text, "theme": text, "audience": "seniors" if "senior" in lowered else "kids" if " kid" in " " + lowered else "adults", "large_print": "large print" in lowered, "puzzle_type": explicit or "word_search"}
    formats = puzzle_format_fit(meta)["recommended"]
    if explicit:
        formats = sorted(formats, key=lambda row: (row["puzzle_type"] != explicit, -row["internal_heuristic_points"]))
    archetypes = infer_archetypes(meta)
    return {
        "idea": text,
        "archetypes": [item["label"] for item in archetypes],
        "best_format": formats[0], "alternative_formats": formats[1:3],
        "marketplace_fit": marketplace_fit(meta), "warnings": commercial_warnings(meta),
        "next_safe_step": "Check strict content capacity and catalog differentiation before approving a BookPlan.",
        "notice": "Product-fit guidance only; no demand, sales, rank, competition, or profit claim is made.",
    }


def render_idea_guidance(guidance: dict[str, Any]) -> str:
    best = guidance["best_format"]
    markets = sorted(guidance["marketplace_fit"].values(), key=lambda item: (-item["internal_heuristic_points"], item["marketplace"]))[:3]
    lines = ["Commercial Fit", "", "Archetype: " + " + ".join(guidance["archetypes"]),
             f"Best format fit: {best['label']}", "Why: " + "; ".join(best["reasons"] or ["The idea has a clear audience or use-case direction."]),
             "", "Best marketplace fit:"]
    lines.extend(f"• {item['marketplace']} — {item['fit']}" for item in markets)
    if guidance["warnings"]:
        lines += ["", "Commercial warnings:"] + [f"• {item}" for item in guidance["warnings"]]
    lines += ["", "Next safe step: " + guidance["next_safe_step"], guidance["notice"]]
    return "\n".join(lines)
