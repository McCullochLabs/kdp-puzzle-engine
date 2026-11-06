#!/usr/bin/env python3
"""Print-ready large-print word-search book for Amazon KDP. Swap the themes
JSON and it's a new book in a new niche -- that's the whole premise: code
generates books at a volume a hand-maker can't match, not a one-off script
for a single title.

Outputs an 8.5x11 interior PDF with front matter, puzzles, and full
solutions. KDP needs a separate cover, either from their free Cover Creator
or generated separately here."""
from __future__ import annotations
import argparse, json, math, os, random, string
from reportlab.pdfgen import canvas
from reportlab.pdfgen.canvas import Canvas
from educational_value import is_educational_context
from reportlab.lib.pagesizes import letter

PAGE_W, PAGE_H = letter            # 612 x 792 pt  (8.5 x 11 in)
MARGIN = 54                        # 0.75in uniform — safe KDP gutter (<150pg) + roomy large print
GRID_N = 15  # The familiar default used for standard 12-word puzzles.
MAX_GRID_N = 21
DIRS = [(0, 1), (1, 0), (1, 1), (1, -1), (0, -1), (-1, 0), (-1, -1), (-1, 1)]

Cell = tuple[int, int]
Grid = list[list[str]]

from font_utils import pdf_font_candidates, register_pdf_font
from publishing.title_pages import render_title_page, spec_from_mapping

PDF_FONT_FAMILIES = {
    "Sans":  "sans",
    "SansB": "sans-bold",
    "MonoB": "mono-bold",
}

# Interior accents are deliberately quiet: they give each small run of puzzles
# its own visual identity without competing with the grid or reducing print
# readability.  The color order is deterministic, so a regenerated book keeps
# the same chapter treatment.
INTERIOR_ACCENTS = (
    (0.14, 0.42, 0.55),  # ocean blue
    (0.29, 0.48, 0.31),  # garden green
    (0.56, 0.30, 0.42),  # berry
    (0.59, 0.39, 0.12),  # warm amber
    (0.30, 0.34, 0.58),  # indigo
    (0.42, 0.32, 0.24),  # earth
)

def register_fonts() -> None:
    unresolved = [
        alias for alias, family in PDF_FONT_FAMILIES.items()
        if not register_pdf_font(alias, pdf_font_candidates(family))
    ]
    if unresolved:
        raise RuntimeError(
            f"Required font(s) could not be found for: {', '.join(unresolved)}. "
            "Install or restore the standard Arial and Courier New fonts, then try again."
        )


# ---------------- puzzle generation ----------------
def _try_place(grid: Grid, word: str, N: int, *, directions=None, rng=None) -> list[Cell] | None:
    rng = rng if rng is not None else random
    dr, dc = rng.choice(DIRS if directions is None else directions)
    r, c = rng.randint(0, N - 1), rng.randint(0, N - 1)
    cells: list[Cell] = []
    for k, ch in enumerate(word):
        rr, cc = r + dr * k, c + dc * k
        if not (0 <= rr < N and 0 <= cc < N):
            return None
        cur = grid[rr][cc]
        if cur and cur != ch:
            return None
        cells.append((rr, cc))
    for (rr, cc), ch in zip(cells, word):
        grid[rr][cc] = ch
    return cells


def validate_word_set(words: list[str], N: int = GRID_N) -> None:
    """Shared pre-placement contract for planners and the grid generator."""
    if not words or len(words) != len(set(words)) or any(not w or not w.isascii() or not w.isalpha() or w != w.upper() or len(w) > N for w in words):
        raise ValueError('Every target must be unique uppercase A-Z text that fits the grid; revise the word list.')
    # Embedded targets can make a unique physical answer impossible.
    for short in words:
        hosts = [long for long in words if long != short and (short in long or short in long[::-1])]
        if len(hosts) > 1 or any(long.count(short) > 1 for long in hosts):
            raise ValueError(f'Target {short} is embedded in multiple answers; replace it.')


def generate_puzzle(words: list[str], N: int = GRID_N, *, directions=None, rng=None, content_policy="general") -> tuple[Grid, list[list[Cell]], list[str]]:
    """Place every word when possible, retrying a whole grid before accepting less.

    A greedy placement can occasionally paint itself into a corner even for a
    small 12-word puzzle.  Retrying the empty grid makes package-time results
    stable and prevents a different seed from passing a check then losing a
    word in the finished PDF.
    """
    rng = rng if rng is not None else random
    if directions is not None and (not directions or any(tuple(d) not in DIRS for d in directions)):
        raise ValueError("Directions must be a nonempty subset of the eight unit directions.")
    from publishing.puzzle_integrity import verify_wordsearch, occurrences
    if content_policy not in ("general", "adult_intended_profanity"):
        raise ValueError("Unsupported word-search content policy.")
    validate_word_set(words, N)
    ordered = sorted(words, key=len, reverse=True)
    best: tuple[Grid, list[list[Cell]], list[str]] | None = None
    last_errors = []
    for _attempt in range(200):
        grid: Grid = [["" for _ in range(N)] for _ in range(N)]
        placements: list[list[Cell]] = []
        placed: list[str] = []
        for word in ordered:
            existing = occurrences(grid, word)
            cells = next((path for path in existing if len(path)<2 or
                          (path[1][0]-path[0][0],path[1][1]-path[0][1]) in (directions or DIRS)),None)
            for _ in range(0 if cells else 500):
                cells = _try_place(grid, word, N, directions=directions, rng=rng)
                if cells:
                    break
            if cells:
                placements.append(cells); placed.append(word)
        if best is None or len(placed) > len(best[2]):
            best = (grid, placements, placed)
        if len(placed) != len(ordered):
            continue
        for row in grid:
            for col in range(N):
                if not row[col]:
                    row[col] = rng.choice(string.ascii_uppercase)
        last_errors = verify_wordsearch(grid, placements, placed, words, directions, content_policy=content_policy)
        if not last_errors:
            return grid, placements, placed
    assert best is not None
    missing = sorted(set(words) - set(best[2]))
    detail = '; '.join(last_errors[:5]) if last_errors else f'Missing targets: {missing}'
    raise ValueError(f'No complete, unambiguous grid after 200 attempts. {detail}. Revise the word list or grid size.')


