"""Generate resumable, review-only replacement banks for blocked Word Searches.

This tool never edits a live theme and never marks generated vocabulary as
approved.  It uses the configured Gemini candidate provider to propose small,
coherent page batches, applies the same local length/duplicate/protected-name
screens as production, and writes a candidate file for editorial review.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from publishing.listing_intelligence import GeminiCredentials, _interaction_output_text
from build_master_word_bank import EXTRA_REJECTED_TERMS
from word_search_creator import REVIEW_REQUIRED_TERMS


TARGET = ROOT / "word_banks" / "editorial_wordsearch_rebuild_candidates.json"
BATCH_PAGES = 8


BOOKS = {
    "classic_cars": {
        "title": "Classic Cars and Road Trips Word Search", "puzzles": 48,
        "topic": "classic cars, automotive history, restoration, garages, vehicle parts, car shows, and scenic driving",
        "audience": "adult classic-car and road-trip enthusiasts",
        "avoid": "air travel, international travel, modern brand names, model names, celebrities",
    },
    "grade_school": {
        "title": "Vocabulary Adventures: Grade School", "puzzles": 48,
        "topic": "useful grade-school vocabulary across reading, writing, math, science, social studies, arts, study habits, and everyday life",
        "audience": "children in grades 3 through 5",
        "avoid": "people names, country names, brands, politics, violence, adult themes, archaic or highly technical words",
    },
    "advanced_vocabulary": {
        "title": "Advanced Vocabulary Challenge Word Search", "puzzles": 48,
        "topic": "recognizable advanced English vocabulary grouped by meaning and real-life use",
        "audience": "teens and adults who enjoy learning stronger vocabulary",
        "avoid": "people names, place names, brands, slurs, graphic terms, obscure scientific taxonomy, malformed words",
    },
    "faithful_words": {
        "title": "Faithful Words Word Search", "puzzles": 50,
        "topic": "reader-friendly Bible and Christian faith vocabulary: familiar people, places, virtues, worship, prayer, parables, service, hope, and community",
        "audience": "adult and senior Christian puzzle solvers",
        "avoid": "obscure genealogy names, archaic verb forms, unexplained concordance fragments, denominational controversy, unrelated generic words",
    },
    "road_trip": {
        "title": "Road Trip Classics Word Search", "puzzles": 50,
        "topic": "road trips, highways, maps, roadside stops, scenic routes, camping travel, packing, navigation, and shared travel moments",
        "audience": "adult and teen travel puzzle fans",
        "avoid": "engine parts, restoration jargon, vehicle brands or models, air travel, cruises, international-document terminology",
    },
    "american_history": {
        "title": "American Moments Word Search", "puzzles": 50,
        "topic": "United States history grouped by eras, civics, movements, inventions, landmarks, daily life, exploration, and public institutions",
        "audience": "general adult and teen history readers",
        "avoid": "unsupported trivia claims, isolated generic verbs, partisan slogans, living politicians, brands, graphic violence",
    },
    "faith_signature": {
        "title": "Faithful Words: Large-Print Bible Word Search for Adults", "puzzles": 100,
        "topic": "broad but reader-friendly Bible and Christian faith vocabulary: books, familiar people and places, teachings, virtues, worship, prayer, service, fellowship, hope, gratitude, and reflection",
        "audience": "adult and senior Christian puzzle solvers",
        "avoid": "obscure genealogy names, archaic verb forms, unexplained concordance fragments, denominational controversy, unrelated generic words",
    },
    "grade_5": {
        "title": "Vocabulary Ladder: Grade 5 Word Quest", "puzzles": 48,
        "topic": "grade 5 vocabulary grouped by reading, writing, math, life science, earth science, social studies, arts, learning skills, and everyday communication",
        "audience": "fifth-grade students and families",
        "avoid": "people names, country names, brands, politics, violence, adult themes, archaic words, high-school-only terminology",
    },
}

# Public editorial directions only.  They keep successive provider batches in
# different parts of a broad topic without transmitting any local vocabulary.
FOCUS_TRACKS = {
    "Classic Cars and Road Trips Word Search": [
        "vintage exterior features, body styles, paint and trim", "engines, cooling, fuel and exhaust",
        "transmissions, steering, suspension and brakes", "interiors, dashboards, seating and comfort",
        "restoration shops, hand tools, detailing and maintenance", "car shows, clubs, judging and collecting",
        "highway driving, scenic routes and roadside memories", "tires, wheels, lighting, safety and weather driving"],
    "Vocabulary Adventures: Grade School": [
        "reading and story language", "writing, spelling and grammar", "whole numbers, fractions and geometry",
        "life science and ecosystems", "earth, weather and space science", "communities, maps and civics",
        "music, art and creative making", "study habits, cooperation and everyday communication",
        "health, movement, safety and healthy routines", "libraries, research and age-appropriate technology"],
    "Advanced Vocabulary Challenge Word Search": [
        "thinking and reasoning", "communication and persuasion", "emotion and character", "society and leadership",
        "science and discovery", "arts and literature", "work, planning and achievement", "change, contrast and degree",
        "time, sequence, causes and consequences", "ethics, cooperation and responsible decisions"],
    "Faithful Words Word Search": [
        "faith, hope and encouragement", "prayer, worship and praise", "familiar Bible people and places",
        "parables, teachings and wisdom", "virtues, character and spiritual growth", "service, fellowship and community",
        "gratitude, peace and reflection", "Christian celebrations, symbols and church life",
        "sacred music, hymns and joyful praise"],
    "Road Trip Classics Word Search": [
        "planning, packing and departure", "maps, routes and navigation", "highways, signs and road safety",
        "scenic landscapes and overlooks", "roadside stops, diners and attractions", "campgrounds, cabins and picnics",
        "travel games, music and shared memories", "weather, seasons and road conditions",
        "lodging, cabins and overnight stops", "roadside nature and wildlife viewing"],
    "American Moments Word Search": [
        "Indigenous cultures and early exploration", "colonial life and independence", "the Constitution and civic institutions",
        "westward movement and transportation", "abolition, the Civil War and Reconstruction", "immigration and industrial growth",
        "inventions, communication and daily life", "civil rights, public service and national landmarks",
        "agriculture, home life and changing communities", "education, science and historic preservation"],
    "Faithful Words: Large-Print Bible Word Search for Adults": [
        "books and sections of the Bible", "familiar people of the Old Testament", "familiar people of the New Testament",
        "well-known biblical places", "prayer and worship", "faith, hope and trust", "wisdom and teachings",
        "virtues and spiritual growth", "parables and familiar stories", "service and compassion",
        "fellowship and community", "gratitude, peace and reflection", "symbols, celebrations and church life",
        "sacred music and hymns", "missions, hospitality and caring for neighbors",
        "familiar biblical objects, clothing and materials", "occupations and daily life in biblical times",
        "biblical landscapes, farming and animals", "journeys, travelers and welcoming guests",
        "the early church, discipleship and letters", "Christian family life and teaching children",
        "comfort, courage and perseverance", "stewardship, creation and thankful living",
        "church calendar seasons and celebrations", "ways of praying and quiet devotion"],
    "Vocabulary Ladder: Grade 5 Word Quest": [
        "fifth-grade reading and story elements", "fifth-grade writing, spelling and grammar", "fractions, decimals and geometry",
        "life science and ecosystems", "earth systems, weather and space", "United States geography and civics",
        "art, music and creative projects", "study skills, teamwork and communication",
        "health, movement, safety and healthy choices", "libraries, research and digital citizenship"],
}


def normalized(value: object) -> str:
    return re.sub(r"[^A-Z]", "", str(value or "").upper())


def load_state() -> dict:
    if TARGET.is_file():
        return json.loads(TARGET.read_text(encoding="utf-8"))
    return {"schema_version": 1, "status": "REVIEW_REQUIRED", "provider": "Gemini",
            "created_at": datetime.now().isoformat(timespec="seconds"), "books": {}}


def save_state(state: dict) -> None:
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def request_pages(credentials: GeminiCredentials, spec: dict, start: int,
                  count: int, attempt: int) -> list[dict]:
    tracks = FOCUS_TRACKS.get(spec["title"], [])
    track = tracks[(((start - 1) // BATCH_PAGES) + attempt - 1) % len(tracks)] if tracks else spec["topic"]
    prompt = f"""Create exactly {count} coherent Word Search puzzle pages for this commercial puzzle book.
