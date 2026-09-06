"""One reusable metadata engine for every marketplace."""
from __future__ import annotations

import re

from .puzzle_types import resolve_puzzle_type


# Every generator shares this profile map.  It keeps a Sudoku listing from
# sounding like a word-search book and gives every platform accurate language.
PUZZLE_PROFILES = {
    "Word Search": ("word-search puzzles", "themed word-search grids", "a complete answer key", "Games & Activities / Word & Word Search", ["word search puzzles", "word find book", "word search with answers", "large print word search", "relaxing word puzzles", "screen free activity", "puzzle gift"], ["word search", "word find", "puzzle book", "large print", "puzzle gift", "brain games", "word puzzles"]),
    "Sudoku": ("logic puzzles", "verified Sudoku grids", "full solutions", "Games & Activities / Puzzles", ["large print sudoku", "sudoku with solutions", "logic puzzles adults", "number puzzle book", "brain games adults", "screen free activity", "puzzle gift"], ["sudoku", "logic puzzles", "number puzzles", "large print", "brain games", "puzzle book", "sudoku answers"]),
    "Cryptogram": ("code-breaking puzzles", "cryptogram messages to decode", "complete decoded solutions", "Games & Activities / Puzzles", ["cryptogram puzzles", "code breaking games", "cipher puzzle book", "cryptograms with answers", "word logic games", "brain games adults", "puzzle gift"], ["cryptogram", "cipher puzzles", "code breaker", "word puzzles", "brain games", "puzzle book", "logic games"]),
    "Word Scramble + Trivia": ("word-and-trivia challenges", "word scrambles paired with trivia", "a complete answer key", "Games & Activities / Word & Word Search", ["word scramble puzzles", "trivia question book", "word games adults", "general knowledge quiz", "scramble with answers", "brain games adults", "puzzle gift"], ["word scramble", "trivia games", "word games", "brain games", "puzzle book", "quiz book", "answer key"]),
    "Mixed Brain Games": ("variety brain games", "a mix of Sudoku, Cryptograms, and word-and-trivia games", "complete answers for every section", "Games & Activities / Puzzles", ["mixed brain games", "variety puzzle book", "sudoku cryptogram games", "logic and word games", "brain games adults", "puzzle book with answers", "screen free activity"], ["brain games", "mixed puzzles", "sudoku games", "cryptogram", "word games", "puzzle book", "brain teasers"]),
}

# These phrases are too vague to carry a marketplace listing by themselves.
# They may be true, but buyer-facing copy should say what makes *this* puzzle
# collection distinctive.  The audit below catches them when they crowd out
# the book's topic language.
GENERIC_DISCOVERY_TERMS = {
    "screen free activity", "puzzle gift", "brain games adults", "puzzle book",
    "word puzzles", "number puzzle book", "logic games", "answer key",
}


def _legacy_generated_copy(value: object) -> bool:
    """Recognize only the old boilerplate this app generated itself.

    Publisher-written descriptions remain untouched.  These markers came from
    prior automatic templates and let a normal catalog refresh upgrade them
    to the newer topic-led copy without pretending a human's writing is ours.
    """
    text = str(value or "").casefold()
    return any(marker in text for marker in (
        "collection inspired by", "satisfying word play", "makes a satisfying screen-free break",
        "ready-to-enjoy", "relaxing addition to your own puzzle shelf",
    ))

TOPIC_DISCOVERY_TERMS = {
    "space": ("solar system puzzles", "planet and moon facts", "constellation challenges", "astronomy word play"),
    "garden": ("flower and plant puzzles", "vegetable garden words", "herb and homestead terms", "backyard growing fun"),
    "travel": ("road trip puzzles", "world landmarks", "national park adventures", "vacation activity book"),
    "park": ("trail and wildlife puzzles", "scenic landmark challenges", "outdoor adventure words", "nature travel games"),
    "pet": ("cat and dog puzzles", "animal care words", "house pet activities", "pet lover games"),
    "animal": ("wildlife word challenges", "animal facts and puzzles", "nature activity book", "creature vocabulary"),
    "holiday": ("seasonal celebration puzzles", "festive tradition games", "holiday activity book", "cozy winter challenges"),
    "christmas": ("winter holiday puzzles", "festive tradition games", "Christmas activity book", "seasonal word challenges"),
    "history": ("American history puzzles", "historic event challenges", "heritage activity book", "history vocabulary games"),
    "car": ("car and truck puzzles", "road trip word games", "automotive hobby activity", "vehicle enthusiast puzzles"),
    "vehicle": ("car and truck puzzles", "road trip word games", "automotive hobby activity", "vehicle enthusiast puzzles"),
    "school": ("grade level vocabulary", "classroom word practice", "learning activity book", "academic word challenges"),
    "vocabulary": ("grade level vocabulary", "word skills practice", "learning activity book", "academic word challenges"),
    "food": ("kitchen and recipe puzzles", "food lover word games", "baking activity book", "culinary word challenges"),
    "bible": ("Bible study word games", "faith inspired puzzles", "scripture activity book", "Christian word challenges"),
    "ocean": ("sea life puzzles", "coastal nature games", "marine animal challenges", "ocean activity book"),
}