def grid_size_for(words: list[str]) -> int:
    """Choose a readable grid size from the puzzle's word count."""
    word_count = len(words)
    if word_count <= 12:
        preferred = 15
    elif word_count <= 16:
        preferred = 17
    elif word_count <= 20:
        preferred = 19
    else:
        preferred = 21

    longest_word = max((len(word) for word in words), default=GRID_N)
    return min(MAX_GRID_N, max(preferred, longest_word))


# ---------------- drawing helpers ----------------
def draw_grid(c: Canvas, grid: Grid, gx: float, gy_top: float, cell: float,
              font_size: float, highlights: list[list[Cell]] | None = None, *, grayscale: bool = False) -> None:
    N = len(grid)
    regions = getattr(c, '_puzzle_text_regions', [])
    regions.append(dict(page=c.getPageNumber(), role='solution' if highlights else 'puzzle',
                        bounds=[gx,gy_top-N*cell,gx+N*cell,gy_top], font_pt=font_size))
    c._puzzle_text_regions = regions
    h = N * cell
    # faint internal gridlines
    c.setLineWidth(0.75)
    c.setStrokeColorRGB(0.86, 0.86, 0.86)
    for i in range(N + 1):
        c.line(gx + i * cell, gy_top, gx + i * cell, gy_top - h)
        c.line(gx, gy_top - i * cell, gx + N * cell, gy_top - i * cell)
    # solution highlighters (drawn UNDER the letters)
    if highlights:
        c.setLineCap(1)
        if grayscale:
            c.setStrokeGray(0.65)
        else:
            c.setStrokeColorRGB(1.0, 0.78, 0.20)
        c.setStrokeAlpha(0.5)
        c.setLineWidth(cell * 0.72)
        for cells in highlights:
            (r0, c0), (r1, c1) = cells[0], cells[-1]
            x0, y0 = gx + c0 * cell + cell / 2, gy_top - r0 * cell - cell / 2
            x1, y1 = gx + c1 * cell + cell / 2, gy_top - r1 * cell - cell / 2
            c.line(x0, y0, x1, y1)
        c.setStrokeAlpha(1.0)
        c.setLineCap(0)
    # outer border
    c.setStrokeColorRGB(0.25, 0.25, 0.25)
    c.setLineWidth(1.3)
    c.rect(gx, gy_top - h, N * cell, h)
    # letters
    c.setFillColorRGB(0, 0, 0)
    c.setFont("MonoB", font_size)
    for r in range(N):
        for col in range(N):
            cx = gx + col * cell + cell / 2
            cy = gy_top - r * cell - cell / 2 - font_size * 0.34
            c.drawCentredString(cx, cy, grid[r][col])


def draw_word_list(c: Canvas, words: list[str], gx: float, top_y: float,
                    grid_w: float, cols: int = 3, heading_font: int = 12,
                    word_font: int = 13, row_step: int = 20) -> None:
    c.setFillColorRGB(0, 0, 0)
    c.setFont("SansB", heading_font)
    c.drawCentredString(PAGE_W / 2, top_y, "FIND THESE WORDS")
    # Preserve the seeded, editorially mixed order supplied by the book plan.
    # Alphabetizing here made every finished puzzle read like a dictionary.
    words = list(words)
    # Fit the actual printed words before drawing, preserving font size/order.
    widest = max((c.stringWidth(w, 'Sans', word_font) for w in words), default=0)
    while cols > 1 and widest > grid_w / cols - 16:
        cols -= 1
    rows = math.ceil(len(words) / cols)
    regions = getattr(c, '_puzzle_text_regions', [])
    regions.append(dict(page=c.getPageNumber(),role='word_list',bounds=[gx,top_y-heading_font-10-rows*row_step,gx+grid_w,top_y],font_pt=word_font))
    c._puzzle_text_regions = regions
    col_w = grid_w / cols
    c.setFont("Sans", word_font)
    start_y = top_y - heading_font - 10
    for i, w in enumerate(words):
        col, row = i // rows, i % rows
        x = gx + col * col_w + 8
        y = start_y - row * row_step
        if c.stringWidth(w,'Sans',word_font)>col_w-16 or y<54:
            raise ValueError(f'Word-list layout would clip {w}; use fewer or shorter targets.')
        c.drawString(x, y, w)


def footer(c: Canvas, page_no: int) -> None:
    c.setFillColorRGB(0.45, 0.45, 0.45)
    c.setFont("Sans", 9)
    c.drawCentredString(PAGE_W / 2, 34, str(page_no))