BOOK: {spec['title']}
TOPIC PROMISE: {spec['topic']}
AUDIENCE: {spec['audience']}
PAGE NUMBERS: {start} through {start + count - 1}
THIS BATCH'S DISTINCT FOCUS: {track}

For every page provide a short, specific mini-theme title and exactly 12 unique, natural words or short phrases that all clearly fit that mini-theme and the book promise. Every entry must be 3–21 letters after spaces and punctuation are removed. Across this response, do not repeat any normalized entry. Prefer recognizable vocabulary over obscure filler. Do not create artificial compound words merely to make entries unique. No brands, franchises, celebrities, or trademarked model names.
AVOID: {spec['avoid']}
This is batch {start}; choose varied mini-themes and vocabulary. Duplicate
screening against earlier batches is performed locally and no local word-bank
content is sent to the provider.
Retry number: {attempt}
Return only the required JSON."""
    schema = {"type": "object", "properties": {"pages": {"type": "array", "items": {
        "type": "object", "properties": {"name": {"type": "string"}, "words": {
            "type": "array", "items": {"type": "string"}}}, "required": ["name", "words"],
        "additionalProperties": False}}}, "required": ["pages"], "additionalProperties": False}
    body = {"model": credentials.model, "input": prompt, "store": False,
            "generation_config": {"max_output_tokens": 6000, "thinking_level": "minimal"},
            "response_format": {"type": "text", "mime_type": "application/json", "schema": schema}}
    call = urllib.request.Request("https://generativelanguage.googleapis.com/v1beta/interactions",
        data=json.dumps(body).encode(), headers={"x-goog-api-key": credentials.api_key,
        "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(call, timeout=60) as response:
        payload = json.loads(response.read().decode())
    if str(payload.get("status") or "").casefold() == "incomplete":
        raise RuntimeError("Gemini response was incomplete")
    parsed = json.loads(_interaction_output_text(payload))
    rows = parsed.get("pages") if isinstance(parsed, dict) else None
    if not isinstance(rows, list):
        raise RuntimeError("Gemini returned no page list")
    return rows


def validate_batch(rows: list[dict], expected: int, used: set[str]) -> tuple[list[dict], list[str]]:
    issues: list[str] = []
    if len(rows) != expected:
        issues.append(f"expected {expected} pages; received {len(rows)}")
    clean_rows: list[dict] = []
    batch_seen: set[str] = set()
    for offset, row in enumerate(rows[:expected], 1):
        name = str(row.get("name") or "").strip()
        words = row.get("words") if isinstance(row, dict) else None
        if not name:
            issues.append(f"page {offset}: blank mini-theme")
        if not isinstance(words, list) or len(words) != 12:
            issues.append(f"page {offset}: expected 12 words")
            continue
        cleaned: list[str] = []
        for raw in words:
            display = " ".join(str(raw or "").strip().split())
            norm = normalized(display)
            if not 3 <= len(norm) <= 21:
                issues.append(f"page {offset}: invalid length {display!r}")
            elif norm in used or norm in batch_seen:
                issues.append(f"page {offset}: duplicate {display!r}")
            elif norm in REVIEW_REQUIRED_TERMS or norm in EXTRA_REJECTED_TERMS:
                issues.append(f"page {offset}: protected/rejected {display!r}")
            elif not re.fullmatch(r"[A-Za-z][A-Za-z '&-]*", display):
                issues.append(f"page {offset}: malformed {display!r}")
            else:
                cleaned.append(display.upper())
                batch_seen.add(norm)
        if len(cleaned) == 12:
            clean_rows.append({"name": name, "words": cleaned})
    return clean_rows, issues


def generate_book(credentials: GeminiCredentials, state: dict, key: str, spec: dict) -> None:
    book = state["books"].setdefault(key, {**spec, "pages": [], "issues": []})
    used = {normalized(word) for page in book.get("pages", []) for word in page.get("words", [])}
    while len(book["pages"]) < spec["puzzles"]:
        start = len(book["pages"]) + 1
        count = min(BATCH_PAGES, spec["puzzles"] - len(book["pages"]))
        last_issues: list[str] = []
        for attempt in range(1, 6):
            try:
                rows = request_pages(credentials, spec, start, count, attempt)
                clean, issues = validate_batch(rows, count, used)
            except urllib.error.HTTPError as exc:
                clean, issues = [], [f"Gemini HTTP {exc.code}"]
                if exc.code == 429:
                    # Bounded provider backoff; the saved file makes the run
                    # safely resumable if account quota remains unavailable.
                    time.sleep(min(20, attempt * 4))
            except (urllib.error.URLError, TimeoutError, ValueError, RuntimeError) as exc:
                clean, issues = [], [str(exc)]
            # Keep only complete, locally clean pages.  A partial batch is
            # useful and safe; the next request fills the remaining pages.
            # We never keep a page containing one invalid or repeated entry.
            if clean:
                clean = clean[:spec["puzzles"] - len(book["pages"])]
                book["pages"].extend(clean)
                used.update(normalized(word) for page in clean for word in page["words"])
                book["issues"] = issues
                save_state(state)
                print(f"{key}: {len(book['pages'])}/{spec['puzzles']} pages", flush=True)
                break
            last_issues = issues
        else:
            book["issues"] = last_issues
            save_state(state)
            raise RuntimeError(f"{key} stopped at page {start}: {'; '.join(last_issues[:8])}")
    book["unique_words"] = len(used)
    book["completed_at"] = datetime.now().isoformat(timespec="seconds")
    save_state(state)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", choices=["all", *BOOKS], default="all")
    args = parser.parse_args()
    credentials = GeminiCredentials.load()
    if not credentials:
        raise SystemExit("Gemini credentials are not configured.")
    state = load_state()
    selected = BOOKS.items() if args.book == "all" else [(args.book, BOOKS[args.book])]
    for key, spec in selected:
        generate_book(credentials, state, key, spec)
    print(TARGET)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