def _clean_words(value: str) -> list[str]:
    return [word for word in re.findall(r"[A-Za-z0-9]+", value.lower()) if len(word) > 2]


def _unique(values: list[str], limit: int, max_length: int | None = None) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = " ".join(str(value).split()).strip()
        if max_length:
            cleaned = cleaned[:max_length].rstrip()
        if cleaned and cleaned.casefold() not in seen:
            result.append(cleaned); seen.add(cleaned.casefold())
        if len(result) >= limit:
            break
    return result


def puzzle_type_for(source: dict) -> str:
    """Read the generator's type with safe fallbacks for older packages."""
    # New package records retain a stable ID, while older packages can still
    # resolve from their familiar display name or title-based fallback.
    for key in ("puzzle_type_id", "puzzle_type", "book_type", "kind"):
        capability = resolve_puzzle_type(source.get(key))
        if capability:
            return capability.display_name
    raw = " ".join(str(source.get(key) or "") for key in ("puzzle_type", "book_type", "kind", "title", "subtitle"))
    lowered = raw.casefold()
    if "mixed brain" in lowered or "mixed puzzle" in lowered: return "Mixed Brain Games"
    if "word scramble" in lowered or ("scramble" in lowered and "trivia" in lowered): return "Word Scramble + Trivia"
    if "cryptogram" in lowered or "cipher" in lowered: return "Cryptogram"
    if "sudoku" in lowered: return "Sudoku"
    return "Word Search"


def _count(source: dict) -> int:
    puzzles = source.get("puzzles") if isinstance(source.get("puzzles"), list) else []
    try: return int(source.get("puzzle_count") or len(puzzles) or 0)
    except (TypeError, ValueError): return len(puzzles)


def _topic_terms(topic: str, kind: str) -> list[str]:
    """Give marketplace search fields real subject vocabulary before generic format terms."""
    words = _clean_words(topic)
    result: list[str] = []
    joined = " ".join(words)
    for trigger, candidates in TOPIC_DISCOVERY_TERMS.items():
        if trigger in joined:
            result.extend(candidates)
    # An unfamiliar but valid niche should still retain its exact subject.
    if not result and joined:
        result.extend((f"{joined} puzzles", f"{joined} activity book", f"{joined} challenges"))
    if joined:
        result.extend((f"{joined} puzzle challenges", f"{joined} vocabulary games", f"{joined} printable", f"{joined} activity"))
    for word in words:
        result.extend((f"{word} puzzles", f"{word} word games"))
    if kind == "Sudoku":
        result.extend(("easy medium hard sudoku", "sudoku with solutions"))
    elif kind == "Cryptogram":
        result.extend(("cipher message puzzles", "code breaking challenges"))
    elif kind == "Word Scramble + Trivia":
        result.extend(("fact based word games", "trivia and scramble challenges"))
    elif kind == "Mixed Brain Games":
        result.extend(("sudoku cryptogram collection", "word and logic variety games"))
    else:
        result.extend(("themed word find", "word search with answers"))
    return _unique(result, 12)