# ---------------- pages ----------------
def front_matter(c: Canvas, title: str, subtitle: str, author: str, data: dict | None = None) -> None:
    data = data or {}
    metadata = dict(data)
    metadata.update({"title": title, "subtitle": subtitle, "author": author, "puzzle_type": "Word Search"})
    render_title_page(c, spec_from_mapping(metadata, puzzle_type="Word Search"), page_size=(PAGE_W, PAGE_H), margin=MARGIN, regular_font="Sans", bold_font="SansB")

    # copyright page
    c.setFillColorRGB(0.2, 0.2, 0.2)
    c.setFont("Sans", 10)
    lines = [
        f"Copyright © 2026 {author}.",
        "All rights reserved.",
        "",
        "No part of this publication may be reproduced, distributed, or",
        "transmitted in any form without the prior written permission of",
        "the publisher, except for brief quotations in reviews.",
        "",
        "The puzzles in this book are an original compilation.",
        "Printed editions produced via Amazon KDP.",
    ]
    for i, ln in enumerate(lines):
        c.drawString(MARGIN, PAGE_H - 120 - i * 16, ln)
    c.showPage()

    # how to play
    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.setFont("SansB", 22)
    c.drawCentredString(PAGE_W / 2, PAGE_H - 140, "HOW TO PLAY")
    c.setFont("Sans", 13)
    from publishing.studio_reader_profiles import reader_profile
    instruction = reader_profile(data.get('reader_profile', 'standard'))['instructions']
    how = [
        "Each puzzle hides a list of words in a grid of letters.",
        "",
        *(["Words run left to right or top to bottom.", "No diagonal or backwards words."] if data.get("reader_profile") == "ages_6_8" else ["Words run forwards across, down or diagonally down.", "No backwards words."] if data.get("reader_profile") == "ages_9_12" else ["Words run in straight lines - across, down, diagonally,", "and sometimes backwards."]),
        "",
        "Find every word in the list and circle it in the grid.",
        "",
        "Stuck? Full solutions are at the back of the book.",
        "",
        "Take your time. There is no clock. Enjoy the quiet.",
    ]
    for i, ln in enumerate(how):
        c.drawCentredString(PAGE_W / 2, PAGE_H - 200 - i * 22, ln)
    c.showPage()


def _interior_section_config(data: dict) -> dict:
    """Return safe, optional section settings without changing old themes.

    A saved theme may supply ``interior_sections`` with a group size, optional
    divider pages, and optional named ranges.  Themes without that data still
    receive a restrained five-puzzle chapter treatment, so the improvement is
    useful immediately and does not require a library migration.
    """
    raw = data.get("interior_sections")
    config = dict(raw) if isinstance(raw, dict) else {}
    try:
        group_size = int(config.get("group_size") or 5)
    except (TypeError, ValueError):
        group_size = 5
    config["group_size"] = min(10, max(3, group_size))
    config["divider_pages"] = bool(config.get("divider_pages", False))
    return config


def _section_title_for(data: dict, puzzles: list[dict], start: int, end: int,
                       chapter_number: int, config: dict) -> str:
    """Prefer a reviewed mini-theme; otherwise name an honest topic chapter."""
    named = config.get("sections")
    if isinstance(named, list):
        for item in named:
            if not isinstance(item, dict):
                continue
            entries = item.get("puzzles")
            if isinstance(entries, list) and any(int(value) == start + 1 for value in entries if str(value).isdigit()):
                label = str(item.get("title") or item.get("mini_theme") or "").strip()
                if label:
                    return label
            try:
                first = int(item.get("start") or 0)
                last = int(item.get("end") or first)
            except (TypeError, ValueError):
                first = last = 0
            if first and first <= start + 1 <= last:
                label = str(item.get("title") or item.get("mini_theme") or "").strip()
                if label:
                    return label

    themes = [str(item.get("mini_theme") or item.get("section") or item.get("category") or "").strip()
              for item in puzzles[start:end] if isinstance(item, dict)]
    themes = [item for item in themes if item]
    if themes:
        # A plan can rotate mini-themes within a page.  The most common one is
        # the honest, stable label for the visual chapter.
        return max(sorted(set(themes)), key=lambda item: themes.count(item))
    topic = str(data.get("detected_topic") or data.get("theme") or data.get("series") or "WORD SEARCH").strip()
    return f"{topic} - CHAPTER {chapter_number}"


def interior_section_plan(data: dict, puzzles: list[dict]) -> list[dict]:
    """Build one visual chapter descriptor per puzzle without moving content."""
    config = _interior_section_config(data)
    group_size = config["group_size"]
    plan: list[dict] = []
    for start in range(0, len(puzzles), group_size):
        end = min(len(puzzles), start + group_size)
        chapter = start // group_size + 1
        plan.extend({
            "chapter": chapter,
            "title": _section_title_for(data, puzzles, start, end, chapter, config),
            "accent": INTERIOR_ACCENTS[(chapter - 1) % len(INTERIOR_ACCENTS)],
            "starts_section": offset == start,
            "divider_pages": config["divider_pages"],
        } for offset in range(start, end))
    return plan


def interior_divider_page_count(data: dict, puzzles: list[dict]) -> int:
    """Expose optional divider count for package page-count estimates."""
    return sum(1 for item in interior_section_plan(data, puzzles)
               if item["starts_section"] and item["divider_pages"])


def section_divider_page(c: Canvas, section: dict, page_no: int, running_title: str) -> None:
    """An optional, reader-friendly transition page between named sections."""
    red, green, blue = section["accent"]
    c.setFillColorRGB(red, green, blue)
    c.roundRect(MARGIN, PAGE_H - 306, PAGE_W - 2 * MARGIN, 160, 14, stroke=0, fill=1)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("SansB", 12)
    c.drawCentredString(PAGE_W / 2, PAGE_H - 195, f"CHAPTER {section['chapter']}")
    title = str(section["title"]).upper()
    size = 27
    while size > 14:
        c.setFont("SansB", size)
        if c.stringWidth(title, "SansB", size) <= PAGE_W - 2 * MARGIN - 44:
            break
        size -= 1
    c.setFont("SansB", size)
    c.drawCentredString(PAGE_W / 2, PAGE_H - 245, title)
    c.setFillColorRGB(0.22, 0.22, 0.22)
    c.setFont("Sans", 13)
    c.drawCentredString(PAGE_W / 2, PAGE_H - 365, "A fresh set of puzzles begins here.")
    c.setFillColorRGB(0.45, 0.45, 0.45)
    c.setFont("Sans", 9)
    c.drawCentredString(PAGE_W / 2, 58, running_title)
    footer(c, page_no)
    c.showPage()


