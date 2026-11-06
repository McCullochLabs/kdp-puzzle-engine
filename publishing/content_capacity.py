"""One honest inventory for topic capacity across every puzzle creator."""
from __future__ import annotations

import json
import math
from pathlib import Path

from .word_capacity_plan import build_plan, required_words

WORDSEARCH_BOOK_SIZE = 48
PUZZLE_BOOK_SIZE = 60
CONTENT_BUFFER = 1.60

TOPIC_GROUPS = {
    "Space & Astronomy": ("Space & Astronomy",),
    "Garden & Growing": ("Gardening", "Gardening & Garden Life", "Homesteading", "Herbs Fruits and Vegetables"),
    "Travel & Adventure": ("Travel & World Discovery", "Travel Road Trips and Getaways", "Outdoor Adventure", "National Parks"),
    "Road Trips & Highways": ("Travel Road Trips and Getaways", "Vehicles & Automotive", "Outdoor Adventure"),
    "Pets & Animal Life": ("Cats & Pets", "Dogs & Pets", "Pets and Animal Care", "Birdwatching & Wildlife"),
    "Holidays & Seasons": ("Christmas", "Christmas and Winter", "Halloween", "Halloween Autumn and Harvest", "Holiday and Seasonal Life", "Holidays", "Easter and Spring"),
    "History & Heritage": ("American History", "American Heritage", "World War II History"),
    "Food & Home": ("Baking and Food", "Baking & Food", "Garden to Table", "Home and Household"),
    "School & Vocabulary": ("Grade School Vocabulary", "Middle School Vocabulary", "High School Vocabulary", "Grade 5 Vocabulary", "Grade 6 Vocabulary", "Grade 7 Vocabulary", "Grade 8 Vocabulary", "Grade 9 Vocabulary", "Grade 10 Vocabulary", "Grade 11 Vocabulary", "Grade 12 Vocabulary"),
    "Cars & Adventure": ("Vehicles & Automotive", "Outdoor Adventure", "Travel Road Trips and Getaways"),
    "Nature & Outdoors": ("Nature", "Forest Wildlife and Outdoors", "National Parks", "Ocean Life", "Outdoor Adventure"),
    "Bible & Faith": ("Bible and Faith", "Faith & Encouragement", "Faith Inspiration and Kindness"),
}

FAMILY_PACKS = {
    "Space & Astronomy": ("Planets & Solar System", "Space Missions, Rockets & Astronauts", "Stargazing, Telescopes & Night Sky"),
    "Garden & Growing": ("Gardening, Herbs & Homestead Living",),
    "Travel & Adventure": ("Travel, Road Trips & Weekend Getaways",),
    "Road Trips & Highways": ("Family Road Trips & Travel", "RV, Camping & Off-Road"),
    "Pets & Animal Life": ("Pets, Backyard Animals & Care",),
    "Holidays & Seasons": ("Holidays & Seasonal Fun",),
    "History & Heritage": ("American Heritage", "Presidents, History & Americana"),
    "Food & Home": ("Food, Baking & Kitchen", "Home, Cozy Living & Self Care"),
    "School & Vocabulary": ("Vocabulary Ladder: Grades 5–12",),
    "Cars & Adventure": ("Vehicles, Cars & Trucks", "Family Road Trips & Travel", "RV, Camping & Off-Road"),
    "Nature & Outdoors": ("National Parks, Trails & Wild Places", "Forests, Wildlife & Outdoor Escape", "Coastal, Lake & River Life"),
    "Bible & Faith": ("Bible, Faith & Encouragement — Complete",),
}

def _read(path: Path) -> dict:
    try: return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError): return {}