def marketplace_copy_quality(source: dict, platform: str = "amazon") -> dict:
    """Plain-English audit for factual, specific buyer copy.

    It deliberately scores relevance and clarity—not predicted sales.  A
    high score means the copy names the actual topic, format, audience, and
    buyer benefit without keyword stuffing or unsupported claims.
    """
    content = marketplace_content(source)
    meta = {**source, **content}
    platform = str(platform or "amazon")
    description = str((content.get("platform_descriptions") or {}).get(platform) or content.get("description") or "").strip()
    topic_words = set(_clean_words(str(meta.get("detected_topic") or meta.get("theme") or meta.get("series") or "")))
    kind_words = set(_clean_words(content["puzzle_type"]))
    if platform == "amazon":
        terms = list(content.get("amazon_keywords") or [])
        target_count, minimum_words = 7, 110
    elif platform == "etsy":
        terms = list(content.get("etsy_tags") or [])
        target_count, minimum_words = 13, 70
    elif platform == "ingram":
        terms = list(content.get("ingram_subjects") or [])
        target_count, minimum_words = 1, 160
    else:
        terms = list(content.get("website_tags") or [])
        target_count, minimum_words = 5, 80
    notes: list[str] = []
    score = 100
    word_count = len(_clean_words(description))
    if word_count < minimum_words:
        score -= 18; notes.append(f"Description is only {word_count} words; add factual detail about the puzzles and who they are for.")
    if topic_words and not (topic_words & set(_clean_words(description))):
        score -= 24; notes.append("Description does not name the actual topic clearly enough.")
    if kind_words and not (kind_words & set(_clean_words(description))):
        score -= 12; notes.append("Description should name the actual puzzle format so buyers know what they receive.")
    cleaned = [" ".join(str(value).casefold().split()) for value in terms if str(value).strip()]
    if len(cleaned) < target_count:
        score -= 12; notes.append(f"Only {len(cleaned)} of {target_count} recommended discovery fields are filled.")
    if len(set(cleaned)) != len(cleaned):
        score -= 12; notes.append("Discovery fields repeat one another; use distinct, accurate ways buyers describe this topic.")
    generic = [value for value in cleaned if value in GENERIC_DISCOVERY_TERMS]
    if generic:
        score -= min(18, len(generic) * 6); notes.append("Replace broad phrases such as " + ", ".join(generic[:3]) + " with specific topic language.")
    if platform == "etsy" and any(len(value) > 20 for value in cleaned):
        score -= 12; notes.append("One or more Etsy tags exceed 20 characters.")
    if platform == "amazon" and any("<" in value or ">" in value for value in cleaned):
        score -= 25; notes.append("Amazon keyword fields cannot contain HTML.")
    if not notes:
        notes.append("Copy is specific to the topic, format, buyer, and on-page experience without keyword stuffing.")
    label = "Strong and specific" if score >= 90 else "Good—review notes" if score >= 75 else "Needs a clearer buyer angle"
    return {"score": max(0, score), "label": label, "notes": notes, "description_words": word_count, "terms": terms}