def puzzle_page(c: Canvas, idx: int, name: str, grid: Grid, words: list[str],
                 page_no: int, running_title: str, section: dict | None = None,
                 educational: bool = False, vocabulary_note: str = "", reader_key: str = 'standard') -> None:
    c.setFillColorRGB(0.5, 0.5, 0.5)
    c.setFont("Sans", 10)
    c.drawCentredString(PAGE_W / 2, PAGE_H - 40, running_title)
    section = section or {"chapter": 1, "title": "", "accent": INTERIOR_ACCENTS[0]}
    accent = section.get("accent", INTERIOR_ACCENTS[0])
    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.setFont("SansB", 12)
    c.drawString(MARGIN, PAGE_H - 64, f"PUZZLE {idx}")
    c.setFillColorRGB(*accent)
    c.setFont("SansB", 9)
    from publishing.puzzle_integrity import wordsearch_difficulty
    # Layout receives the finished grid; recover physical paths for a measured label.
    from publishing.puzzle_integrity import occurrences
    paths = [occurrences(grid,w)[0] for w in words]
    measured = wordsearch_difficulty(grid,paths,words)
    chapter_label = f"CHAPTER {section.get('chapter', 1)} | {measured['label'].upper()}"
    c.drawRightString(PAGE_W - MARGIN, PAGE_H - 64, chapter_label)
    # Long themed puzzle names must never enter the trim or gutter area.  A
    # centered heading can otherwise look fine on screen while extending past
    # the physical page edge (which KDP correctly rejects).  Scale the title
    # down only as much as needed to stay inside the generous print-safe area.
    heading = name.upper()
    heading_font = 22
    max_heading_width = PAGE_W - (MARGIN * 2)
    while heading_font > 12:
        c.setFont("SansB", heading_font)
        if c.stringWidth(heading, "SansB", heading_font) <= max_heading_width:
            break
        heading_font -= 1
    c.setFont("SansB", heading_font)
    c.drawCentredString(PAGE_W / 2, PAGE_H - 96, heading)
    c.setStrokeColorRGB(*accent)
    c.setLineWidth(2.4)
    c.line(PAGE_W / 2 - 44, PAGE_H - 108, PAGE_W / 2 + 44, PAGE_H - 108)

    N = len(grid)
    if N <= 15:
        cell, letter_font = 30, 18
        list_settings = {"heading_font": 12, "word_font": 13, "row_step": 20}
    elif N <= 17:
        cell, letter_font = 27, 16
        list_settings = {"heading_font": 11, "word_font": 12, "row_step": 17}
    elif N <= 19:
        cell, letter_font = 24, 14
        list_settings = {"heading_font": 11, "word_font": 11, "row_step": 16}
    else:
        cell, letter_font = 22, 13
        list_settings = {"heading_font": 10, "word_font": 10, "row_step": 14}
    grid_w = N * cell
    from publishing.studio_reader_profiles import reader_profile
    profile = reader_profile(reader_key)
    letter_font = max(letter_font,profile.get('minimum_grid_font_pt',14))
    list_settings['word_font'] = max(list_settings['word_font'],profile.get('minimum_word_font_pt',12))
    gy_top = PAGE_H - 122
    list_width = PAGE_W - 2 * MARGIN
    widest = max((c.stringWidth(w, 'Sans', list_settings['word_font']) for w in words), default=0)
    list_cols = 3
    while list_cols > 1 and widest > list_width / list_cols - 16:
        list_cols -= 1
    list_rows = math.ceil(len(words) / list_cols)
    list_height = list_settings['heading_font'] + 10 + list_rows * list_settings['row_step']
    available_grid_height = gy_top - 26 - 54 - list_height
    cell = min(cell, available_grid_height / N)
    if cell < max(18, letter_font + 4):
        raise ValueError('The grid and all targets do not fit at readable type sizes; review this puzzle layout.')
    grid_w = N * cell
    gx = (PAGE_W - grid_w) / 2
    draw_grid(c, grid, gx, gy_top, cell, letter_font)

    draw_word_list(c, words, MARGIN, gy_top - N * cell - 26, list_width, cols=list_cols,
                   **list_settings)
    if educational and words:
        spotlight = words[(idx - 1) % len(words)].title()
        prompt = vocabulary_note.strip() or f"Use {spotlight} in a sentence after you solve this puzzle."
        c.setFillColorRGB(*accent); c.setFont("SansB", 8.5)
        c.drawString(MARGIN, 54, f"WORD SPOTLIGHT: {spotlight.upper()}")
        c.setFillColorRGB(.34, .34, .34); c.setFont("Sans", 8.5)
        available = PAGE_W - MARGIN - 176
        while c.stringWidth(prompt, "Sans", 8.5) > available and len(prompt) > 24:
            prompt = prompt[:-4].rstrip() + "..."
        c.drawRightString(PAGE_W - MARGIN, 54, prompt)
    footer(c, page_no)
    c.showPage()


