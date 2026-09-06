"""Build four adult-only, non-explicit Word Search collections from local data.

The collections deliberately use mature, lawful, commercially appropriate
language. They are no-repeated-entry pools, not a claim that every individual
word component is unique across a book.
"""
from __future__ import annotations

import copy
import json
import random
import shutil
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BANK_PATH = ROOT / "word_banks" / "Guided_Builder_Master_Word_Bank.json"
THEMES = ROOT / "themes" / "Adult Collection"


COLLECTIONS = {
    "Cocktail Hour, Nightlife & Social Club": {
        "title": "Cocktail Hour Word Search",
        "subtitle": "48 grown-up puzzles for cocktail culture, nightlife and social fun",
        "palette": "midnight-gold", "style": "Bold Spotlight",
        "terms": ["cocktail", "mocktail", "martini", "highball", "old fashioned", "spritz", "margarita", "manhattan", "negroni", "sidecar", "gimlet", "paloma", "daiquiri", "sangria", "bellini", "aperitif", "digestif", "bitters", "vermouth", "shaker", "jigger", "strainer", "bar spoon", "garnish", "citrus twist", "olive", "cherry", "orange peel", "lime wedge", "ice cube", "wine flight", "tasting menu", "happy hour", "cocktail lounge", "rooftop bar", "jazz bar", "dance floor", "live music", "late night", "social club"],
        "contexts": ["night out", "after work", "weekend plans", "city lights", "evening glow", "friends night", "date night", "lounge life", "good company", "party playlist", "bar cart", "restaurant patio", "hotel lobby", "sunset hour", "celebration toast", "birthday cheers", "holiday party", "tasting room", "midnight snack", "downtown scene", "neighborhood spot", "conversation starter", "grown up fun", "special occasion", "supper club", "cocktail class", "mixology night", "shared laughs", "slow evening", "weekend vibe"],
        "description": "Leave the ordinary behind and settle into a grown-up word-search collection inspired by cocktail lounges, rooftop conversations, tasting menus, live music, and unforgettable nights out. Cocktail Hour Word Search is made for adult solvers who enjoy a little sparkle with their screen-free downtime. Each puzzle is clearly laid out, thoughtfully themed, and followed by a complete answer key.",
        "keywords": ["cocktail word search", "nightlife puzzle book", "adult party word find", "bar and lounge games", "mixology gift book", "happy hour puzzles", "grown up word games"],
    },
    "Cannabis Culture, Chill & Legal Lifestyle": {
        "title": "Chill Culture Word Search",
        "subtitle": "48 adult puzzles for laid-back hobbies, legal cannabis culture and cozy downtime",
        "palette": "forest-cabin", "style": "Gallery Frame",
        "terms": ["cannabis culture", "legal dispensary", "herbal aroma", "rolling tray", "glass jar", "flower jar", "cannabis leaf", "hemp fabric", "CBD balm", "terpene profile", "hybrid blend", "indica evening", "sativa daytime", "edible kitchen", "infused treat", "vaporizer", "grinder", "stash box", "smell proof", "chill session", "cozy blanket", "vinyl record", "movie marathon", "board game", "snack table", "tea kettle", "candle glow", "houseplant", "balcony garden", "creative project", "sketch book", "paint set", "puzzle night", "relaxation ritual", "slow weekend", "deep breathing", "good playlist", "soft lighting", "quiet time", "self care"],
        "contexts": ["legal adult use", "responsible choice", "at home", "weekend reset", "evening unwind", "creative break", "cozy corner", "rainy afternoon", "late night movie", "friends gathering", "music session", "garden patio", "after dinner", "slow morning", "calm routine", "mindful moment", "private lounge", "hobby time", "screen free", "weekend ritual", "home comfort", "quiet company", "relaxed pace", "personal space", "favorite chair", "warm lamp", "open window", "soft sofa", "evening tea", "fresh air"],
        "description": "Designed for adults, Chill Culture Word Search pairs legal cannabis-culture vocabulary with cozy hobbies, creative downtime, music, movies, and relaxing at-home rituals. It is a lighthearted, mature-audience collection for solvers who appreciate a laid-back puzzle break. Includes 48 clear puzzles and a complete answer key.",
        "keywords": ["cannabis culture word search", "420 friendly puzzle book", "adult chill word find", "legal lifestyle puzzles", "relaxing adult games", "cozy hobby word search", "mature audience puzzles"],
    },
    "Date Night, Romance & Relationship Fun": {
        "title": "Date Night Word Search",
        "subtitle": "48 adult puzzles for romance, connection and unforgettable evenings together",
        "palette": "royal-plum", "style": "Halo Spotlight",
        "terms": ["date night", "romantic dinner", "first date", "love letter", "inside joke", "sweet message", "shared playlist", "weekend getaway", "movie night", "coffee date", "sunset walk", "dinner reservation", "flower bouquet", "candlelight", "slow dance", "hand holding", "good conversation", "anniversary", "surprise plan", "thoughtful gift", "favorite restaurant", "dessert date", "city stroll", "beach walk", "mountain view", "road trip", "picnic basket", "wine tasting", "game night", "photo booth", "couples quiz", "relationship goals", "kindness", "trust", "laughter", "chemistry", "connection", "quality time", "shared dreams", "romance"],
        "contexts": ["special evening", "weekend plans", "two person adventure", "grown up date", "cozy restaurant", "quiet table", "night on the town", "at home date", "celebration dinner", "memory maker", "lovely surprise", "after dark", "weekend escape", "best company", "good energy", "sweet moment", "future plans", "favorite memory", "little adventure", "couples time", "private joke", "happy hour", "city lights", "scenic view", "long talk", "warm smile", "special place", "shared laugh", "thoughtful moment", "romantic mood"],
        "description": "Bring a little extra spark to your screen-free time with Date Night Word Search, a mature-audience collection inspired by romance, connection, shared adventures, and memorable evenings together. From coffee dates to candlelight dinners, every puzzle gives adults a relaxing way to celebrate the fun side of relationships. Includes 48 themed puzzles and a complete answer key.",
        "keywords": ["date night word search", "couples puzzle book", "romance word find adults", "relationship game gift", "anniversary activity book", "adult love puzzles", "couples game night"],
    },
    "Responsible Firearms, Range & Outdoor Heritage": {
        "title": "Range & Outdoors Word Search",
        "subtitle": "48 adult puzzles for responsible firearm ownership, range culture and outdoor heritage",
        "palette": "graphite-copper", "style": "Gallery Frame",
        "terms": ["responsible ownership", "range safety", "hearing protection", "eye protection", "locked storage", "safe handling", "range officer", "safety briefing", "target stand", "paper target", "range bag", "ear muffs", "safety glasses", "gun cabinet", "lock box", "trigger lock", "cleaning kit", "owner manual", "outdoor range", "indoor range", "sportsman club", "hunting lodge", "trail map", "campfire", "field guide", "wildlife view", "outdoor heritage", "marksmanship sport", "practice day", "range etiquette", "safe transport", "secure storage", "responsible adult", "hunting season", "cabin weekend", "conservation", "land stewardship", "outdoor skills", "respectful culture", "safety first"],
        "contexts": ["safe routine", "range day", "outdoor weekend", "sportsman tradition", "responsible hobby", "adult collection", "safety culture", "club meeting", "country cabin", "field morning", "trail side", "conservation project", "family heritage", "quiet focus", "careful planning", "gear check", "secure home", "local range", "outdoor life", "weekend camp", "woods walk", "respectful practice", "prepared adult", "good judgment", "safety lesson", "clean workspace", "organized gear", "responsible choice", "fresh air", "open country"],
        "description": "Range & Outdoors Word Search is a mature-audience puzzle collection built around responsible firearm ownership, safety-minded range culture, conservation, and outdoor heritage. Every puzzle stays focused on respectful, lawful adult hobbies—never instruction or unsafe behavior. Includes 48 clearly organized puzzles and a complete answer key.",
        "keywords": ["firearm safety word search", "range culture puzzle book", "outdoor heritage word find", "responsible gun owner gift", "sportsman word puzzles", "range day game book", "adult outdoor puzzle"],
    },
}


