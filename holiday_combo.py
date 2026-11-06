"""Build the reviewed, ten-chapter Holiday Word Search + Sudoku collection.

This dedicated route reuses the existing puzzle and cover engines. It never
silently reduces a chapter or substitutes unrelated Master Library vocabulary.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader
from reportlab.pdfgen import canvas

import sudoku
import wordsearch
from publishing.sudoku_difficulty import rate_sudoku
from background_generation.index import require_production_approved_cover_asset, verify_rendered_cover_approval
from preflight import preflight, report_text
from publishing.package_layout import initialize_package_layout, package_file, release_contract
from sudoku_symbols import PACKS, draw_symbol, pack_label


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "word_banks" / "holiday_wordsearch_sudoku_200.json"
APPROVED_ART = ROOT / "cover_assets" / "generated_backgrounds" / "approved" / "holiday_year_round_20260921.png"
TITLE = "Celebrate All Year"
SUBTITLE = "200 Holiday Word Search & Sudoku Puzzles Across 10 Celebrations"
AUTHOR = "Jordan M. Slade"
TYPE = "Word Search + Sudoku"
W, H = wordsearch.PAGE_W, wordsearch.PAGE_H


@dataclass(frozen=True)
class WordPlan:
    number: int
    holiday: str
    mini_theme: str
    words: tuple[str, ...]


@dataclass(frozen=True)
class SudokuPlan:
    number: int
    holiday: str
    style: str
    symbol_pack: str
    difficulty: str
    puzzle: sudoku.SudokuGrid
    solution: sudoku.SudokuGrid


def load_source(path: Path = SOURCE) -> list[dict]:
    source = json.loads(path.read_text(encoding="utf-8"))
    holidays = source["holidays"]
    if len(holidays) != 10 or len({h["name"] for h in holidays}) != 10:
        raise ValueError("The source must contain ten distinct holiday chapters.")
    for holiday in holidays:
        if holiday["symbol_pack"] not in PACKS or len(PACKS[holiday["symbol_pack"]]) != 9:
            raise ValueError(f"Missing nine-symbol pack for {holiday['name']}")
        mini_themes = holiday["mini_themes"]
        if len(mini_themes) != 5:
            raise ValueError(f"{holiday['name']} needs five reviewed mini-themes.")
        used: set[str] = set()
        for label, raw in mini_themes.items():
            words = [part.strip().upper() for part in raw.split("|")]
            if len(words) != 24 or any(not re.fullmatch(r"[A-Z]{2,15}", item) for item in words):
                raise ValueError(f"{holiday['name']} / {label} needs 24 valid 2–15 letter entries.")
            if len(set(words)) != 24 or used.intersection(words):
                raise ValueError(f"Repeated word within {holiday['name']} / {label}.")
            used.update(words)
        if len(used) != 120:
            raise ValueError(f"{holiday['name']} does not have 120 distinct words.")
    return holidays


def build_plan(holidays: list[dict], seed: int = 20260921) -> tuple[list[WordPlan], list[SudokuPlan]]:
    rng = random.Random(seed)
    words: list[WordPlan] = []
    sudokus: list[SudokuPlan] = []
    sudoku_fingerprints: set[str] = set()
    for chapter, holiday in enumerate(holidays):
        name = holiday["name"]
        for label, raw in holiday["mini_themes"].items():
            pool = raw.split("|")
            # Keep every reviewed target, but partition compound hosts safely.
            # A short target cannot share a grid with several containing words.
            for _ in range(256):
                rng.shuffle(pool)
                try:
                    for start in (0, 12):
                        wordsearch.validate_word_set(pool[start:start + 12], 15)
                    break
                except ValueError:
                    continue
            else:
                raise ValueError(f"{name} / {label}: the full reviewed set cannot be partitioned into two valid word searches.")
            for start in (0, 12):
                selection = pool[start:start + 12]
                rng.shuffle(selection)
                words.append(WordPlan(chapter * 20 + len(words) % 10 + 1,
                                      name, label, tuple(selection)))
        for slot in range(10):
            difficulty = ("easy", "medium", "medium", "easy", "hard")[slot % 5]
            for _ in range(12):
                solution = sudoku.make_solved(rng)
                puzzle, rating = sudoku.make_rated_puzzle(solution, difficulty, rng)
                fingerprint = "".join(str(v) for row in puzzle for v in row)
                if fingerprint not in sudoku_fingerprints:
                    break
            else:
                raise ValueError("Could not produce a fresh Sudoku grid.")
            sudoku_fingerprints.add(fingerprint)
            sudokus.append(SudokuPlan(chapter * 20 + 11 + slot, name,
                                      "numbers" if slot < 5 else "shapes",
                                      holiday["symbol_pack"], rate_sudoku(puzzle)['label'], puzzle, solution))
    if len(words) != 100 or len(sudokus) != 100:
        raise ValueError("The 200-puzzle plan is incomplete.")
    return words, sudokus


def _footer(c: canvas.Canvas, page: int) -> None:
    wordsearch.footer(c, page)


def _paragraph(c: canvas.Canvas, lines: list[str], top: float, *, font: str = "Sans", size: int = 12,
               leading: int = 21) -> None:
    c.setFont(font, size)
    c.setFillGray(.19)
    for index, line in enumerate(lines):
        c.drawString(72, top - index * leading, line)


def _holiday_title_page(c: canvas.Canvas, holidays: list[dict]) -> None:
    """A book-specific, low-ink opening that previews all ten symbol families."""
    c.saveState()
    c.setStrokeGray(.52)
    c.setLineWidth(.75)
    c.roundRect(55, 55, W - 110, H - 110, 11, stroke=1, fill=0)
    c.setLineWidth(0.75)
    c.roundRect(62, 62, W - 124, H - 124, 8, stroke=1, fill=0)

    c.setFillGray(.32)
    c.setFont("SansB", 9)
    c.drawCentredString(W / 2, 703, "SLADE PUZZLES  /  THE YEAR-ROUND COLLECTION")
    c.setStrokeGray(.62)
    c.line(165, 691, W - 165, 691)

    c.setFillGray(.08)
    c.setFont("SansB", 48)
    c.drawCentredString(W / 2, 617, "CELEBRATE")
    c.drawCentredString(W / 2, 565, "ALL YEAR")
    c.setFillGray(.35)
    c.setFont("Sans", 11.5)
    c.drawCentredString(W / 2, 531, "200 HOLIDAY WORD SEARCH & SUDOKU PUZZLES")
    c.drawCentredString(W / 2, 511, "ACROSS TEN CELEBRATIONS")

    c.setStrokeGray(.60)
    c.setLineWidth(0.75)
    c.line(92, 474, 244, 474)
    c.line(368, 474, 520, 474)
    c.setFillGray(.28)
    c.setFont("SansB", 9)
    c.drawCentredString(W / 2, 471, "THE YEAR IN PUZZLES")

    labels = ("NEW YEAR", "VALENTINE", "EASTER", "MOTHER'S DAY", "FATHER'S DAY",
              "JULY FOURTH", "HALLOWEEN", "THANKSGIVING", "HANUKKAH", "CHRISTMAS")
    for index, (holiday, label) in enumerate(zip(holidays, labels)):
        column, row = index % 5, index // 5
        x, y = 108 + column * 99, 411 - row * 119
        c.setStrokeGray(.66)
        c.setLineWidth(0.75)
        c.circle(x, y, 29, stroke=1, fill=0)
        draw_symbol(c, holiday["symbol_pack"], 1, x, y, 51)
        c.setFillGray(.37)
        c.setFont("SansB", 7.5)
        c.drawCentredString(x, y + 39, f"{index + 1:02d}")
        c.setFont("SansB", 8)
        c.setFillGray(.20)
        c.drawCentredString(x, y - 43, label)

    c.setStrokeGray(.65)
    c.line(181, 212, 431, 212)
    c.setFillGray(.10)
    c.setFont("SansB", 25)
    c.drawCentredString(220, 176, "100")
    c.drawCentredString(392, 176, "100")
    c.setFont("SansB", 8.5)
    c.setFillGray(.29)
    c.drawCentredString(220, 158, "12-WORD SEARCHES")
    c.drawCentredString(392, 158, "SUDOKU PUZZLES")
    c.setFont("Sans", 8)
    c.drawCentredString(392, 145, "50 numbers + 50 holiday symbols")
    c.setStrokeGray(.65)
    c.line(W / 2, 143, W / 2, 195)

    c.setFillGray(.12)
    c.setFont("SansB", 12)
    c.drawCentredString(W / 2, 105, AUTHOR)
    c.setFillGray(.43)
    c.setFont("SansB", 8)
    c.drawCentredString(W / 2, 86, "SLADE PUZZLES")
    c.restoreState()
    c.showPage()


def _front_pages(c: canvas.Canvas, holidays: list[dict]) -> int:
    _holiday_title_page(c, holidays)
    c.setTitle(TITLE); c.setAuthor(AUTHOR); c.setSubject(SUBTITLE)
    c.setFont("SansB", 22); c.drawString(72, 704, "WELCOME TO THE CELEBRATION")
    _paragraph(c, ["10 holiday chapters. 100 themed word searches. 100 Sudoku puzzles.",
                   "Each chapter contains 10 word searches, 5 number Sudoku puzzles,",
                   "and 5 Sudoku puzzles with symbols chosen for that holiday.", "",
                   "Word search: find each listed word in the grid. Words may run in any",
                   "of eight directions. Each puzzle has 12 words on one focused topic.",
                   "Words are not reused within a holiday chapter; a fitting word may",
                   "return in a different holiday chapter.", "",
                   "Sudoku: place the numbers 1–9, or all nine pictured symbols, so each",
                   "row, column, and 3 x 3 box contains every one exactly once.",
                   "All puzzles have complete solutions at the back."], 652)
    c.setStrokeGray(.72); c.setLineWidth(0.75); c.line(126, 175, W - 126, 175)
    c.setFillGray(.25); c.setFont("SansB", 9)
    c.drawCentredString(W / 2, 150, "Copyright © 2026 Jordan M. Slade")
    c.setFont("Sans", 8.5)
    c.drawCentredString(W / 2, 133, "All rights reserved. Published by Slade Puzzles.")
    c.drawCentredString(W / 2, 116, "No part of this book may be reproduced or distributed without written permission,")
    c.drawCentredString(W / 2, 101, "except for brief quotations used in reviews. First edition, 2026.")
    _footer(c, 2); c.showPage()
    c.setFont("SansB", 23); c.drawString(72, 711, "HOLIDAY CHAPTERS")
    for index, holiday in enumerate(holidays, 1):
        top = 660 - (index - 1) * 51
        c.setFont("SansB", 13); c.drawString(76, top, f"{index:02d}  {holiday['name']}")
        c.setFont("Sans", 10); c.drawRightString(W - 76, top, "10 WORD SEARCH + 10 SUDOKU")
        c.setStrokeGray(.8); c.line(76, top - 8, W - 76, top - 8)
    _footer(c, 3); c.showPage()
    return 4


def _chapter_page(c: canvas.Canvas, holiday: dict, chapter: int, page: int) -> None:
    c.setFillGray(.25); c.setFont("SansB", 12)
    c.drawCentredString(W / 2, 680, f"CHAPTER {chapter} OF 10")
    heading = holiday["name"].upper()
    size = 32
    while c.stringWidth(heading, "SansB", size) > W - 130:
        size -= 1
    c.setFont("SansB", size); c.setFillGray(.1); c.drawCentredString(W / 2, 612, heading)
    c.setStrokeGray(.55); c.line(160, 584, W - 160, 584)
    pack = holiday["symbol_pack"]
    for offset, value in enumerate((1, 2, 3)):
        draw_symbol(c, pack, value, W / 2 + (offset - 1) * 93, 446, 65)
    c.setFont("SansB", 15); c.drawCentredString(W / 2, 330, "20 PUZZLES TO EXPLORE")
    c.setFont("Sans", 12); c.drawCentredString(W / 2, 301,
                    "10 word searches  |  5 number Sudoku  |  5 holiday-symbol Sudoku")
    _footer(c, page); c.showPage()


def _sudoku_page(c: canvas.Canvas, plan: SudokuPlan, chapter: int, page: int) -> None:
    c.setFont("Sans", 10); c.setFillGray(.45); c.drawCentredString(W / 2, 752, TITLE)
    c.setFont("SansB", 12); c.setFillGray(.1); c.drawString(72, 724, f"PUZZLE {plan.number}")
    c.drawRightString(W - 72, 724, f"CHAPTER {chapter}")
    c.setFont("SansB", 21); c.drawCentredString(W / 2, 687, plan.holiday.upper())
    label = "NUMBER SUDOKU" if plan.style == "numbers" else pack_label(plan.symbol_pack)
    c.setFont("SansB", 11); c.setFillGray(.3); c.drawCentredString(W / 2, 663,
             f"{label}  |  {plan.difficulty.upper()}")
    sudoku.draw_sudoku(c, plan.puzzle, 81, 616, 50, "MonoB", 24,
                       display_style=plan.style, symbol_pack=plan.symbol_pack)
    if plan.style == "shapes":
        c.setFont("SansB", 10); c.drawCentredString(W / 2, 135, "USE EACH OF THESE NINE SYMBOLS ONCE PER ROW, COLUMN AND BOX")
        for i in range(9):
            draw_symbol(c, plan.symbol_pack, i + 1, 108 + i * 49.5, 104, 37)
    else:
        c.setFont("Sans", 11); c.drawCentredString(W / 2, 127,
             "Use each number from 1 to 9 once per row, column and 3 x 3 box.")
    _footer(c, page); c.showPage()


def _sudoku_solutions(c: canvas.Canvas, plans: list[SudokuPlan], page: int) -> int:
    c.setFont("SansB", 25); c.drawCentredString(W / 2, H / 2, "SUDOKU SOLUTIONS")
    _footer(c, page); c.showPage(); page += 1
    for start in range(0, len(plans), 2):
        for slot, item in enumerate(plans[start:start + 2]):
            top = 713 - slot * 350
            c.setFont("SansB", 12); c.setFillGray(.12)
            style = "NUMBERS" if item.style == "numbers" else "HOLIDAY SYMBOLS"
            c.drawCentredString(W / 2, top, f"PUZZLE {item.number}  |  {item.holiday.upper()}  |  {style}")
            sudoku.draw_sudoku(c, item.solution, 180, top - 17, 28, "MonoB", 13,
                               display_style=item.style, symbol_pack=item.symbol_pack)
        _footer(c, page); c.showPage(); page += 1
    return page


def render_interior(path: Path, holidays: list[dict], word_plans: list[WordPlan],
                    sudoku_plans: list[SudokuPlan], seed: int) -> tuple[int, str, str, list[dict]]:
    wordsearch.register_fonts(); sudoku.register_fonts()
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=(W, H), pageCompression=1)
    page = _front_pages(c, holidays)
    word_answers: list[tuple] = []
    qa: list[dict] = []
    records = []
    from publishing.puzzle_integrity import write_manifest, wordsearch_difficulty
    from publishing.sudoku_difficulty import rate_sudoku
    first_word_grid = ""
    first_sudoku = "".join(str(v) if v else "." for row in sudoku_plans[0].puzzle for v in row)
    for chapter, holiday in enumerate(holidays, 1):
        name = holiday["name"]
        _chapter_page(c, holiday, chapter, page); page += 1
        for item in (plan for plan in word_plans if plan.holiday == name):
            state = random.getstate()
            try:
                random.seed(seed + item.number * 9973)
                grid, placements, placed = wordsearch.generate_puzzle(list(item.words), 15)
            finally:
                random.setstate(state)
            if len(placed) != 12 or len(placements) != 12:
                raise ValueError(f"Puzzle {item.number} placed only {len(placed)} of 12 words.")
            if not first_word_grid:
                first_word_grid = "".join("".join(row) for row in grid)
            section = {"chapter": chapter, "title": name, "accent": wordsearch.INTERIOR_ACCENTS[(chapter - 1) % 6]}
            records.append(dict(number=item.number,type='word_search',grid=grid,placements=placements,words=placed,
                intended_words=list(item.words),solution_grid=grid,solution_placements=placements,
                puzzle_page=c.getPageNumber(),difficulty=wordsearch_difficulty(grid,placements,placed)))
            wordsearch.puzzle_page(c, item.number, f"{name}: {item.mini_theme}", grid,
                                   list(item.words), page, TITLE, section)
            word_answers.append((item.number, f"{name}: {item.mini_theme}", grid, placements))
            qa.append({"number": item.number, "holiday": name, "type": "word_search",
                       "mini_theme": item.mini_theme, "words": list(item.words), "placed": len(placed)})
            page += 1
        for item in (plan for plan in sudoku_plans if plan.holiday == name):
            if sudoku.count_solutions([row[:] for row in item.puzzle], limit=2) != 1:
                raise ValueError(f"Sudoku {item.number} is not uniquely solvable.")
            records.append(dict(number=item.number,type='sudoku',grid=item.puzzle,solution_grid=item.solution,
                puzzle_page=c.getPageNumber(),difficulty=rate_sudoku(item.puzzle),display_style=item.style))
            _sudoku_page(c, item, chapter, page); page += 1
            qa.append({"number": item.number, "holiday": name, "type": "sudoku",
                       "style": item.style, "symbol_pack": item.symbol_pack,
                       "difficulty": item.difficulty, "unique_solution": True})
    first_word_solution=c.getPageNumber()+1
    page = wordsearch.solutions_pages(c, word_answers, page, TITLE)
    first_sudoku_solution=c.getPageNumber()+1
    page = _sudoku_solutions(c, sudoku_plans, page)
    for i,item in enumerate(word_plans):
        next(r for r in records if r['number']==item.number)['solution_page']=first_word_solution+i//2
    for i,item in enumerate(sudoku_plans):
        next(r for r in records if r['number']==item.number)['solution_page']=first_sudoku_solution+i//2
    if (page - 1) % 2:
        c.setFont("Sans", 9); c.drawCentredString(W / 2, H / 2, "End of book")
        _footer(c, page); c.showPage(); page += 1
    c.save()
    write_manifest(path,sorted(records,key=lambda r:r['number']),getattr(c,'_puzzle_text_regions',[]))
    actual = len(PdfReader(str(path)).pages)
    if actual != page - 1:
        raise ValueError(f"Page count mismatch: rendered {actual}, expected {page - 1}.")
    return actual, first_word_grid, first_sudoku, qa


def _call(script: str, args: list[str]) -> None:
    subprocess.run([sys.executable, str(ROOT / script), *args], cwd=ROOT, check=True)


def _render_covers(front: Path, wrap: Path, wrap_preview: Path, *, art: Path,
                   pages: int, word_grid: str, sudoku_grid: str) -> None:
    require_production_approved_cover_asset(art)
    _call("cover.py", ["--title", TITLE, "--subtitle", SUBTITLE, "--author", AUTHOR,
          "--format-label", "WORD SEARCH + SUDOKU", "--puzzle-type", TYPE,
          "--puzzle-count", "200", "--badge", "10 HOLIDAY CHAPTERS",
          "--sample-wordsearch", word_grid, "--sample-sudoku", sudoku_grid,
          "--palette", "celebration", "--style", "holiday-editorial",
          "--art", str(art), "--out", str(front)])
    _call("wrap_cover.py", ["--front", str(front), "--pages", str(pages),
          "--palette", "celebration", "--title", TITLE, "--author", AUTHOR,
          "--back-heading", "A WHOLE YEAR OF PUZZLES", "--puzzle-type", TYPE,
          "--puzzle-count", "200", "--theme", "year-round-holidays",
          "--sample-sudoku", sudoku_grid,
          "--back", "Explore ten holiday chapters, each filled with ten themed 12-word searches, five number Sudoku puzzles, and five holiday-symbol Sudoku puzzles. From New Year's Day to Christmas, every celebration has its own words and symbols. Find your favorites, try something new, and check complete solutions at the back.",
          "--out", str(wrap), "--preview-out", str(wrap_preview)])


def _listing_text(pages: int) -> str:
    from publishing.listing_copy import kdp_us_large_trim_estimate, recommended_prices
    pricing_meta = {"title": TITLE, "subtitle": SUBTITLE, "puzzle_type": TYPE,
                    "page_count": pages, "puzzle_count": 200, "trim_size": "8.5x11"}
    prices = recommended_prices(pricing_meta)
    royalty = kdp_us_large_trim_estimate(pricing_meta)
    return f"""KDP LISTING KIT — COPY-READY