def themed_welcome_page(c: Canvas, data: dict, title: str) -> None:
    """A short, automatically tailored welcome that makes every book feel intentional."""
    topic = str(data.get("detected_topic") or title).strip()
    audience = str(data.get("audience") or "Adults & Teens").strip()
    difficulty = str(data.get("difficulty_label") or "Relaxing").strip()
    c.setFillColorRGB(0.10, 0.10, 0.10)
    c.setFont("SansB", 24)
    c.drawCentredString(PAGE_W / 2, PAGE_H - 150, "WELCOME TO THE COLLECTION")
    c.setStrokeColorRGB(0.65, 0.65, 0.65); c.setLineWidth(1)
    c.line(PAGE_W / 2 - 92, PAGE_H - 174, PAGE_W / 2 + 92, PAGE_H - 174)
    c.setFont("Sans", 14)
    custom_welcome = str(data.get("welcome_message") or "").strip()
    features = [str(item).strip() for item in data.get("collection_features", []) if str(item).strip()] if isinstance(data.get("collection_features"), list) else []
    lines = ([custom_welcome, *features] if custom_welcome else [
        f"This {difficulty.lower()} word-search collection celebrates {topic}.",
        f"Made for {audience.lower()}, it is a screen-free way to slow down,",
        "focus on a favorite subject, and enjoy one satisfying challenge at a time.",
    ]) + ["", "Circle words, take breaks, and return to any puzzle whenever you like.", "Your solutions are waiting at the back of the book."]
    y = PAGE_H - 245
    for line in lines:
        # The automatic welcome can include a full book title.  Wrap it before
        # centering so an otherwise polished page cannot cross the trim edge.
        for wrapped in _wrap(line, 72) if line else [""]:
            c.drawCentredString(PAGE_W / 2, y, wrapped)
            y -= 28
    c.setFont("SansB", 13)
    c.drawCentredString(PAGE_W / 2, 140, "ENJOY THE SEARCH.")
    c.showPage()


def tracker_puzzle_name(puzzles: list[dict], index: int, max_chars: int = 28) -> str:
    """Return the real mini-theme used by the puzzle tracker."""
    name = str(puzzles[index - 1].get("name", f"Puzzle {index}"))
    return name if len(name) <= max_chars else name[:max_chars - 3].rstrip() + "..."


def detail_pages(c: Canvas, data: dict, puzzles: list[dict], running_title: str) -> int:
    """Add two useful, truth-safe collection pages to every new book.

    These pages make a finished book feel more intentional without inventing
    topic facts.  A theme may opt out with ``detail_pages.enabled: false``.
    """
    config = data.get("detail_pages", {})
    if isinstance(config, dict) and config.get("enabled") is False:
        return 0
    topic = str(data.get("detected_topic") or data.get("series") or running_title).strip()
    audience = str(data.get("audience") or "Adults & Teens").strip()
    difficulty = str(data.get("difficulty_label") or "Relaxing").strip()
    count = len(puzzles)
    educational = is_educational_context(topic, data.get("series"), data.get("title"), data.get("subtitle"))

    # Collection guide
    c.setFillColorRGB(0.10, 0.10, 0.10)
    c.setFont("SansB", 25)
    c.drawCentredString(PAGE_W / 2, PAGE_H - 130, "YOUR COLLECTION GUIDE")
    c.setStrokeColorRGB(0.65, 0.65, 0.65); c.setLineWidth(1)
    c.line(PAGE_W / 2 - 100, PAGE_H - 152, PAGE_W / 2 + 100, PAGE_H - 152)
    c.setFont("Sans", 14)
    guide_lines = [
        f"This book includes {count} {topic} word-search puzzles.",
        f"Difficulty: {difficulty}. Made for {audience.lower()}.",
        "",
        "A relaxed way to enjoy the collection:",
        "- Pick any puzzle that catches your eye - there is no required order.",
        "- Use the puzzle name as a small topic prompt before you begin.",
        "- Mark your favorites in the notes page that follows.",
        "- Find complete solutions at the back whenever you need them.",
    ]
    y = PAGE_H - 215
    for line in guide_lines:
        c.drawCentredString(PAGE_W / 2, y, line)
        y -= 29
    c.setFont("SansB", 12)
    c.drawCentredString(PAGE_W / 2, 130, "ONE PUZZLE AT A TIME. ENJOY THE SEARCH.")
    c.showPage()

    # Reader notes / favorite tracker — useful for every topic and audience.
    c.setFillColorRGB(0.10, 0.10, 0.10)
    c.setFont("SansB", 25)
    c.drawCentredString(PAGE_W / 2, PAGE_H - 130, "MY VOCABULARY PROGRESS" if educational else "MY PUZZLE NOTES")
    c.setFont("Sans", 13)
    c.drawCentredString(PAGE_W / 2, PAGE_H - 160, "Keep track of the puzzles and words you enjoyed most.")
    c.setStrokeColorRGB(0.45, 0.45, 0.45); c.setLineWidth(1)
    # Educational trackers include a fourth writing prompt. Give that prompt its
    # own space inside the panel instead of letting it collide with the border.
    tracker_panel_y = PAGE_H - (390 if educational else 360)
    tracker_panel_height = 170 if educational else 140
    c.roundRect(
        MARGIN,
        tracker_panel_y,
        PAGE_W - MARGIN * 2,
        tracker_panel_height,
        8,
        stroke=1,
        fill=0,
    )
    c.setFont("SansB", 13)
    c.drawString(MARGIN + 20, PAGE_H - 252, "My favorite puzzle:")
    c.line(MARGIN + 160, PAGE_H - 255, PAGE_W - MARGIN - 24, PAGE_H - 255)
    c.drawString(MARGIN + 20, PAGE_H - 292, "A new word I learned:" if educational else "A word I want to remember:")
    c.line(MARGIN + 200, PAGE_H - 295, PAGE_W - MARGIN - 24, PAGE_H - 295)
    c.drawString(MARGIN + 20, PAGE_H - 332, "My next puzzle:")
    c.line(MARGIN + 145, PAGE_H - 335, PAGE_W - MARGIN - 24, PAGE_H - 335)
    if educational:
        c.setFont("SansB", 13); c.drawString(MARGIN + 20, PAGE_H - 372, "Use that word in a sentence:")
        c.line(MARGIN + 205, PAGE_H - 375, PAGE_W - MARGIN - 24, PAGE_H - 375)
    c.setFont("SansB", 15)
    loved_heading_y = PAGE_H - (435 if educational else 420)
    c.drawString(MARGIN, loved_heading_y, "PUZZLES I LOVED")
    c.setFont("Sans", 12)
    y = PAGE_H - (467 if educational else 452)
    for index in range(1, min(count, 12) + 1):
        col = 0 if index <= 6 else 1
        row = (index - 1) % 6
        x = MARGIN + col * 265
        yy = y - row * 34
        c.rect(x, yy - 8, 11, 11, stroke=1, fill=0)
        # Educational books are themed too.  Repeating a generic
        # "Vocabulary Practice" label hid the actual mini-theme and made the
        # tracker look unfinished even when every puzzle was correctly named.
        name = tracker_puzzle_name(puzzles, index)
        c.drawString(x + 20, yy - 7, f"{index:02d}. {name}")
    c.setFillColorRGB(0.45, 0.45, 0.45)
    c.setFont("Sans", 9)
    c.drawCentredString(PAGE_W / 2, 58, running_title)
    c.showPage()
    return 2