def topic_capacity(project: Path) -> list[dict]:
    """Return plain-English readiness rows without guessing unpublished content."""
    project = Path(project)
    bank = _read(project / "word_banks" / "Guided_Builder_Master_Word_Bank.json")
    from word_intelligence.editorial_overlay import merge_master_bank
    bank = merge_master_bank(bank, project)
    topic_words = bank.get("topics", {}) if isinstance(bank.get("topics"), dict) else {}
    topic_packs = bank.get("topic_packs", {}) if isinstance(bank.get("topic_packs"), dict) else {}
    packs = _read(project / "word_banks" / "puzzle_content_library.json").get("packs", {})
    packs = packs if isinstance(packs, dict) else {}
    rows=[]
    for name, groups in TOPIC_GROUPS.items():
        words=[]
        source_topics=[]
        for pack_name in FAMILY_PACKS.get(name, ()): source_topics.extend(topic_packs.get(pack_name, []))
        for topic in source_topics or groups:
            values=topic_words.get(topic, [])
            if isinstance(values, list): words.extend(values)
        clean = list(dict.fromkeys(str(word).strip().upper() for word in words if str(word).strip()))
        pack = packs.get(name, {}) if isinstance(packs.get(name), dict) else {}
        cryptos=len(pack.get("cryptograms", [])) if isinstance(pack.get("cryptograms"), list) else 0
        trivia=len(pack.get("trivia", [])) if isinstance(pack.get("trivia"), list) else 0
        # Non-word generators can safely create their topic challenge prompts
        # only from linked, approved master-bank words.  A family with fewer
        # than 240 clean terms remains visibly short rather than borrowing
        # unrelated filler words from another topic.
        if len(clean) >= 240:
            cryptos=max(cryptos, min(240, len(clean)))
            trivia=max(trivia, min(240, len(clean)))
        plan = build_plan(name, clean)
        ws_books=len(clean)//(WORDSEARCH_BOOK_SIZE * 12)  # 12 unique words/puzzle
        crypto_books=cryptos//math.ceil(PUZZLE_BOOK_SIZE*CONTENT_BUFFER)
        trivia_books=trivia//math.ceil(PUZZLE_BOOK_SIZE*CONTENT_BUFFER)
        rows.append({"topic":name,"words":len(clean),"word_search_books":ws_books,"cryptograms":cryptos,"cryptogram_books":crypto_books,"trivia":trivia,"trivia_books":trivia_books,
                     "portfolio_required_words": required_words(), "portfolio_ready": plan["portfolio_ready"], "portfolio_gap": plan["gap"],
                     "next_step": "Ready for 2 standard Word Searches + a Signature Edition" if plan["portfolio_ready"] else "Expand topic words for the planned 2 standard books + Signature Edition"})
    # Focused production packs are the extra book ideas surfaced in Guided
    # Book Builder.  They share existing vetted words but have their own
    # honest no-repeat capacity rather than pretending to be new vocabulary.
    production = bank.get("production_topic_packs", {})
    if isinstance(production, dict):
        for name, record in sorted(production.items()):
            sources = record.get("sources", []) if isinstance(record, dict) else []
            words = list(dict.fromkeys(str(word).strip().upper() for source in sources for word in topic_words.get(source, []) if str(word).strip()))
            plan = build_plan(name, words)
            books = len(words) // (WORDSEARCH_BOOK_SIZE * 12)
            rows.append({"topic":name,"words":len(words),"word_search_books":books,"cryptograms":0,"cryptogram_books":0,"trivia":0,"trivia_books":0,
                         "portfolio_required_words": required_words(), "portfolio_ready": plan["portfolio_ready"], "portfolio_gap": plan["gap"],
                         "next_step":"Ready for 2 standard Word Searches + a Signature Edition" if plan["portfolio_ready"] else "Expand topic words for the planned 2 standard books + Signature Edition"})
    return rows

def blueprint(topic: str, puzzle_type: str = "Word Search") -> dict:
    """Safe defaults a creator can adopt in one click, never a fake readiness promise."""
    topic=str(topic or "").strip() or "General Interest"
    type_name=str(puzzle_type or "Word Search")
    counts={"Word Search":48,"Sudoku":60,"Cryptogram":60,"Word Scramble + Trivia":60,"Mixed Brain Games":60}
    styles={"Word Search":"Calm Modern","Sudoku":"Calm Modern","Cryptogram":"Signature Collection","Word Scramble + Trivia":"Playful Learning","Mixed Brain Games":"Playful Learning"}
    return {"topic":topic,"puzzle_type":type_name,"puzzle_count":counts.get(type_name,48),"interior_style":styles.get(type_name,"Studio Classic"),"bonuses":["Completion certificate","Puzzle progress tracker","About this topic facts","Extra challenge page","Next-book preview"],"cover_direction":"Automatic matching","launch_marketplaces":["amazon","etsy","website"]}