Title: {TITLE}
Subtitle: {SUBTITLE}
Author: {AUTHOR}
Book type: {TYPE}
Trim size: 8.5 x 11 inches
Interior: black ink on white paper
Interior pages: {pages}
Puzzle count: 200 (100 word searches, 50 classic-number Sudoku, 50 holiday-symbol Sudoku)
Word search size: 12 words per puzzle; 1,200 entries across the book

DESCRIPTION — COPY
Ten celebrations. Two puzzle styles. One substantial collection made for a full year of festive fun.

Celebrate All Year brings together 200 puzzles across ten holiday chapters: New Year's Day, Valentine's Day, Easter, Mother's Day, Father's Day, Independence Day, Halloween, Thanksgiving, Hanukkah, and Christmas.

Every holiday chapter includes:
• 10 focused, 12-word searches inspired by foods, decorations, traditions, gatherings, and seasonal moments
• 5 classic number Sudoku puzzles
• 5 themed symbol Sudoku puzzles featuring nine illustrated icons chosen for that celebration
• Complete solutions for every puzzle

That adds up to 100 word searches, 50 number Sudoku puzzles, 50 symbol Sudoku puzzles, and 1,200 word-search entries. Words do not repeat within the same holiday chapter, so every celebration keeps moving into fresh territory.