def signature_pages(c: Canvas, puzzles: list[dict], running_title: str, config: dict | None = None) -> None:
    """Optional premium pages that make a collection feel collectible."""
    config = config or {}
    # Thirty compact entries per column keep a 60-puzzle collection together on
    # one page.  Longer collections split into balanced pages instead of letting
    # checkboxes drift below the printable area.
    passport_per_page = 60
    for start in range(0, len(puzzles), passport_per_page):
        page_puzzles = puzzles[start:start + passport_per_page]
        c.setFillColorRGB(0.1, 0.1, 0.1)
        c.setFont("SansB", 26)
        heading = str(config.get("passport_title", "PUZZLE PASSPORT")).upper()
        if len(puzzles) > passport_per_page:
            heading += f" - PAGE {start // passport_per_page + 1}"
        heading_size = 26
        while c.stringWidth(heading, "SansB", heading_size) > PAGE_W - 2 * MARGIN and heading_size > 8:
            heading_size -= 0.5
        c.setFont("SansB", heading_size)
        c.drawCentredString(PAGE_W / 2, PAGE_H - 110, heading)
        c.setFont("Sans", 12)
        c.drawCentredString(PAGE_W / 2, PAGE_H - 138, "Check off each puzzle as you complete it.")
        entries_per_column = min(30, max(1, math.ceil(len(page_puzzles) / 2)))
        row_step = 18
        for offset, puzzle in enumerate(page_puzzles):
            index = start + offset + 1
            col, row = divmod(offset, entries_per_column)
            column_width = (PAGE_W - 2 * MARGIN) / 2
            x = MARGIN + col * column_width
            y = PAGE_H - 185 - row * row_step
            c.rect(x, y - 9, 11, 11, stroke=1, fill=0)
            c.setFont("Sans", 9)
            label = f"{index:02d}. {puzzle.get('name', f'Puzzle {index}')}"
            max_label_width = column_width - 30
            if c.stringWidth(label, "Sans", 9) > max_label_width:
                while label and c.stringWidth(label + "...", "Sans", 9) > max_label_width:
                    label = label[:-1]
                label = label.rstrip() + "..."
            c.drawString(x + 18, y - 7, label)
        c.showPage()
    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.setFont("SansB", 28)
    c.drawCentredString(PAGE_W / 2, PAGE_H - 190, str(config.get("achievement_title", "SIGNATURE EDITION")).upper())
    c.setFont("Sans", 14)
    lines = [
        str(config.get("achievement_message", "A calm challenge, one puzzle at a time.")), "",
        "Achievement unlocked:",
        f"I completed all {len(puzzles)} puzzles in this collection.", "",
        "Date completed: ______________________________", "",
        "My favorite puzzle: __________________________", "",
        str(config.get("challenge", "Keep this passport as a reminder of every puzzle you solved.")),
    ]
    for i, line in enumerate(lines):
        c.drawCentredString(PAGE_W / 2, PAGE_H - 250 - i * 28, line)
    c.setFont("Sans", 9)
    c.setFillColorRGB(0.45, 0.45, 0.45)
    c.drawCentredString(PAGE_W / 2, 58, running_title)
    c.showPage()
    facts = [str(fact) for fact in config.get("fact_cards", []) if str(fact).strip()]
    if facts:
        c.setFillColorRGB(0.1, 0.1, 0.1)
        c.setFont("SansB", 26)
        c.drawCentredString(PAGE_W / 2, PAGE_H - 120, str(config.get("facts_title", "DID YOU KNOW?")).upper())
        y = PAGE_H - 180
        c.setFont("Sans", 13)
        for number, fact in enumerate(facts[:5], start=1):
            for line in _wrap(f"{number}. {fact}", 78):
                c.drawString(MARGIN, y, line)
                y -= 21
            y -= 16
        c.showPage()