def marketplace_content(source: dict) -> dict:
    """Create strong, factual copy for all current and future puzzle formats."""
    title = str(source.get("title") or "Untitled Puzzle Book").strip()
    subtitle = str(source.get("subtitle") or "").strip()
    topic = str(source.get("detected_topic") or source.get("theme") or source.get("series") or "everyday puzzle time").strip()
    audience = str(source.get("audience") or "adults and teens").strip()
    difficulty = str(source.get("difficulty_label") or source.get("difficulty") or "Standard").strip().lower()
    count = _count(source)
    kind = puzzle_type_for(source)
    profile = PUZZLE_PROFILES.get(kind, PUZZLE_PROFILES["Word Search"])
    noun, inside, answers, subject, _seed_keywords, _seed_tags = profile
    count_text = f"{count} " if count else ""
    signature = "signature" in " ".join(str(source.get(key) or "") for key in ("title", "subtitle", "edition")).casefold() or count >= 100
    edition = "Signature Edition " if signature else ""
    lead = (f"{title}" + (f" — {subtitle}" if subtitle else "") + f" is a {topic} collection with {count_text}{noun} for {audience}. "
            f"The puzzles focus on {topic}, use a {difficulty} difficulty level, and include {answers}.")
    retail = lead + f"\n\nInside, readers work through {inside} that are clearly numbered and easy to return to. The {edition.lower()}{kind.lower()} format is designed for people who want a focused, paper-based way to spend time with {topic}. Work at your own pace, start anywhere in the collection, and use the solution section whenever you want to check an answer."
    kdp = retail + f"\n\nInside you will find:\n• {count_text}{noun.title()} centered on {topic}\n• Clear, easy-to-read puzzle pages\n• {answers.title()}"
    etsy = f"{title} is a digital {count_text}{kind.lower()} collection for {audience} who enjoy {topic}. This printable download includes {inside}, clearly numbered pages, and {answers}. Please note: this listing is for a digital download; no physical item is shipped."
    topic_terms = _topic_terms(topic, kind)
    generated = {
        "puzzle_type": kind,
        "puzzle_type_id": (resolve_puzzle_type(kind).type_id if resolve_puzzle_type(kind) else "word_search"),
        "short_description": f"{count_text}{kind} puzzles with {answers}.".strip(),
        "description": retail,
        "platform_descriptions": {"amazon": kdp, "etsy": etsy, "ingram": retail, "lulu": retail, "bookvault": retail, "barnes_noble": retail, "website": retail},
        "amazon_keywords": _unique(topic_terms, 7),
        "etsy_tags": _unique(topic_terms + [topic, "printable puzzle pdf", "digital puzzle download"], 13, max_length=20),
        "website_tags": _unique([topic, kind, *topic_terms], 20),
        "ingram_subjects": [subject],
        "barnes_noble_metadata": {"category": subject},
        "marketplace_copy_source": "generated",
    }
    # A carefully written theme-level listing is more specific than the
    # generic fallback. Preserve it all the way through every handoff rather
    # than letting a later catalog refresh flatten it.
    custom_platforms = source.get("platform_descriptions")
    custom_platform_keys: set[str] = set()
    if isinstance(custom_platforms, dict):
        custom_platform_keys = {str(key) for key, value in custom_platforms.items() if str(value).strip() and not _legacy_generated_copy(value)}
        generated["platform_descriptions"] = {
            **generated["platform_descriptions"],
            **{str(key): str(value).strip() for key, value in custom_platforms.items() if str(value).strip() and not _legacy_generated_copy(value)},
        }
    custom_description = str(source.get("description") or "").strip()
    if custom_description and not _legacy_generated_copy(custom_description):
        generated["description"] = custom_description
        # A theme writer usually supplies one carefully tailored description.
        # Use it on every marketplace unless a platform-specific version was
        # explicitly supplied above.
        generated["platform_descriptions"] = {
            key: value if key in custom_platform_keys else custom_description
            for key, value in generated["platform_descriptions"].items()
        }
    for key in ("amazon_keywords", "etsy_tags", "website_tags", "ingram_subjects"):
        values = source.get(key)
        if isinstance(values, list) and values:
            limit = 7 if key == "amazon_keywords" else 13 if key == "etsy_tags" else 20
            generated[key] = _unique([str(value) for value in values], limit, max_length=20 if key == "etsy_tags" else None)
    return generated


def refresh_marketplace_content(metadata: dict) -> dict:
    """Refresh automated marketplace fields without overwriting a custom blurb."""
    content = marketplace_content(metadata)
    current = str(metadata.get("description") or "").strip()
    legacy = _legacy_generated_copy(current)
    if current and not legacy:
        content["description"] = current
    return {**metadata, **content}


def build_metadata(source: dict) -> dict:
    """Make accurate defaults once; a locked record is never overwritten automatically."""
    title = str(source.get("title") or "Untitled Puzzle Book").strip()
    subtitle = str(source.get("subtitle") or "").strip()
    author = str(source.get("author") or "Jordan M. Slade").strip()
    series = str(source.get("series") or "").strip()
    topic = str(source.get("detected_topic") or source.get("theme") or series or "themed puzzles").strip()
    count = _count(source)
    difficulty = str(source.get("difficulty_label") or "Standard").title()
    content = marketplace_content({**source, "title": title, "subtitle": subtitle, "detected_topic": topic, "puzzle_count": count, "difficulty_label": difficulty})
    custom_description = str(source.get("description") or "").strip()
    if custom_description:
        content["description"] = custom_description
    return {"title": title, "subtitle": subtitle, "author": author, "series": series, "theme": topic,
            "audience": str(source.get("audience") or "Adults and teens"), "difficulty": difficulty,
            # Keep generated non-word-search packages just as complete as
            # theme-backed Word Search records.  Marketplace previews, price
            # guidance, and listing copy all need the actual puzzle count.
            "difficulty_label": difficulty, "puzzle_count": count,
            **content, "categories": content["ingram_subjects"]}