The roomy 8.5 x 11-inch pages and clear puzzle layouts make this a satisfying screen-free activity for adults, teens, families, holiday travel, quiet evenings, and gift-giving. Choose a favorite celebration—or work through the whole year—and enjoy a collection that feels different from chapter to chapter.

KEYWORD IDEAS — ENTER IN AMAZON'S SEVEN KEYWORD FIELDS
1. festive brain games adults teens seniors
2. christmas thanksgiving halloween activities
3. new year valentine easter games
4. hanukkah independence day activities
5. symbol logic number games
6. family travel quiet time activities
7. relaxing screen free gifts for puzzlers

CATEGORY DIRECTIONS — VERIFY CURRENT KDP CHOICES
Primary marketplace: Amazon.com.
Choose the closest current paperback categories for Games & Activities / Word Search, Games & Activities / Sudoku, and Games & Activities / Puzzles. KDP category names vary by marketplace; use only the closest available accurate choices.

AUDIENCE AND SETUP
Primary audience: adults and teens. Do not enter a children's reading age.
Sexually explicit images or title: No.
Series: leave blank unless this title is formally added to an existing series.
AI-generated content disclosure: Yes — Text and Images. The interior word material and cover artwork include AI-generated content that was editorially reviewed and substantially developed for this book. This disclosure is entered during KDP setup and is not customer-facing listing copy.