def solutions_pages(c: Canvas, solutions: list[tuple[int, str, Grid, list[list[Cell]]]],
                     page_no_start: int, running_title: str, *, grayscale: bool = False) -> int:
    page_no = page_no_start
    # section divider
    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.setFont("SansB", 30)
    c.drawCentredString(PAGE_W / 2, PAGE_H / 2 + 10, "SOLUTIONS")
    footer(c, page_no)
    c.showPage()
    page_no += 1

    slots_top = [PAGE_H - 96, PAGE_H - 96 - 320]   # two solutions per page
    for i in range(0, len(solutions), 2):
        c.setFillColorRGB(0.5, 0.5, 0.5)
        c.setFont("Sans", 10)
        c.drawCentredString(PAGE_W / 2, PAGE_H - 40, running_title)
        for slot, sol in zip(slots_top, solutions[i:i + 2]):
            idx, name, grid, placements = sol
            c.setFillColorRGB(0.1, 0.1, 0.1)
            c.setFont("SansB", 13)
            c.drawCentredString(PAGE_W / 2, slot, f"PUZZLE {idx} - {name.upper()}")
            N = len(grid)
            cell = min(17, 260 / N)
            grid_w = N * cell
            gx = (PAGE_W - grid_w) / 2
            draw_grid(c, grid, gx, slot - 16, cell, max(9, int(cell * 0.58)),
                      highlights=placements, grayscale=grayscale)
        footer(c, page_no)
        c.showPage()
        page_no += 1
    return page_no


def back_matter(c: Canvas, author: str, also_from: list[dict]) -> None:
    """Back-matter pages — the highest-leverage thing for a new KDP book:
      1. Review request (lifts review count = lifts ranking).
      2. 'Also from [author]' cross-sell (when one book sells, the others get free shelf space).
      3. Short 'About' note.
    """
    # --- review request ---
    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.setFont("SansB", 28)
    c.drawCentredString(PAGE_W / 2, PAGE_H - 200, "DID YOU ENJOY THIS BOOK?")
    c.setFont("Sans", 14)
    lines = [
        "",
        "Reviews are how small publishers like us reach more readers.",
        "If you enjoyed these puzzles, please leave a quick review on Amazon.",
        "",
        "Even one honest sentence makes a real difference.",
        "",
        "Thank you, from everyone at " + (author or "our small press") + ".",
    ]
    for i, ln in enumerate(lines):
        c.drawCentredString(PAGE_W / 2, PAGE_H - 260 - i * 24, ln)
    # decorative rule
    c.setStrokeColorRGB(0.5, 0.55, 0.5)
    c.setLineWidth(1)
    c.line(PAGE_W / 2 - 80, PAGE_H - 470, PAGE_W / 2 + 80, PAGE_H - 470)
    # five star icons drawn as polygons (no font glyph dependency)
    c.setFillColorRGB(0.95, 0.78, 0.12)
    c.setStrokeColorRGB(0.7, 0.55, 0.08)
    c.setLineWidth(0.75)
    import math as _m
    star_y = PAGE_H - 510
    spacing = 32
    total_w = spacing * 4
    start_x = PAGE_W / 2 - total_w / 2
    R = 11
    for i in range(5):
        cx = start_x + i * spacing
        pts = []
        for k in range(10):
            ang = -_m.pi / 2 + k * _m.pi / 5
            r = R if k % 2 == 0 else R * 0.45
            pts.append((cx + r * _m.cos(ang), star_y + r * _m.sin(ang)))
        p = c.beginPath()
        p.moveTo(*pts[0])
        for pt in pts[1:]:
            p.lineTo(*pt)
        p.close()
        c.drawPath(p, stroke=1, fill=1)
    c.showPage()

    # --- also from <author> (series cross-sell) ---
    if also_from:
        c.setFillColorRGB(0.1, 0.1, 0.1)
        c.setFont("SansB", 26)
        c.drawCentredString(PAGE_W / 2, PAGE_H - 180, "ALSO FROM " + (author or "OUR PRESS").upper())
        c.setStrokeColorRGB(0.5, 0.55, 0.5)
        c.line(PAGE_W / 2 - 80, PAGE_H - 200, PAGE_W / 2 + 80, PAGE_H - 200)
        c.setFont("Sans", 13)
        c.drawCentredString(PAGE_W / 2, PAGE_H - 230,
                            "Search the titles below on Amazon to find them:")
        y = PAGE_H - 290
        for entry in also_from:
            c.setFont("SansB", 14)
            c.drawCentredString(PAGE_W / 2, y, entry.get("title", ""))
            sub = entry.get("subtitle", "")
            if sub:
                c.setFont("Sans", 11)
                c.setFillColorRGB(0.4, 0.4, 0.4)
                c.drawCentredString(PAGE_W / 2, y - 18, sub)
                c.setFillColorRGB(0.1, 0.1, 0.1)
            y -= 64
        c.showPage()

    # --- about the press ---
    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.setFont("SansB", 22)
    c.drawCentredString(PAGE_W / 2, PAGE_H - 180, "ABOUT " + (author or "OUR PRESS").upper())
    c.setFont("Sans", 13)
    about_lines = [
        "",
        f"{author} publishes calm, beautifully made puzzle books in",
        "large print, made to be easy on the eyes and a pleasure to solve.",
        "",
        "We believe a puzzle book should slow time down, not race it.",
        "We plan each collection with care and review its puzzles for quality.",
        "",
        "Thank you for spending your time with one of our books.",
    ]
    for i, ln in enumerate(about_lines):
        c.drawCentredString(PAGE_W / 2, PAGE_H - 240 - i * 22, ln)
    c.showPage()


