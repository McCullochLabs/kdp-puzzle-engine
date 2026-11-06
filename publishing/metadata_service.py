"""One reusable metadata engine for every marketplace."""
from __future__ import annotations

import re

from .puzzle_types import resolve_puzzle_type


# Every generator shares this profile map.  It keeps a Sudoku listing from
# sounding like a word-search book and gives every platform accurate language.
PUZZLE_PROFILES = {
    "Word Search": ("word-search puzzles", "themed word-search grids", "a complete answer key", "Games & Activities / Word & Word Search", ["word search puzzles", "word find book", "word search with answers", "large print word search", "relaxing word puzzles", "screen free activity", "puzzle gift"], ["word search", "word find", "puzzle book", "large print", "puzzle gift", "brain games", "word puzzles"]),
    "Sudoku": ("logic puzzles", "verified number, letter, and shape Sudoku grids", "full solutions", "Games & Activities / Sudoku", ["large print sudoku", "sudoku with solutions", "logic puzzles adults", "number puzzle book", "brain games adults", "screen free activity", "puzzle gift"], ["sudoku", "logic puzzles", "number puzzles", "large print", "brain games", "puzzle book", "sudoku answers"]),
    "Cryptogram": ("code-breaking puzzles", "cryptogram messages to decode", "complete decoded solutions", "Games & Activities / Logic & Brain Teasers", ["cryptogram puzzles", "code breaking games", "cipher puzzle book", "cryptograms with answers", "word logic games", "brain games adults", "puzzle gift"], ["cryptogram", "cipher puzzles", "code breaker", "word puzzles", "brain games", "puzzle book", "logic games"]),
    "Word Scramble + Trivia": ("word scrambles with fact clues", "scrambled words guided by fact questions", "a complete answer key", "Games & Activities / Word & Word Search", ["word scramble puzzles", "fact clue word games", "word games adults", "general knowledge clues", "scramble with answers", "brain games adults", "puzzle gift"], ["word scramble", "fact clues", "word games", "brain games", "puzzle book", "knowledge clues", "answer key"]),
    "Mixed Brain Games": ("variety brain games", "a mix of Sudoku, Cryptograms, and word scrambles with fact clues", "complete answers for every section", "Games & Activities / Puzzles", ["mixed brain games", "variety puzzle book", "sudoku cryptogram games", "logic and word games", "brain games adults", "puzzle book with answers", "screen free activity"], ["brain games", "mixed puzzles", "sudoku games", "cryptogram", "word games", "puzzle book", "brain teasers"]),
    "Word Search + Sudoku": ("word searches and Sudoku puzzles", "holiday word searches plus classic-number and themed-symbol Sudoku", "complete solutions for both puzzle styles", "Games & Activities / Puzzles", ["holiday word search sudoku", "holiday variety puzzle book", "symbol sudoku puzzles", "holiday word find book", "number sudoku puzzles", "seasonal puzzle collection", "puzzle book with answers"], ["holiday puzzles", "word search", "sudoku", "symbol sudoku", "seasonal games", "puzzle book", "answers included"]),
}

AMAZON_CATEGORY_DIRECTIONS = {
    "Word Search": ("Humor & Entertainment / Puzzles & Games / Word Search", "Humor & Entertainment / Puzzles & Games / Word Games", "Humor & Entertainment / Puzzles & Games / Puzzles"),
    "Sudoku": ("Humor & Entertainment / Puzzles & Games / Sudoku", "Humor & Entertainment / Puzzles & Games / Logic & Brain Teasers", "Humor & Entertainment / Puzzles & Games / Puzzles"),
    "Cryptogram": ("Humor & Entertainment / Puzzles & Games / Logic & Brain Teasers", "Humor & Entertainment / Puzzles & Games / Puzzles", "Humor & Entertainment / Puzzles & Games / Word Games"),
    "Word Scramble + Trivia": ("Humor & Entertainment / Puzzles & Games / Word Games", "Humor & Entertainment / Puzzles & Games / Puzzles", "Humor & Entertainment / Puzzles & Games / Logic & Brain Teasers"),
    "Mixed Brain Games": ("Humor & Entertainment / Puzzles & Games / Puzzles", "Humor & Entertainment / Puzzles & Games / Logic & Brain Teasers", "Humor & Entertainment / Puzzles & Games / Word Games"),
    "Word Search + Sudoku": ("Humor & Entertainment / Puzzles & Games / Puzzles", "Humor & Entertainment / Puzzles & Games / Word Search", "Humor & Entertainment / Puzzles & Games / Sudoku"),
}

