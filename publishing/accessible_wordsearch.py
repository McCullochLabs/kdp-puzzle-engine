"""Opt-in accessible interior, rendered by the existing wordsearch CLI.

This module deliberately has no approval, catalog or marketplace operations.
It records actual grids and independent checks alongside the PDF for later QA.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import random

from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth
from .repetition_policy import POLICY_ID, BOOK_IDS, evaluate, normalize

PROFILE = "memories_large_print_v1"
COLLECTION_ID = POLICY_ID
EASY_DIRECTIONS = ((0, 1), (1, 0), (1, 1), (1, -1))
ALL_DIRECTIONS = EASY_DIRECTIONS + ((0, -1), (-1, 0), (-1, -1), (-1, 1))
# Bounded screen, not a claim that all possible offensive strings are detected.
ACCIDENTAL_DENYLIST = ("FUCK", "SHIT", "CUNT", "NIGGER", "FAGGOT")


def compile_editorial_source(raw: dict) -> dict:
    """Map a curated collection draft into the same theme model the studio reads."""
    book_id = str(raw.get("book_id") or "")
    titles = {"growing_up_50s_60s": "Growing Up in the 50s and 60s",
              "kitchen_table_memories": "Kitchen Table Memories",
              "summer_days_remembered": "Summer Days Remembered"}
    if book_id not in BOOK_IDS:
        raise ValueError("This production route only accepts the three approved collection book IDs.")
    if raw.get("title") != titles[book_id]:
        raise ValueError("The collection title does not match the approved working metadata.")
    sections = raw.get("sections")
    if not isinstance(sections, list) or len(sections) != 10:
        raise ValueError("The editorial source must contain ten sections.")
    puzzles = []
    for chapter in sections:
        rows = chapter.get("puzzles") if isinstance(chapter, dict) else None
        if not isinstance(rows, list) or len(rows) != 8:
            raise ValueError("Each editorial section must contain eight puzzle topics.")
        for name, display_words, prompt in rows:
            words = [item.strip() for item in str(display_words).split(",")]
            puzzles.append({"name": str(name), "section": str(chapter["title"]),
                            "mini_theme": str(chapter["title"]), "words": words,
                            "reflection_prompt": str(prompt)})
    result = {key: raw[key] for key in ("title", "subtitle", "topic", "welcome", "closing")}
    result.update({"author": "Jordan M. Slade", "brand": "SladePuzzleCo",
        "series": "Everyday Moments Word Search Collection", "audience": "Adults",
        "difficulty_label": "Easy", "large_print": True, "puzzle_count": 80,
        "words_per_puzzle": 12, "puzzle_type": "Word Search", "trim_size": "8.5x11",
        "page_count": 160, "detected_topic": raw["topic"], "difficulty": "Easy",
        "collection_id": COLLECTION_ID, "collection_book_id": book_id,
        "repetition_policy": {"id": POLICY_ID}, "no_repeat_words": False,
        "cover_badge": "80 PUZZLES", "interior_profile": PROFILE,
        "content_review_status": "pending_human_editorial_review",
        "cover_approval_status": "pending_human_aesthetic_review",
        "accessible_sections": sections, "puzzles": puzzles})
    return result


def occurrences(grid, word, directions=ALL_DIRECTIONS):
    found = []
    seen = set()
    for row in range(len(grid)):
        for col in range(len(grid)):
            for dr, dc in directions:
                cells = [(row + dr * k, col + dc * k) for k in range(len(word))]
                if all(0 <= r < len(grid) and 0 <= c < len(grid) for r, c in cells):
                    if "".join(grid[r][c] for r, c in cells) == word:
                        # A palindrome read in reverse is the same physical answer.
                        key = tuple(sorted(cells))
                        if key not in seen:
                            seen.add(key); found.append(cells)
    return found


def verify_grid(grid, placements, words):
    issues = []
    if len(grid) != 12 or any(len(row) != 12 for row in grid):
        return ["Grid must be 12 x 12."]
    if any(len(ch) != 1 or ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" for row in grid for ch in row):
        return ["Grid contains a non-ASCII letter."]
    if len(placements) != len(words) or len(words) != len(set(words)):
        issues.append("Placement count or target uniqueness mismatch.")
    for word, cells in zip(words, placements):
        if len(cells) != len(word) or any(not (0 <= r < 12 and 0 <= c < 12) for r, c in cells):
            issues.append(f"Invalid placement: {word}"); continue
        if "".join(grid[r][c] for r, c in cells) != word:
            issues.append(f"Placement does not spell {word}.")
        steps = {(b[0] - a[0], b[1] - a[1]) for a, b in zip(cells, cells[1:])}
        if len(steps) != 1 or not steps <= set(EASY_DIRECTIONS):
            issues.append(f"Disallowed direction: {word}.")
        if len(occurrences(grid, word)) != 1:
            issues.append(f"Target must occur exactly once in all eight directions: {word}.")
    for term in ACCIDENTAL_DENYLIST:
        if occurrences(grid, term):
            issues.append("Accidental denylist match.")
    return issues


def make_plan(data, seed):
    import wordsearch as engine
    repetition = evaluate(data)
    if not repetition["passed"]:
        raise ValueError("; ".join(repetition["errors"]))
    sections = data.get("accessible_sections")
    if not isinstance(sections, list) or len(sections) != 10:
        raise ValueError("Accessible collection requires ten editorial sections.")
    for section in sections:
        for field in ("title", "introduction", "reflection", "closing_reflection"):
            if not str(section.get(field) or "").strip():
                raise ValueError(f"Section requires {field}.")
    records, hashes = [], set()
    for index, puzzle in enumerate(data["puzzles"]):
        display = puzzle["words"]
        normalized = [normalize(word) for word in display]
        if any(not 3 <= len(word) <= 12 for word in normalized):
            raise ValueError(f"Puzzle {index + 1}: every target must have 3–12 normalized letters.")
        contained = [(short, long) for short in normalized for long in normalized
                     if short != long and len(short) < len(long)
                     and (short in long or short in long[::-1])]
        if contained:
            short, long = contained[0]
            raise ValueError(f"Puzzle {index + 1}: {short} is contained forwards or backwards in {long}; replace one target to avoid duplicate answer locations.")
        if not str(puzzle.get("reflection_prompt") or "").strip():
            raise ValueError(f"Puzzle {index + 1} needs its original optional prompt.")
        if puzzle.get("section") != sections[index // 8]["title"]:
            raise ValueError(f"Puzzle {index + 1}: section allocation mismatch.")
        for attempt in range(200):
            actual_seed = seed + index * 1000 + attempt
            grid, placements, placed = engine.generate_puzzle(normalized, N=12,
                directions=EASY_DIRECTIONS, rng=random.Random(actual_seed))
            issues = verify_grid(grid, placements, placed)
            if sorted(placed) != sorted(normalized):
                issues.append("Not all intended targets were placed.")
            digest = hashlib.sha256(json.dumps(grid).encode()).hexdigest()
            if not issues and digest not in hashes:
                hashes.add(digest)
                records.append({"number": index + 1, "name": puzzle["name"],
                    "grid": grid, "placements": placements, "placed": placed,
                    "display_words": display, "seed": actual_seed, "grid_sha256": digest,
                    "puzzle_page": 10 + index // 8 * 10 + index % 8,
                    "solution_page": 109 + index // 2, "validation_errors": []})
                break
        else:
            raise ValueError(f"Puzzle {index + 1}: no independently valid grid after 200 attempts; revise its word list.")
    return records, repetition


def _text(c, text, x, y, width=504, size=18, font="Sans", leading=None, bottom=54):
    leading = leading or size * 1.35
    c.setFont(font, size); c.setFillGray(0)
    for paragraph in str(text).split("\n"):
        line = ""
        for word in paragraph.split():
            if stringWidth(word, font, size) > width:
                raise ValueError(f"Unbreakable text exceeds layout width: {word}")
            candidate = f"{line} {word}".strip()
            if stringWidth(candidate, font, size) > width and line:
                if y < bottom: raise ValueError("Text overflow; do not reduce print size.")
                c.drawString(x, y, line); y -= leading; line = word
            else: line = candidate
        if line:
            if y < bottom: raise ValueError("Text overflow; do not reduce print size.")
            c.drawString(x, y, line); y -= leading
        y -= leading * .3
    return y


def _finish(c):
    c.setFillGray(0); c.setFont("Sans", 12)
    c.drawCentredString(306, 34, str(c.getPageNumber()))
    c.showPage()


def _reading_page(c, heading, body, prompts=()):
    y = _text(c, heading, 54, 716, size=28, font="SansB") - 28
    y = _text(c, body, 54, y) - 24
    for prompt in prompts:
        y = _text(c, prompt, 54, y) - 22
        for _ in range(3):
            if y < 70: raise ValueError("Reflection page exceeds safe area.")
            c.setStrokeGray(.65); c.line(54, y, 558, y); y -= 32
        y -= 14
    _finish(c)


def _grid(c, record, *, x, top, cell, font, answers=False):
    import wordsearch as engine
    # Use the established grid renderer, but gray highlights for a black-ink book.
    if answers:
        c.saveState(); c.setLineCap(1); c.setLineWidth(cell * .78); c.setStrokeGray(.80)
        for cells in record["placements"]:
            a, b = cells[0], cells[-1]
            c.line(x + (a[1] + .5) * cell, top - (a[0] + .5) * cell,
                   x + (b[1] + .5) * cell, top - (b[0] + .5) * cell)
        c.restoreState()
    engine.draw_grid(c, record["grid"], x, top, cell, font)
    c._puzzle_text_regions[-1]['role'] = 'solution' if answers else 'puzzle'


def render(data, path, seed):
    """Write a full, validated interior; never claims release approval."""
    import wordsearch as engine
    records, repetition = make_plan(data, seed)
    engine.register_fonts()
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=(612, 792))
    c.setTitle(data["title"]); c.setAuthor(data["author"])
    _reading_page(c, data["title"], data["subtitle"] + "\n\n" + data["author"] + "\nSladePuzzleCo")
    _reading_page(c, "Copyright", "Copyright 2026 " + data["author"] + ". All rights reserved.\n\n"
        "Published by SladePuzzleCo. No part of this book may be reproduced for distribution without permission, except as allowed by law.\n\n"
        "Words and optional reflections explore familiar experiences. No shared upbringing or particular memory is assumed. This is a recreational puzzle collection, not medical advice.")
    _reading_page(c, "Make yourself comfortable", data["welcome"])
    _reading_page(c, "A gentle way to search", "Choose any puzzle. Look for twelve words in the grid. Words run right, down, or diagonally downward in either direction. None run upward or backward.\n\nSpaces and punctuation appear in the word list but are omitted in the grid. Circle each word you find. Every target appears once.\n\nThe prompts are optional. You may recall, imagine, write, talk, or simply move to the next puzzle. There is no timer.")
    _reading_page(c, "A worked example", "For the word TABLE, follow T A B L E in a straight line. The same rule works for a word running down or diagonally downward.\n\nFor ICE CREAM, search for ICECREAM without a space. The word list retains its natural spelling.\n\nA word may share letters with another word. Check the solution page printed on each puzzle whenever you like.")
    _reading_page(c, "Before you begin", "Try this short activity: choose a familiar object near you and say its name one letter at a time. Imagine those letters in a straight line.\n\nFind a comfortable place and lighting that suits you. Use whichever pencil or pen you prefer.", ["What would make a puzzle break enjoyable for you today?"])
    _reading_page(c, "Explore the ten sections", "\n".join(f"{s['title']} - page {9 + i * 10}" for i, s in enumerate(data["accessible_sections"])))
    _reading_page(c, "Your puzzle preferences", "You can begin anywhere. These choices are optional and can change each time you return.", ["Would you prefer quiet time or a shared puzzle?", "Which theme would you like to explore first?"])
    for chapter, section in enumerate(data["accessible_sections"]):
        _reading_page(c, section["title"], section["introduction"])
        for index in range(chapter * 8, chapter * 8 + 8):
            item, puzzle = records[index], data["puzzles"][index]
            assert c.getPageNumber() == item["puzzle_page"]
            _text(c, f"{item['number']:02d}  {puzzle['name']}", 54, 728, size=24, font="SansB", bottom=688)
            _grid(c, item, x=102, top=672, cell=34, font=26)
            c._puzzle_text_regions.append(dict(page=c.getPageNumber(),role='word_list',
                bounds=[54,150,558,245],font_pt=18))
            for i, word in enumerate(item["display_words"]):
                _text(c, word, 54 + (i // 4) * 168, 230 - (i % 4) * 24, width=158, size=18, bottom=152)
            _text(c, "Optional: " + puzzle["reflection_prompt"], 54, 112, size=18, bottom=65)
            c.setFont("Sans", 12); c.drawString(54, 49, f"Solution: page {item['solution_page']}")
            _finish(c)
        _reading_page(c, "A moment with " + section["title"].lower(), "Remember, imagine, or leave this page for another day.", [section["reflection"]])
    for index in range(0, 80, 2):
        assert c.getPageNumber() == records[index]["solution_page"]
        for offset, top in ((0, 706), (1, 368)):
            item = records[index + offset]
            _text(c, f"{item['number']:02d}  {item['name']}", 54, top + 22, size=18, font="SansB", bottom=top + 20)
            _grid(c, item, x=162, top=top, cell=24, font=18, answers=True)
        _finish(c)
    for section in data["accessible_sections"]:
        _reading_page(c, "One more thought: " + section["title"], "There is no right answer. Make this page your own.", [section["closing_reflection"]])
    _reading_page(c, "Thank you for spending time here", data["closing"])
    _reading_page(c, "Keep a favorite thought", "A small detail, a new idea, or a place you would like to return to can be worth saving.", ["What would you like to carry away from this collection?"])
    if c.getPageNumber() != 161:
        raise ValueError("Accessible interior pagination mismatch.")
    c.save()
    from .puzzle_integrity import write_manifest, wordsearch_difficulty
    manifest_records = [dict(number=row['number'], type='word_search', grid=row['grid'],
        words=row['placed'], intended_words=row['placed'], placements=row['placements'],
        solution_grid=row['grid'],solution_placements=row['placements'], directions=EASY_DIRECTIONS,
        puzzle_page=row['puzzle_page'],solution_page=row['solution_page'],
        puzzle_heading=f"{row['number']:02d} {row['name']}",solution_heading=f"{row['number']:02d} {row['name']}",
        difficulty=wordsearch_difficulty(row['grid'],row['placements'],row['placed'])) for row in records]
    write_manifest(path, manifest_records, getattr(c,'_puzzle_text_regions',[]))
    report = {"profile": PROFILE, "page_count": 160, "puzzle_count": 80,
        "grid_size": 12, "grid_font_pt": 26, "word_font_pt": 18, "solution_font_pt": 18,
        "seed": seed, "repetition": repetition, "puzzles": records,
        "interior_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "human_editorial_review": "pending", "physical_proof": "not inspected"}
    path.with_suffix(".validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
