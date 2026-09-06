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
from reportlab.lib.pagesizes import letter

PAGE_W, PAGE_H = letter            # 612 x 792 pt  (8.5 x 11 in)
MARGIN = 54                        # 0.75in uniform — safe KDP gutter (<150pg) + roomy large print
GRID_N = 15  # The familiar default used for standard 12-word puzzles.
MAX_GRID_N = 21
DIRS = [(0, 1), (1, 0), (1, 1), (1, -1), (0, -1), (-1, 0), (-1, -1), (-1, 1)]

Cell = tuple[int, int]
Grid = list[list[str]]

from font_utils import pdf_font_candidates, register_pdf_font

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
def _try_place(grid: Grid, word: str, N: int) -> list[Cell] | None:
    dr, dc = random.choice(DIRS)
    r, c = random.randint(0, N - 1), random.randint(0, N - 1)
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


def generate_puzzle(words: list[str], N: int = GRID_N) -> tuple[Grid, list[list[Cell]], list[str]]:
    """Place every word when possible, retrying a whole grid before accepting less.

    A greedy placement can occasionally paint itself into a corner even for a
    small 12-word puzzle.  Retrying the empty grid makes package-time results
    stable and prevents a different seed from passing a check then losing a
    word in the finished PDF.
    """
    ordered = sorted(words, key=len, reverse=True)
    best: tuple[Grid, list[list[Cell]], list[str]] | None = None
    for _attempt in range(30):
        grid: Grid = [["" for _ in range(N)] for _ in range(N)]
        placements: list[list[Cell]] = []
        placed: list[str] = []
        for word in ordered:
            cells = None
            for _ in range(500):
                cells = _try_place(grid, word, N)
                if cells:
                    break
            if cells:
                placements.append(cells); placed.append(word)
        if best is None or len(placed) > len(best[2]):
            best = (grid, placements, placed)
        if len(placed) == len(ordered):
            break
    assert best is not None
    grid, placements, placed = best
    for r in range(N):
        for c in range(N):
            if not grid[r][c]:
                grid[r][c] = random.choice(string.ascii_uppercase)
    return grid, placements, placed


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
              font_size: float, highlights: list[list[Cell]] | None = None) -> None:
    N = len(grid)
    h = N * cell
    # faint internal gridlines
    c.setLineWidth(0.5)
    c.setStrokeColorRGB(0.86, 0.86, 0.86)
    for i in range(N + 1):
        c.line(gx + i * cell, gy_top, gx + i * cell, gy_top - h)
        c.line(gx, gy_top - i * cell, gx + N * cell, gy_top - i * cell)
    # solution highlighters (drawn UNDER the letters)
    if highlights:
        c.setLineCap(1)
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
    rows = math.ceil(len(words) / cols)
    col_w = grid_w / cols
    c.setFont("Sans", word_font)
    start_y = top_y - heading_font - 10
    for i, w in enumerate(words):
        col, row = i // rows, i % rows
        x = gx + col * col_w + 8
        y = start_y - row * row_step
        c.drawString(x, y, w)


def footer(c: Canvas, page_no: int) -> None:
    c.setFillColorRGB(0.45, 0.45, 0.45)
    c.setFont("Sans", 9)
    c.drawCentredString(PAGE_W / 2, 34, str(page_no))