def clean(values: list[str]) -> list[str]:
    return list(dict.fromkeys(" ".join(value.upper().split()) for value in values if value.strip()))


def phrases(record: dict) -> list[str]:
    values = clean([f"{term} {context}" for term in record["terms"] for context in record["contexts"]])
    # 1,200 relevant phrase entries supports two 48×12 no-repeat books with
    # a reserve. The term/context construction keeps every entry on theme.
    return values[:1200]


def theme_data(name: str, record: dict, words: list[str]) -> dict:
    selected = words[:]
    random.Random(f"{name}|SladePuzzleCo|adult-collection").shuffle(selected)
    puzzles = [{"name": f"{name} Puzzle {number:03d}", "words": selected[(number - 1) * 12:number * 12]} for number in range(1, 49)]
    return {
        "title": record["title"], "subtitle": record["subtitle"], "author": "Jordan M. Slade", "audience": "Adults (18+)",
        "series": "SladePuzzleCo Adult Collection", "detected_topic": name, "palette": record["palette"], "cover_style": record["style"],
        "recommended_palette": record["palette"], "recommended_cover_style": record["style"], "cover_badge": "ADULTS ONLY • 48 PUZZLES",
        "no_repeat_words": True, "difficulty_label": "Standard", "clipart_search_terms": f"{name} elegant adult lifestyle illustration", "puzzles": puzzles,
        "description": record["description"], "amazon_keywords": record["keywords"], "etsy_tags": record["keywords"], "website_tags": record["keywords"],
        "adult_collection": {"enabled": True, "cover_language": "mature-but-non-explicit", "age_notice": "Adults 18+"},
    }


def main() -> None:
    bank = json.loads(BANK_PATH.read_text(encoding="utf-8-sig"))
    backup = BANK_PATH.with_name(f"Guided_Builder_Master_Word_Bank.before_adult_collection_{datetime.now():%Y%m%d_%H%M%S}.json")
    shutil.copy2(BANK_PATH, backup)
    topics = bank.setdefault("topics", {})
    packs = bank.setdefault("topic_packs", {})
    production = bank.setdefault("production_topic_packs", {})
    families = bank.setdefault("pack_families", {})
    THEMES.mkdir(parents=True, exist_ok=True)
    for name, record in COLLECTIONS.items():
        words = phrases(record)
        if len(words) < 1152:
            raise RuntimeError(f"{name} needs at least 1,152 entries, found {len(words)}")
        topics[name] = words
        packs[name] = [name]
        production[name] = {"sources": [name], "puzzle_type": "Word Search", "adult_only": True}
        path = THEMES / (record["title"].lower().replace(" ", "_") + ".json")
        path.write_text(json.dumps(theme_data(name, record, words), indent=2) + "\n", encoding="utf-8")
    family = families.setdefault("Adult Collection (18+)", [])
    for name in COLLECTIONS:
        if name not in family:
            family.append(name)
    BANK_PATH.write_text(json.dumps(bank, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Added {len(COLLECTIONS)} adult-only packs and themes. Backup: {backup.name}")


if __name__ == "__main__":
    main()