TOPIC_COPY_PROFILES = {
    "baking": ("Trade the measuring cups for a pencil and enjoy a fresh batch of logic.", "bakers, food lovers, and anyone who enjoys a cozy kitchen-table challenge", "recipe breaks, quiet evenings, and thoughtful gifts for a favorite baker"),
    "cat": ("Curl up with a satisfying logic break made for cat people.", "cat lovers who want calm, screen-free puzzle time", "slow mornings, rainy afternoons, travel, and gifts for devoted cat people"),
    "dog": ("After the walk, settle in with a puzzle break made for dog people.", "dog lovers who enjoy approachable logic challenges", "coffee-table solving, travel, quiet evenings, and gifts for dog lovers"),
    "christmas": ("Bring a little calm to the busiest season with a festive pencil-and-paper escape.", "holiday puzzle fans who enjoy cozy winter traditions", "December evenings, family visits, stocking stuffers, and holiday travel"),
    "garden": ("Pause between garden plans and enjoy a quiet puzzle path of your own.", "gardeners, plant lovers, and relaxed logic-puzzle fans", "porch time, rainy garden days, travel, and gifts for green thumbs"),
    "national park": ("Bring the spirit of the trail to a screen-free puzzle break.", "park lovers, travelers, and outdoor-minded solvers", "road trips, cabin weekends, quiet evenings, and gifts for national-park fans"),
    "ocean": ("Let the day slow down with a puzzle break inspired by the sea.", "ocean lovers and solvers who prefer a calm, unhurried challenge", "vacations, quiet afternoons, travel bags, and coastal gifts"),
    "road trip": ("Pack a pencil and take the open road one puzzle at a time.", "travelers, vehicle fans, and armchair adventurers", "long trips, campground evenings, waiting rooms, and gifts for road-trip fans"),
    "travel": ("Turn a spare moment into a small trip around the world.", "travel lovers and curious solvers", "flights, road trips, waiting rooms, and gifts for frequent travelers"),
    "space": ("Give your next puzzle break a cosmic sense of discovery.", "stargazers, astronomy fans, and curious problem-solvers", "quiet nights, travel, classroom breaks, and gifts for space lovers"),
    "heritage": ("Crack the code and rediscover the people, ideas, and moments that shaped America.", "history fans and code-breaking puzzle lovers", "quiet evenings, travel, history-themed gifts, and satisfying mental workouts"),
    "faith": ("Slow down, focus, and enjoy a peaceful puzzle break rooted in faith and encouragement.", "Bible readers and faith-minded puzzle lovers", "quiet time, church groups, travel, and thoughtful Christian gifts"),
    "bible": ("Slow down, focus, and enjoy a peaceful puzzle break rooted in faith and encouragement.", "Bible readers and faith-minded word-puzzle lovers", "quiet time, church groups, travel, and thoughtful Christian gifts"),
    "vocabulary": ("Turn word practice into an inviting search-and-discover challenge.", "students, families, homeschoolers, and teachers building word confidence", "independent practice, learning centers, homeschool time, and screen-free review"),
    "school": ("Make a study break feel like a reward without leaving learning behind.", "students, families, teachers, and lifelong learners", "study breaks, classrooms, homeschool time, and educational gifts"),
    "car": ("Start your engines for a word-search tour of vehicles and the open road.", "classic-car fans, road-trip lovers, and automotive hobbyists", "garage breaks, travel, waiting rooms, and gifts for vehicle enthusiasts"),
    "american": ("Explore familiar pieces of American life one hidden word at a time.", "history, civics, and Americana fans", "quiet evenings, travel, family gifts, and screen-free learning"),
    "food": ("Pull up a chair for a playful serving of food-and-home word challenges.", "home cooks, food lovers, and word-game fans", "kitchen-table breaks, family gatherings, travel, and foodie gifts"),
    "curiosity": ("Open the cabinet, follow the clue, and see what surprising answer appears next.", "curious adults and teens who enjoy words, facts, and discovery", "coffee breaks, travel, family game time, and everyday brain exercise"),
    "nature": ("Step away from the screen and into a varied puzzle journey inspired by wild places.", "nature lovers and variety-puzzle fans", "cabins, camping trips, quiet afternoons, and outdoor-themed gifts"),
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
        "brings ", "this is a focused collection", "inside, readers work through",
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
    elif kind == "Word Search + Sudoku":
        result.extend(("holiday word search", "number and symbol sudoku", "holiday variety puzzles"))
    elif kind == "Cryptogram":
        result.extend(("cipher message puzzles", "code breaking challenges"))
    elif kind == "Word Scramble + Trivia":
        result.extend(("fact clue word games", "word scramble with clues"))
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


def _resolved_topic(source: dict, title: str) -> str:
    topic = str(source.get("detected_topic") or source.get("theme") or source.get("series") or "").strip()
    if topic:
        return topic
    lowered = title.casefold()
    for token, label in (
        ("vocabulary", "Grade-Level Vocabulary"), ("bible", "Bible & Faith"), ("faith", "Bible & Faith"),
        ("car", "Cars & Road Trips"), ("road trip", "Road Trips & Highways"), ("american", "American History & Heritage"),
        ("garden", "Garden & Growing"), ("space", "Space & Astronomy"), ("stargazer", "Space & Astronomy"),
        ("ocean", "Ocean Life"), ("woods", "Nature & Outdoors"), ("curiosity", "General Knowledge & Curiosity"),
    ):
        if token in lowered:
            return label
    return "Themed Puzzle Time"


def _topic_copy(topic: str, title: str) -> tuple[str, str, str]:
    haystack = f"{topic} {title}".casefold()
    for token, profile in TOPIC_COPY_PROFILES.items():
        if token in haystack:
            return profile
    return (
        f"Settle in with a focused puzzle break built around {topic}.",
        "adults and teens who enjoy thoughtful, screen-free challenges",
        "quiet mornings, travel, waiting rooms, and easy-to-wrap gifts",
    )


def _keyword_phrases(topic: str, kind: str, title: str, audience: str) -> list[str]:
    """Fill seven useful KDP boxes without merely repeating title metadata."""
    candidates = _topic_terms(topic, kind)
    if "grade 5" in title.casefold():
        candidates = ["fifth grade vocabulary practice", "homeschool language arts", "spelling reinforcement activity", "classroom learning center", "reading skills ages 9 12", *candidates]
    candidates += [
        f"{topic} gift for {audience}", "easy to read pencil puzzles", "screen free travel activity",
        "quiet time brain challenge", "complete solutions included",
    ]
    title_tokens = set(_clean_words(title))
    result = []
    for phrase in candidates:
        tokens = set(_clean_words(phrase))
        if tokens and tokens <= title_tokens:
            continue
        result.append(phrase)
    return _unique(result, 7, max_length=50)


def marketplace_content(source: dict) -> dict:
    """Create strong, factual copy for all current and future puzzle formats."""
    title = str(source.get("title") or "Untitled Puzzle Book").strip()
    subtitle = str(source.get("subtitle") or "").strip()
    topic = _resolved_topic(source, title)
    audience = str(source.get("audience") or ("Grade 5 students, families, and educators" if "grade 5" in title.casefold() else "adults and teens")).strip()
    difficulty = str(source.get("difficulty_label") or source.get("difficulty") or "Standard").strip().lower()
    count = _count(source)
    kind = puzzle_type_for(source)
    profile = PUZZLE_PROFILES.get(kind, PUZZLE_PROFILES["Word Search"])
    noun, inside, answers, subject, _seed_keywords, _seed_tags = profile
    count_text = f"{count} " if count else ""
    opener, intended_for, occasions = _topic_copy(topic, title)
    large_print = "large print" in f"{title} {subtitle} {source.get('format_label') or ''}".casefold()
    public_kind = "word-scramble-and-fact-clue" if kind == "Word Scramble + Trivia" else kind.lower()
    print_line = " The large-print layout gives each puzzle generous room to solve." if large_print else " The clean page layout keeps each challenge easy to follow."
    format_line = {
        "Word Search": "Scan each themed grid, work through its focused word list, and enjoy the satisfaction of the final find.",
        "Sudoku": "Move between classic numbers, letters, and themed shapes while the underlying Sudoku rules stay familiar.",
        "Cryptogram": "Use letter patterns and the supplied clue to solve each cryptogram and reveal its hidden message one careful step at a time.",
        "Word Scramble + Trivia": "Read the fact clue, untangle the themed answer, and check your work in the answer section.",
        "Mixed Brain Games": "Switch among Sudoku, Cryptograms, and word scrambles with fact clues whenever you want a different kind of challenge.",
        "Word Search + Sudoku": "Explore holiday word searches, then switch to classic-number and holiday-symbol Sudoku in each chapter.",
    }.get(kind, f"Work through each {public_kind} challenge at your own pace.")
    lead = f"{opener}\n\n{title} brings together {count_text}{noun} inspired by {topic}. {format_line}{print_line} The difficulty is {difficulty}, and {answers} are included at the back."
    theme_promise = {
        "Word Search": f"Puzzle titles and word lists keep {topic} at the center instead of drifting into a random dictionary assortment.",
        "Sudoku": f"The {topic} art direction and themed shape rounds give the collection its personality while preserving familiar Sudoku logic.",
        "Cryptogram": f"The encoded messages maintain the {topic} direction, so the solving experience feels cohesive from the first cipher to the last.",
        "Word Scramble + Trivia": f"Each clue and scrambled answer stays tied to {topic}; the questions guide the word play rather than promising a separate trivia quiz.",
        "Mixed Brain Games": f"Section changes add variety while the {topic} direction keeps the collection feeling like one complete book.",
        "Word Search + Sudoku": "Each holiday chapter keeps its word lists on theme and pairs them with number and matching-symbol Sudoku.",
    }.get(kind, f"The collection maintains a clear {topic} direction from beginning to end.")
    retail = (lead + f"\n\nMade for {intended_for}, this collection works especially well for {occasions}. Solve one puzzle during a short break or keep going through a longer session—the numbered pages make it easy to stop and return. {theme_promise}\n\nThe instructions are straightforward, the progression is approachable, and the solution section makes independent solving practical. It is a useful choice for anyone who wants something more engaging than passive screen time without turning a relaxing break into homework.\n\nEvery claim in this listing reflects the finished book: {count_text}{noun}, a {difficulty} difficulty level, and {answers}.")
    kdp = retail + f"\n\nInside you will find:\n• {count_text}{noun.title()} built around {topic}\n• {'Large-print' if large_print else 'Clear, easy-to-read'} puzzle pages\n• {answers.title()}\n• A focused, screen-free activity for {audience}"
    digital_details = (f"WHAT YOU RECEIVE\n• One US Letter printable PDF\n• {count_text}{noun.title()}\n• {answers.title()}\n\n"
                       "DIGITAL DOWNLOAD — NO PHYSICAL PRODUCT WILL BE SHIPPED. Print the pages you want for personal use or solve with a compatible PDF annotation app.")
    etsy = f"{opener}\n\n{title} is a printable download built around {topic} for {intended_for}. {format_line}{print_line}\n\n{digital_details}"
    payhip = f"{opener}\n\nDownload the complete {title} collection and enjoy {count_text}{noun} with {answers}. {format_line}{print_line}\n\n{digital_details}"
    topic_terms = _topic_terms(topic, kind)
    etsy_terms = topic_terms + {
        "Word Search": ["printable word find", "large print puzzle", "themed word search"],
        "Sudoku": ["printable sudoku", "logic game pdf", "sudoku solutions"],
        "Cryptogram": ["printable cryptogram", "code breaker game", "cipher puzzle pdf"],
        "Word Scramble + Trivia": ["word scramble pdf", "fact clue puzzles", "unscramble words"],
        "Mixed Brain Games": ["mixed puzzle pdf", "variety brain games", "logic word games"],
        "Word Search + Sudoku": ["holiday puzzle pdf", "word search sudoku", "seasonal puzzle book"],
    }.get(kind, []) + [topic, "printable puzzle pdf", "digital download", "pencil puzzle", "quiet time activity", "travel activity", "answer key included"]
    amazon_categories = list(AMAZON_CATEGORY_DIRECTIONS.get(kind, AMAZON_CATEGORY_DIRECTIONS["Mixed Brain Games"]))
    if "grade 5" in title.casefold():
        amazon_categories = ["Children's Books / Activities, Crafts & Games / Games", "Children's Books / Education & Reference / Language Arts", amazon_categories[0]]
    generated = {
        "puzzle_type": kind,
        "puzzle_type_id": (resolve_puzzle_type(kind).type_id if resolve_puzzle_type(kind) else "word_search"),
        "resolved_topic": topic,
        "short_description": f"{count_text}{noun} with {answers}.".strip(),
        "description": retail,
        "platform_descriptions": {"amazon": kdp, "etsy": etsy, "payhip": payhip, "ingram": retail, "lulu": retail, "bookvault": retail, "barnes_noble": retail, "website": retail},
        "amazon_keywords": _keyword_phrases(topic, kind, title, audience),
        "etsy_tags": _unique(etsy_terms, 13, max_length=20),
        "website_tags": _unique([topic, kind, *topic_terms], 20),
        "ingram_subjects": [subject],
        "bisac_codes": [{"code": {"Word Search": "GAM014000", "Sudoku": "GAM017000", "Cryptogram": "GAM005000", "Word Scramble + Trivia": "GAM014000", "Mixed Brain Games": "GAM007000", "Word Search + Sudoku": "GAM007000"}.get(kind, "GAM007000"), "heading": subject}],
        "amazon_category_directions": amazon_categories,
        "primary_audience": "Children" if "grade 5" in title.casefold() else "Adult / General",
        "reading_age": "9–12" if "grade 5" in title.casefold() else "Not required for an adult/general puzzle book",
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
            **content, "categories": content["ingram_subjects"],
            **{key: source[key] for key in ("no_repeat_words", "repetition_policy", "collection_id", "collection_book_id", "interior_profile") if key in source}}