# ---------------- pages ----------------
def front_matter(c: Canvas, title: str, subtitle: str, author: str) -> None:
    # title page
    c.setFillColorRGB(0.10, 0.10, 0.10)
    title_lines = _wrap(title.upper(), 16)
    title_top = PAGE_H - 220
    title_step = 38
    for i, line in enumerate(title_lines):
        # Character wrapping alone is not enough for wide capital letters.
        # Keep every title line within the same print-safe area as the puzzles.
        title_font = 30
        while title_font > 14:
            c.setFont("SansB", title_font)
            if c.stringWidth(line, "SansB", title_font) <= PAGE_W - (MARGIN * 2):
                break
            title_font -= 1
        c.setFont("SansB", title_font)
        c.drawCentredString(PAGE_W / 2, title_top - i * title_step, line)
    title_bottom = title_top - max(0, len(title_lines) - 1) * title_step
    subtitle_top = title_bottom - 46
    c.setFont("Sans", 15)
    subtitle_lines = _wrap(subtitle, 40)
    for i, line in enumerate(subtitle_lines):
        c.drawCentredString(PAGE_W / 2, subtitle_top - i * 22, line)
    subtitle_bottom = subtitle_top - max(0, len(subtitle_lines) - 1) * 22
    c.setStrokeColorRGB(0.7, 0.7, 0.7)
    c.setLineWidth(1)
    rule_y = subtitle_bottom - 32
    c.line(PAGE_W / 2 - 80, rule_y, PAGE_W / 2 + 80, rule_y)
    c.setFont("Sans", 13)
    c.drawCentredString(PAGE_W / 2, 120, author)
    c.showPage()

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
    how = [
        "Each puzzle hides a list of words in a grid of letters.",
        "",
        "Words run in straight lines - across, down, diagonally,",
        "and sometimes backwards.",
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
                 page_no: int, running_title: str, section: dict | None = None) -> None:
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
    chapter_label = f"CHAPTER {section.get('chapter', 1)}"
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
    gx = (PAGE_W - grid_w) / 2
    gy_top = PAGE_H - 122          # grid bottom = 670 - 450 = 220
    draw_grid(c, grid, gx, gy_top, cell, letter_font)

    draw_word_list(c, words, gx, gy_top - N * cell - 26, grid_w, cols=3,
                   **list_settings)
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
    c.drawCentredString(PAGE_W / 2, PAGE_H - 130, "MY PUZZLE NOTES")
    c.setFont("Sans", 13)
    c.drawCentredString(PAGE_W / 2, PAGE_H - 160, "Keep track of the puzzles and words you enjoyed most.")
    c.setStrokeColorRGB(0.45, 0.45, 0.45); c.setLineWidth(1)
    c.roundRect(MARGIN, PAGE_H - 360, PAGE_W - MARGIN * 2, 140, 8, stroke=1, fill=0)
    c.setFont("SansB", 13)
    c.drawString(MARGIN + 20, PAGE_H - 252, "My favorite puzzle:")
    c.line(MARGIN + 160, PAGE_H - 255, PAGE_W - MARGIN - 24, PAGE_H - 255)
    c.drawString(MARGIN + 20, PAGE_H - 292, "A word I want to remember:")
    c.line(MARGIN + 200, PAGE_H - 295, PAGE_W - MARGIN - 24, PAGE_H - 295)
    c.drawString(MARGIN + 20, PAGE_H - 332, "My next puzzle:")
    c.line(MARGIN + 145, PAGE_H - 335, PAGE_W - MARGIN - 24, PAGE_H - 335)
    c.setFont("SansB", 15)
    c.drawString(MARGIN, PAGE_H - 420, "PUZZLES I LOVED")
    c.setFont("Sans", 12)
    y = PAGE_H - 452
    for index in range(1, min(count, 12) + 1):
        col = 0 if index <= 6 else 1
        row = (index - 1) % 6
        x = MARGIN + col * 265
        yy = y - row * 34
        c.rect(x, yy - 8, 11, 11, stroke=1, fill=0)
        name = str(puzzles[index - 1].get("name", f"Puzzle {index}"))[:28]
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
        c.drawCentredString(PAGE_W / 2, PAGE_H - 110, heading)
        c.setFont("Sans", 12)
        c.drawCentredString(PAGE_W / 2, PAGE_H - 138, "Check off each puzzle as you complete it.")
        entries_per_column = min(30, max(1, math.ceil(len(page_puzzles) / 2)))
        row_step = 18
        for offset, puzzle in enumerate(page_puzzles):
            index = start + offset + 1
            col, row = divmod(offset, entries_per_column)
            x = MARGIN + col * 280
            y = PAGE_H - 185 - row * row_step
            c.rect(x, y - 9, 11, 11, stroke=1, fill=0)
            c.setFont("Sans", 9)
            label = str(puzzle.get("name", f"Puzzle {index}"))[:34]
            c.drawString(x + 18, y - 7, f"{index:02d}. {label}")
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
                     page_no_start: int, running_title: str) -> int:
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
            draw_grid(c, grid, gx, slot - 16, cell, max(7, int(cell * 0.58)),
                      highlights=placements)
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
    c.setLineWidth(0.6)
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
        "We make every book by hand and care a great deal about quality.",
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


def clean_words(words: list[str]) -> list[str]:
    out: list[str] = []
    for w in words:
        w = "".join(ch for ch in w.upper() if ch.isalpha())
        if w and len(w) <= MAX_GRID_N:
            out.append(w)
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

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    register_fonts()
    c = canvas.Canvas(a.out, pagesize=letter)
    c.setTitle(title)
    c.setAuthor(author)

    front_matter(c, title, subtitle, author)
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
    for i, p in enumerate(puzzles, start=1):
        section = section_plan[i - 1]
        if section["starts_section"] and section["divider_pages"]:
            section_divider_page(c, section, page_no, running)
            page_no += 1
        words = clean_words(p["words"])
        grid, placements, placed = generate_puzzle(words, N=grid_size_for(words))
        puzzle_page(c, i, p["name"], grid, placed, page_no, running, section)
        solutions.append((i, p["name"], grid, placements))
        if len(placed) < len(words):
            print(f"  note: puzzle {i} '{p['name']}' placed {len(placed)}/{len(words)} words")
        page_no += 1

    solutions_pages(c, solutions, page_no, running)

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

    n_puzzles = len(puzzles)
    size_kb = os.path.getsize(a.out) / 1024
    print(f"DONE -> {a.out}")
    print(f"  {n_puzzles} puzzles + solutions, {size_kb:.0f} KB, 8.5x11 print-ready")


if __name__ == "__main__":
    main()