PRICE
Suggested Amazon.com starting list price: ${prices['amazon']:.2f}.
Estimated US print cost: ${royalty['estimated_printing_cost']:.2f}; estimated royalty: ${royalty['estimated_royalty']:.2f} per sale at this price, before any other applicable costs.
These are app estimates for this {pages}-page, 8.5 x 11, black-ink paperback—not guaranteed payouts. Recheck the current KDP print-cost calculator and comparable live listings before setting the final price.

UPLOAD
Use 01_PRINT_UPLOADS/interior.pdf and 01_PRINT_UPLOADS/kdp_full_wrap.pdf.
Confirm all pages, margins, bleed, and spine in the current KDP Print Previewer before publishing.
"""


def refresh_listing(package: Path) -> dict:
    """Refresh customer copy and KDP setup guidance without rebuilding print files."""
    manifest_path = package_file(package, "PACKAGE_SOURCE_RECORD.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (manifest.get("title"), manifest.get("puzzle_type"), manifest.get("puzzle_count")) != (TITLE, TYPE, 200):
        raise ValueError("Listing refresh is limited to the reviewed 200-puzzle holiday package.")
    interior = package_file(package, "interior.pdf")
    pages = len(PdfReader(str(interior)).pages)
    if pages != int(manifest.get("interior_pages") or 0):
        raise ValueError("Interior page count no longer matches the saved package record.")
    listing_text = _listing_text(pages)
    package_file(package, "KDP_LISTING_KIT.txt", for_write=True).write_text(listing_text, encoding="utf-8")
    description = listing_text.split("DESCRIPTION — COPY\n", 1)[1].split("\nKEYWORD IDEAS", 1)[0].strip()
    keyword_block = listing_text.split("KEYWORD IDEAS — ENTER IN AMAZON'S SEVEN KEYWORD FIELDS\n", 1)[1].split("\nCATEGORY", 1)[0]
    manifest["description"] = description
    manifest["amazon_keywords"] = [line.split(". ", 1)[1] for line in keyword_block.splitlines() if ". " in line]
    manifest["category_directions"] = ["Games & Activities / Word Search",
                                       "Games & Activities / Sudoku",
                                       "Games & Activities / Puzzles"]
    manifest["primary_audience"] = "Adults and teens"
    manifest["kdp_ai_generated_disclosure"] = {"text": True, "images": True, "translations": False}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    from publishing.manager import PublishingService
    PublishingService(ROOT).sync_output_packages()
    return {"package": str(package), "pages": pages, "keywords": manifest["amazon_keywords"],
            "listing": str(package_file(package, "KDP_LISTING_KIT.txt"))}


def _write_rights_ledger(output: Path, art: Path, approved_art: dict) -> None:
    """Record existing asset approval without creating a new rights approval."""
    package_file(output, "COVER_ART_RIGHTS_LEDGER.txt", for_write=True).write_text(
        "COVER ART RIGHTS LEDGER\n"
        "Existing production-approved asset; approval is preserved, not newly granted.\n"
        + json.dumps({"art": str(art), "approval": approved_art}, ensure_ascii=False, indent=2, default=str)
        + "\nOwner review of marketplace rights and AI disclosure remains required.\n",
        encoding="utf-8")


def build(output: Path, *, source: Path = SOURCE, seed: int = 20260921,
          art: Path = APPROVED_ART, sync_catalog: bool = True) -> dict:
    holidays = load_source(source)
    approved_art = require_production_approved_cover_asset(art)
    words, sudokus = build_plan(holidays, seed)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Refusing to overwrite an existing book package: {output}")
    initialize_package_layout(output)
    interior = package_file(output, "interior.pdf", for_write=True)
    pages, word_grid, sudoku_grid, qa = render_interior(interior, holidays, words, sudokus, seed)
    front = package_file(output, "front_cover.png", for_write=True)
    wrap = package_file(output, "kdp_full_wrap.pdf", for_write=True)
    wrap_preview = package_file(output, "kdp_full_wrap_preview.png", for_write=True)
    _render_covers(front, wrap, wrap_preview, art=art, pages=pages,
                   word_grid=word_grid, sudoku_grid=sudoku_grid)
    _write_rights_ledger(output, art, approved_art)
    listing_text = _listing_text(pages)
    listing = package_file(output, "KDP_LISTING_KIT.txt", for_write=True)
    listing.write_text(listing_text, encoding="utf-8")
    description = listing_text.split("DESCRIPTION — COPY\n", 1)[1].split("\nKEYWORD IDEAS", 1)[0].strip()
    keywords = listing_text.split("KEYWORD IDEAS — ENTER IN AMAZON'S SEVEN KEYWORD FIELDS\n", 1)[1].split("\nCATEGORY", 1)[0]
    manifest = {"title": TITLE, "subtitle": SUBTITLE, "author": AUTHOR, "puzzle_type": TYPE,
                "theme": "Year-round holidays", "puzzle_count": 200, "interior_pages": pages,
                "trim_size": "8.5x11", "difficulty": "Mixed", "description": description,
                "amazon_keywords": [line.split(". ", 1)[1] for line in keywords.splitlines() if ". " in line],
                "source_word_bank": str(source), "seed": seed,
                "holiday_chapters": [h["name"] for h in holidays],
                "word_search_words_per_puzzle": 12, "total_word_search_entries": 1200,
                "cover_art": str(art), "cover_style": "holiday-editorial",
                "category_directions": ["Games & Activities / Word Search",
                                        "Games & Activities / Sudoku",
                                        "Games & Activities / Puzzles"],
                "primary_audience": "Adults and teens",
                "kdp_ai_generated_disclosure": {"text": True, "images": True, "translations": False}}
    package_file(output, "PACKAGE_SOURCE_RECORD.json", for_write=True).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    package_file(output, "PUZZLE_QA.json", for_write=True).write_text(
        json.dumps({"puzzles": qa, "counts": {"word_search": 100, "number_sudoku": 50,
                    "symbol_sudoku": 50}}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ok, lines = preflight(output)
    package_file(output, "PUBLISHER_PREFLIGHT.txt", for_write=True).write_text(report_text(output), encoding="utf-8")
    package_file(output, "PRODUCTION_PROOF_GATE.txt", for_write=True).write_text(
        ("PASSED" if ok else "NEEDS ATTENTION") + " — 200 puzzle generation and PDF dimensions\n" +
        "\n".join(lines) + "\nHuman visual review and KDP Print Previewer are still required.\n", encoding="utf-8")
    if not ok or not release_contract(output)["ready"]:
        raise ValueError("Book package did not pass its final file and print checks.")
    if sync_catalog:
        from publishing.manager import PublishingService
        PublishingService(ROOT).sync_output_packages()
    return {"folder": str(output), "pages": pages, "word_search": 100,
            "number_sudoku": 50, "symbol_sudoku": 50, "preflight": lines}


def rebuild_book(package: Path, *, source: Path = SOURCE, seed: int = 20260921,
                 art: Path = APPROVED_ART) -> dict:
    """Rebuild this complete book in staging, then replace it with recovery copies."""
    manifest_path = package_file(package, "PACKAGE_SOURCE_RECORD.json")
    current = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (current.get("title"), current.get("puzzle_type"), current.get("puzzle_count")) != (TITLE, TYPE, 200):
        raise ValueError("Complete rebuild is limited to the reviewed 200-puzzle holiday package.")
    package.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="holiday_book_rebuild_", dir=package.parent) as stage_name:
        stage = Path(stage_name) / package.name
        result = build(stage, source=source, seed=seed, art=art, sync_catalog=False)
        if not release_contract(stage)["ready"]:
            raise ValueError("The staged replacement did not pass its release contract.")
        revision = package / "04_REVIEW_AND_RECORDS" / "book_revisions" / datetime.now().strftime("previous_%Y%m%d_%H%M%S")
        revision.mkdir(parents=True)
        for logical in ("interior.pdf", "kdp_full_wrap.pdf", "KDP_LISTING_KIT.txt",
                        "front_cover.png", "kdp_full_wrap_preview.png",
                        "PACKAGE_SOURCE_RECORD.json", "PUZZLE_QA.json",
                        "PUBLISHER_PREFLIGHT.txt", "PRODUCTION_PROOF_GATE.txt"):
            old = package_file(package, logical)
            if old.is_file():
                shutil.copy2(old, revision / old.name)
        for source_file in stage.rglob("*"):
            if not source_file.is_file():
                continue
            relative = source_file.relative_to(stage)
            destination = package / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, destination)
    from publishing.manager import PublishingService
    PublishingService(ROOT).sync_output_packages()
    result["folder"] = str(package)
    result["previous_book"] = str(revision)
    return result


def rebuild_cover(package: Path, *, art: Path = APPROVED_ART) -> dict:
    """Rebuild only this book's cover from its saved seed, with recovery copies."""
    manifest_path = package_file(package, "PACKAGE_SOURCE_RECORD.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (manifest.get("title"), manifest.get("puzzle_type"), manifest.get("puzzle_count")) != (TITLE, TYPE, 200):
        raise ValueError("Cover-only rebuild is limited to the reviewed 200-puzzle holiday package.")
    approved_art = require_production_approved_cover_asset(art)
    interior = package_file(package, "interior.pdf")
    pages = len(PdfReader(str(interior)).pages)
    if pages != int(manifest.get("interior_pages") or 0):
        raise ValueError("Interior changed since this cover was prepared; rebuild the complete book.")
    source = Path(str(manifest["source_word_bank"]))
    words, sudokus = build_plan(load_source(source), int(manifest["seed"]))
    state = random.getstate()
    try:
        random.seed(int(manifest["seed"]) + words[0].number * 9973)
        grid, _locations, placed = wordsearch.generate_puzzle(list(words[0].words), 15)
    finally:
        random.setstate(state)
    if len(placed) != 12:
        raise ValueError("The actual first word-search sample could not be reproduced.")
    word_grid = "".join("".join(row) for row in grid)
    sudoku_grid = "".join(str(v) if v else "." for row in sudokus[0].puzzle for v in row)
    front = package_file(package, "front_cover.png")
    wrap = package_file(package, "kdp_full_wrap.pdf")
    preview = package_file(package, "kdp_full_wrap_preview.png")
    proof = front.with_name(front.stem + ".approval.json")
    thumbnail = front.with_name(front.stem + "_thumbnail.png")
    revisions = package / "04_REVIEW_AND_RECORDS" / "cover_revisions"
    revisions.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="holiday_cover_", dir=revisions) as stage_name:
        stage = Path(stage_name)
        new_front, new_wrap, new_preview = (stage / "front_cover.png",
                                            stage / "kdp_full_wrap.pdf", stage / "kdp_full_wrap_preview.png")
        _render_covers(new_front, new_wrap, new_preview, art=art, pages=pages,
                       word_grid=word_grid, sudoku_grid=sudoku_grid)
        approved, reason, _proof = verify_rendered_cover_approval(new_front)
        if not approved:
            raise ValueError("The newly rendered cover lacks a current art approval: " + reason)
        box = PdfReader(str(new_wrap)).pages[0].mediabox
        expected_width = (17.25 + pages * .002252) * 72
        if abs(float(box.width) - expected_width) > 4 or abs(float(box.height) - 11.25 * 72) > 4:
            raise ValueError("New wrap dimensions do not match the saved 316-page interior.")
        old_files = (front, thumbnail, proof, wrap, preview)
        revision = revisions / datetime.now().strftime("previous_%Y%m%d_%H%M%S")
        revision.mkdir()
        for old in old_files:
            if old.is_file():
                shutil.copy2(old, revision / old.name)
        replacements = ((new_front, front), (new_front.with_name("front_cover_thumbnail.png"), thumbnail),
                        (new_front.with_name("front_cover.approval.json"), proof),
                        (new_wrap, wrap), (new_preview, preview))
        for candidate, destination in replacements:
            candidate.replace(destination)
    manifest["cover_art"] = str(art)
    manifest["cover_asset_id"] = approved_art["asset_id"]
    manifest["cover_style"] = "holiday-editorial"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    okay, checks = preflight(package)
    if not okay or not release_contract(package)["ready"]:
        raise ValueError("Rebuilt cover did not pass the existing package and print checks. Previous files are in " + str(revision))
    package_file(package, "PUBLISHER_PREFLIGHT.txt", for_write=True).write_text(report_text(package), encoding="utf-8")
    from publishing.manager import PublishingService
    PublishingService(ROOT).sync_output_packages()
    return {"package": str(package), "pages": pages, "approved_art": approved_art["asset_id"],
            "previous_cover": str(revision), "preflight": checks}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "out" / "celebrate_all_year_200_holiday_puzzles")
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--seed", type=int, default=20260921)
    parser.add_argument("--art", type=Path, default=APPROVED_ART)
    parser.add_argument("--no-sync", action="store_true")
    parser.add_argument("--rebuild-cover", action="store_true", help="Rebuild only the existing book's approved cover and wrap.")
    parser.add_argument("--rebuild-book", action="store_true", help="Safely rebuild the complete existing holiday package.")
    parser.add_argument("--refresh-listing", action="store_true", help="Refresh listing copy and setup guidance without changing PDFs.")
    args = parser.parse_args()
    if sum((args.rebuild_cover, args.rebuild_book, args.refresh_listing)) > 1:
        parser.error("Choose only one rebuild or refresh action.")
    result = (refresh_listing(args.output) if args.refresh_listing else
              rebuild_book(args.output, source=args.source, seed=args.seed, art=args.art) if args.rebuild_book else
              rebuild_cover(args.output, art=args.art) if args.rebuild_cover else
              build(args.output, source=args.source, seed=args.seed,
                    art=args.art, sync_catalog=not args.no_sync))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
