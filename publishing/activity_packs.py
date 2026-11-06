"""Small printable packs using the established puzzle engines.

This is a digital-printable route, not a shortcut around book production gates.
It never registers a commercial book, publishes a listing, or changes a catalog.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import random
import re
import shutil
import tempfile
import zipfile

from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen.canvas import Canvas

from font_utils import pdf_font_candidates, register_pdf_font
import sudoku
import wordsearch

PRESETS = {
    "Road Trip": "JOURNEY HIGHWAY MAP COMPASS SUITCASE PICNIC CAMERA BRIDGE TUNNEL MOUNTAIN VALLEY FOREST LAKE RIVER BEACH TRAIL CAMPING CABIN SUNRISE SUNSET ADVENTURE EXPLORE RESTSTOP SCENERY",
    "Birthday": "BIRTHDAY CANDLES CAKE BALLOONS PRESENTS FRIENDS FAMILY PARTY MUSIC DANCING GAMES WISHES CONFETTI RIBBON INVITATION CELEBRATE LAUGHTER CUPCAKE FROSTING DECORATIONS SURPRISE CARDS STREAMERS SMILES",
    "Garden": "GARDEN FLOWER SEED ROOT STEM LEAF PETAL SOIL WATER SUNSHINE COMPOST MULCH SPADE RAKE TROWEL BEETLE BUTTERFLY LADYBUG SPROUT HARVEST TOMATO CARROT LETTUCE RADISH",
    "Space": "PLANET ORBIT ROCKET GALAXY COMET METEOR MOON SOLAR LUNAR SATURN JUPITER VENUS MARS EARTH NEBULA COSMOS STAR TELESCOPE ASTRONAUT SATELLITE GRAVITY ECLIPSE CRATER ASTEROID",
    "Winter Holidays": "WINTER SNOWFLAKE MITTENS SCARF COCOA COOKIE CANDLE WREATH RIBBON HOLLY GIFT BELLS CAROL SLEIGH REINDEER STOCKING GINGERBREAD ORNAMENT FESTIVE EVERGREEN SNOWMAN FROST FIREPLACE CELEBRATION",
}
FORMATS = ("Word Search", "Word Scramble", "Sudoku")
WORDS_PER_PAGE = 8


@dataclass(frozen=True)
class ActivityPackPlan:
    title: str
    words: tuple[str, ...] = ()
    recipient: str = ""
    theme: str = "Custom"
    formats: tuple[str, ...] = FORMATS
    activity_count: int = 6
    difficulty: str = "easy"
    seed: int = 1
    reader_profile: str = 'standard'
    theme_balance: str = 'Balanced'


def parse_words(text: str) -> tuple[str, ...]:
    """Keep multiword entries together; never silently discard invalid input."""
    return tuple(part.strip() for part in re.split(r"[,\n;]+", text) if part.strip())


def validate_plan(plan: ActivityPackPlan) -> ActivityPackPlan:
    for label, text, limit in (("Title", plan.title, 100), ("Personalization", plan.recipient, 100), ("Theme", plan.theme, 60)):
        if not isinstance(text, str) or len(text) > limit or any(ord(ch) < 32 for ch in text):
            raise ValueError(f"{label} must be plain text of at most {limit} characters.")
    if not plan.title.strip():
        raise ValueError("Enter a title for this activity pack.")
    if not plan.formats or len(set(plan.formats)) != len(plan.formats) or any(kind not in FORMATS for kind in plan.formats):
        raise ValueError("Choose one or more different supported activity types.")
    if type(plan.activity_count) is not int or not len(plan.formats) <= plan.activity_count <= 24:
        raise ValueError("Choose 1 to 24 activity pages, with at least one page per selected type.")
    if plan.difficulty not in ("easy", "medium", "hard"):
        raise ValueError("Choose easy, medium, or hard Sudoku difficulty.")
    if type(plan.seed) is not int or not 0 <= plan.seed <= 2**31 - 1:
        raise ValueError("Use a seed from 0 to 2147483647.")
    from .studio_reader_profiles import reader_profile, check_reader_topic, BALANCES
    reader_profile(plan.reader_profile)
    check_reader_topic(plan.theme + ' ' + plan.title, plan.reader_profile)
    if plan.theme_balance not in BALANCES: raise ValueError('Choose a supported theme balance.')
    kinds = [plan.formats[index % len(plan.formats)] for index in range(plan.activity_count)]
    words = []
    if any(kind != "Sudoku" for kind in kinds):
        # Reuse the application's current protected-term policy, including future updates.
        from word_search_creator import REVIEW_REQUIRED_TERMS
        protected = {re.sub(r"[ -]", "", term.upper()) for term in REVIEW_REQUIRED_TERMS}
        for raw in plan.words:
            word = re.sub(r"[ -]", "", str(raw).strip().upper())
            if not re.fullmatch(r"[A-Z]{2,18}", word):
                raise ValueError(f"'{raw}' must contain 2 to 18 English letters (spaces and hyphens are allowed).")
            if word in protected:
                raise ValueError(f"'{raw}' requires content review and cannot enter this automatic route.")
            if len(set(word)) == 1 and "Word Scramble" in kinds:
                raise ValueError(f"'{raw}' cannot make a meaningful word scramble.")
            if word in words:
                raise ValueError(f"'{raw}' duplicates another entry after spaces and hyphens are removed.")
            from .studio_reader_profiles import word_suits_reader
            if not word_suits_reader(word, plan.reader_profile):
                raise ValueError(f"'{raw}' does not fit the selected reader profile. Refresh automatic words or choose another profile.")
            words.append(word)
        needed = max(kinds.count("Word Search"), kinds.count("Word Scramble")) * WORDS_PER_PAGE
        if len(words) < needed:
            raise ValueError(f"Add at least {needed} different words for this plan (8 per word-activity page). Words do not repeat within the same activity type.")
        if len(words) > 500:
            raise ValueError("Use at most 500 different words per pack.")
    return ActivityPackPlan(plan.title.strip(), tuple(words), plan.recipient.strip(), plan.theme.strip(), tuple(plan.formats), plan.activity_count, plan.difficulty, plan.seed, plan.reader_profile, plan.theme_balance)


def generate_activities(plan: ActivityPackPlan) -> list[dict]:
    plan = validate_plan(plan)
    from .studio_reader_profiles import reader_profile
    profile = reader_profile(plan.reader_profile)
    rng = random.Random(plan.seed)
    pools = {}
    for kind in ("Word Search", "Word Scramble"):
        pools[kind] = list(plan.words)
        rng.shuffle(pools[kind])
    activities = []
    for index in range(plan.activity_count):
        kind = plan.formats[index % len(plan.formats)]
        item = {"number": index + 1, "kind": kind}
        if kind == "Sudoku":
            solved = sudoku.make_solved(rng)
            puzzle, rating = sudoku.make_rated_puzzle(solved, plan.difficulty, rng)
            if sudoku.count_solutions([row[:] for row in puzzle]) != 1:
                raise ValueError("Sudoku uniqueness check failed; no pack was saved.")
            item.update(grid=puzzle, solution=solved)
            from .sudoku_difficulty import rate_sudoku
            item['difficulty_evidence']=rate_sudoku(puzzle)
        else:
            words = pools[kind][:WORDS_PER_PAGE]
            del pools[kind][:WORDS_PER_PAGE]
            if kind == "Word Search":
                grid, placements, placed = wordsearch.generate_puzzle(words, max(profile['grid'], max(map(len, words))), directions=profile['directions'], rng=rng)
                if sorted(placed) != sorted(words):
                    raise ValueError("The word search could not place every word; no pack was saved.")
                if any("".join(grid[r][c] for r, c in cells) != word for word, cells in zip(placed, placements)):
                    raise ValueError("Word-search answer verification failed.")
                item.update(words=placed, grid=grid, placements=placements)
                from .puzzle_integrity import wordsearch_difficulty
                item['difficulty_evidence']=wordsearch_difficulty(grid,placements,placed)
            else:
                # A rotation always differs for a nonuniform word, unlike finite shuffle retries.
                from puzzle_book_studio import scramble
                shown = []
                for word in words:
                    mixed = scramble(word, rng)
                    if mixed == word:
                        mixed = next(word[n:] + word[:n] for n in range(1, len(word)) if word[n:] + word[:n] != word)
                    shown.append(mixed)
                item.update(words=words, scrambled=shown)
        activities.append(item)
    return activities


def _fonts():
    for alias, family in (("Sans", "sans"), ("SansB", "sans-bold"), ("MonoB", "mono-bold")):
        if not register_pdf_font(alias, pdf_font_candidates(family)):
            raise RuntimeError(f"A required font is missing: {family}.")


def _lines(c, text, y, size=13, bold=False, centered=False):
    """Wrap even a single long title/word inside the printable area."""
    face = "SansB" if bold else "Sans"
    c.setFont(face, size)
    lines, line = [], ""
    for word in text.split():
        trial = (line + " " + word).strip()
        if c.stringWidth(trial, face, size) <= 504:
            line = trial
            continue
        if line:
            lines.append(line)
            line = ""
        for ch in word:
            if c.stringWidth(line + ch, face, size) > 504:
                lines.append(line)
                line = ""
            line += ch
    if line:
        lines.append(line)
    for line in lines:
        (c.drawCentredString(306, y, line) if centered else c.drawString(54, y, line))
        y -= size * 1.5
    return y


def _page_end(c, page):
    c.setFont("Sans", 9)
    c.drawCentredString(306, 35, f"SladePuzzleCo | {page}")
    c.showPage()


def render_pdfs(folder: Path, plan: ActivityPackPlan, activities: list[dict]):
    _fonts()
    for answers, name in ((False, "ACTIVITIES.pdf"), (True, "ANSWERS.pdf")):
        c = Canvas(str(folder / name), pagesize=letter, invariant=1)
        c.setTitle(plan.title + (" - Answers" if answers else " - Activities"))
        c.setAuthor("SladePuzzleCo")
        y = _lines(c, "ANSWER SHEETS" if answers else "PRINTABLE ACTIVITY PACK", 690, 15, True, True)
        y = _lines(c, plan.title, y - 25, 22, True, True)
        if plan.recipient:
            y = _lines(c, plan.recipient, y - 20, 16, centered=True)
        y = _lines(c, f"{plan.activity_count} activities | Theme: {plan.theme}", y - 30, centered=True)
        from .studio_reader_profiles import reader_profile
        profile = reader_profile(plan.reader_profile)
        if plan.reader_profile != 'standard':
            y = _lines(c, profile['label'] + ' | Adult preview recommended', y - 16, 11, centered=True)
        y -= 20
        if answers:
            _lines(c, "Match each answer sheet to the activity number. Keep these sheets separate when handing out activities.", y)
        else:
            for text in (
                "Print on US Letter paper at Actual Size / 100%. Choose the activity pages you want. Answers are in a separate PDF.",
                'Word Search: ' + profile['instructions'],
                "Word Scramble: rearrange the letters into a theme word. Answers show the intended words; other valid anagrams may exist.",
                "Sudoku: use 1 to 9 in every row, column, and 3 by 3 box without repeating a number.",
            ):
                if text.startswith("Word Search") and "Word Search" not in plan.formats: continue
                if text.startswith("Word Scramble") and "Word Scramble" not in plan.formats: continue
                if text.startswith("Sudoku") and "Sudoku" not in plan.formats: continue
                y = _lines(c, text, y, 12) - 12
        _page_end(c, 1)
        for item in activities:
            number, kind = item["number"], item["kind"]
            _lines(c, f"Activity {number}: {kind}" + (" - Answers" if answers else ""), 730, 20, True)
            if kind == "Word Search":
                n = len(item["grid"])
                cell = min(28, 504 / n)
                wordsearch.draw_grid(c, item["grid"], (612 - cell*n)/2, 665, cell, cell*.58, item["placements"] if answers else None)
                # Two columns accommodate the longest accepted words at 12 pt.
                top = 665 - cell*n - 25
                for i, word in enumerate(item["words"]):
                    c.setFont("Sans", profile.get('minimum_word_font_pt',12))
                    c.drawString(60 + (i % 2)*252, top - (i//2)*23, word)
            elif kind == "Sudoku":
                sudoku.draw_sudoku(c, item["solution"] if answers else item["grid"], 81, 665, 50, "MonoB", 27)
                _lines(c, f"Difficulty: {item['difficulty_evidence']['label']}", 160, 12)
            else:
                for i, (word, mixed) in enumerate(zip(item["words"], item["scrambled"]), 1):
                    y = 650 - (i-1)*65
                    _lines(c, f"{i}. {mixed}" + (f"  =  {word}" if answers else ""), y, 16, True)
                    if not answers:
                        c.line(80, y-30, 550, y-30)
            _page_end(c, number + 1)
        c.save()


def build_activity_pack(plan: ActivityPackPlan, output_root: Path) -> Path:
    """Assemble a complete local folder; never overwrite an existing pack."""
    plan = validate_plan(plan)
    activities = generate_activities(plan)
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    # A reserved unique directory is retained only once the complete pack is ready.
    slug = re.sub(r"[^a-z0-9]+", "_", plan.title.casefold()).strip("_")[:48] or "activity_pack"
    staging = Path(tempfile.mkdtemp(prefix=".activity_pack_", dir=output_root))
    destination = None
    try:
        render_pdfs(staging, plan, activities)
        for name in ("ACTIVITIES.pdf", "ANSWERS.pdf"):
            reader = PdfReader(staging / name)
            if len(reader.pages) != plan.activity_count + 1 or any(not (page.extract_text() or "").strip() for page in reader.pages):
                raise ValueError(f"Printable proof failed for {name}.")
            if any(tuple(float(v) for v in page.mediabox) != (0.0, 0.0, 612.0, 792.0) for page in reader.pages):
                raise ValueError(f"Incorrect page size in {name}.")
        readme = (f"{plan.title}\n\nPrint ACTIVITIES.pdf for players; keep ANSWERS.pdf separately.\n"
                  "Paper: US Letter, Actual Size / 100%. Each PDF starts with an introduction.\n"
                  "The theme applies to word activities; Sudoku uses numbers. Vocabulary may recur across different activity types.\n"
                  "Review all content and print a sample before distribution or commercial use.\n"
                  "These are printable activity files, not a KDP publishing package. Nothing was uploaded or published.\n")
        (staging / "READ_ME.txt").write_text(readme, encoding="utf-8")
        manifest = {"schema_version": 1, "product_type": "printable_activity_pack", "plan": asdict(plan), "activities": activities,
                    "proof": {"status": "local_checks_passed", "human_review": "required", "page_size": "US Letter", "pages_per_pdf": plan.activity_count + 1},
                    "sha256": {name: hashlib.sha256((staging / name).read_bytes()).hexdigest() for name in ("ACTIVITIES.pdf", "ANSWERS.pdf")}}
        (staging / "PACK_MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        with zipfile.ZipFile(staging / "PRINTABLE_PACK.zip", "w", zipfile.ZIP_DEFLATED) as archive:
            for name in ("ACTIVITIES.pdf", "ANSWERS.pdf", "READ_ME.txt"):
                archive.write(staging / name, name)
        # mkdtemp ensures collision-free names even for simultaneous identical plans.
        destination = Path(tempfile.mkdtemp(prefix=slug + "_", dir=output_root))
        for source in staging.iterdir():
            shutil.move(str(source), destination / source.name)
        return destination
    except Exception:
        if destination is not None:
            shutil.rmtree(destination)
        raise
    finally:
        shutil.rmtree(staging)