# ---------------- utils ----------------
def _wrap(text: str, width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        if len(cur) + len(w) + 1 <= width:
            cur = (cur + " " + w).strip()
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [text]


def clean_words(words: list[str], *, strict: bool = True) -> list[str]:
    out: list[str] = []
    for w in words:
        w = "".join(ch for ch in w.upper() if ch.isalpha())
        if strict and (not w or not w.isascii() or len(w) > MAX_GRID_N):
            raise ValueError(f'Target {w!r} must contain 1–{MAX_GRID_N} A-Z letters; replace it before building.')
        if w and len(w) <= MAX_GRID_N:
            out.append(w)
    if strict and len(out) != len(set(out)):
        raise ValueError('Two targets normalize to the same word; replace the duplicate.')
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--themes", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--title")
    ap.add_argument("--subtitle")
    ap.add_argument("--author")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--signature-edition", action="store_true", help="add a puzzle passport and achievement page")
    ap.add_argument("--preview-puzzles", type=int, help="generate only the first N puzzles plus solutions for a quick reader preview")
    a = ap.parse_args()

    random.seed(a.seed)
    try:
        with open(a.themes, encoding="utf-8-sig") as theme_file:
            data = json.load(theme_file)
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Could not read theme file '{a.themes}': {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("puzzles"), list) or not data["puzzles"]:
        raise SystemExit("This theme file must contain a non-empty 'puzzles' list.")
    title = a.title or data.get("title", "Word Search")
    subtitle = a.subtitle or data.get("subtitle", "")
    author = a.author or data.get("author", "")
    running = title
    puzzles = data["puzzles"][:max(1, a.preview_puzzles)] if a.preview_puzzles else data["puzzles"]

    if data.get("interior_profile") == "memories_large_print_v1":
        from publishing.accessible_wordsearch import render
        if a.preview_puzzles or a.signature_edition:
            raise SystemExit("The accessible 80-puzzle profile requires its complete standard-edition source.")
        report = render({**data, "title": title, "subtitle": subtitle, "author": author}, a.out, a.seed)
        print(f"DONE -> {a.out}: {report['puzzle_count']} puzzles, {report['page_count']} pages; human review pending")
        return

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    register_fonts()
    c = canvas.Canvas(a.out, pagesize=letter, initialFontName="Sans")
    c.setTitle(title)
    c.setAuthor(author)

    data["puzzle_count"] = len(puzzles)
    front_matter(c, title, subtitle, author, data)
    themed_welcome_page(c, data, title)
    detail_pages(c, data, puzzles, running)
    # Signature pages are an edition choice made at package time.  Saved theme
    # files can retain design notes for a Signature Edition, but a normal book
    # must never silently inherit the premium pages from those notes.
    signature_config = data.get("signature_edition", {})
    if a.signature_edition:
        signature_pages(c, puzzles, running, signature_config if isinstance(signature_config, dict) else {})

    solutions = []
    page_no = 1
    section_plan = interior_section_plan(data, puzzles)
    topic_text = (str(data.get("detected_topic") or "") + " " + str(data.get("series") or "")).casefold()
    educational = any(token in topic_text for token in ("vocabulary", "grade school", "middle school", "high school"))
    from word_intelligence.page_titles import puzzle_page_title
    records = []
    from publishing.puzzle_integrity import write_manifest, wordsearch_difficulty
    for i, p in enumerate(puzzles, start=1):
        section = section_plan[i - 1]
        if section["starts_section"] and section["divider_pages"]:
            section_divider_page(c, section, page_no, running)
            page_no += 1
        words = clean_words(p["words"])
        from publishing.studio_reader_profiles import reader_profile, word_suits_reader, check_reader_topic
        reader_key = data.get('reader_profile', 'standard')
        profile = reader_profile(reader_key)
        check_reader_topic(data.get('detected_topic', ''), reader_key)
        if any(not word_suits_reader(word, reader_key) for word in words):
            raise ValueError('The word list no longer fits its reader profile. Refresh the checked word plan.')
        n = grid_size_for(words) if reader_key == 'standard' else max(profile['grid'], max(map(len, words)))
        grid, placements, placed = generate_puzzle(words, N=n, directions=profile['directions'])
        records.append(dict(number=i, type='word_search', grid=grid, placements=placements, words=placed,
                            intended_words=words, directions=profile['directions'], puzzle_page=c.getPageNumber(),
                            solution_grid=grid, solution_placements=placements,
                            difficulty=wordsearch_difficulty(grid,placements,placed)))
        page_title = puzzle_page_title(data, p, i)
        vocabulary_note = str(p.get("vocabulary_note") or p.get("usage_prompt") or "")
        puzzle_page(c, i, page_title, grid, words, page_no, running, section, educational, vocabulary_note, reader_key)
        solutions.append((i, page_title, grid, placements))
        page_no += 1

    solution_start = c.getPageNumber() + 1
    solutions_pages(c, solutions, page_no, running)
    for index, record in enumerate(records):
        record['solution_page'] = solution_start + index // 2

    # Back-matter: review request + cross-sell + about
    also_from = data.get("also_from", [])
    back_matter(c, author, also_from)

    # Print books use physical sheets.  KDP can add a blank page to an odd
    # manuscript, but doing it here keeps the approved interior page count and
    # calculated cover spine in agreement before the files ever leave Studio.
    completed_pages = c.getPageNumber() - 1
    if completed_pages % 2:
        c.showPage()

    c.save()
    write_manifest(a.out, records, getattr(c,'_puzzle_text_regions',[]))

    n_puzzles = len(puzzles)
    size_kb = os.path.getsize(a.out) / 1024
    print(f"DONE -> {a.out}")
    print(f"  {n_puzzles} puzzles + solutions, {size_kb:.0f} KB, 8.5x11 print-ready")


if __name__ == "__main__":
    main()
