"""Compile the three editorial manuscripts to the studio's existing theme schema.

No approval is inferred from compilation or an automated check. Draft sources
stay outside the active theme catalog until explicitly promoted for review.
"""
from __future__ import annotations

import json
from pathlib import Path
import random

from .repetition_policy import POLICY_ID, BOOK_IDS, evaluate
from .accessible_wordsearch import PROFILE


def compile_source(path: Path) -> dict:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if raw["book_id"] not in BOOK_IDS:
        raise ValueError("Not an authorized collection source.")
    puzzles = []
    for section in raw["sections"]:
        if len(section["puzzles"]) != 8:
            raise ValueError("Each section requires eight puzzles.")
        for name, word_line, prompt in section["puzzles"]:
            words = [word.strip() for word in word_line.split(",")]
            random.Random(8000 + len(puzzles)).shuffle(words)
            puzzles.append({"name": name, "words": words, "section": section["title"],
                "mini_theme": section["title"], "reflection_prompt": prompt,
                "page_title_basis": "editorial_review", "editorial_reviewer": "AI draft; human review pending"})
    data = {"title": raw["title"], "subtitle": raw["subtitle"], "author": "Jordan M. Slade",
        "brand": "SladePuzzleCo", "audience": "Older adults who enjoy familiar everyday themes",
        "detected_topic": raw["topic"], "difficulty_label": "Easy", "large_print": True,
        "collection_id": POLICY_ID, "collection_book_id": raw["book_id"],
        "repetition_policy": {"id": POLICY_ID}, "no_repeat_words": False,
        "interior_profile": PROFILE, "puzzle_type": "Word Search", "puzzles": puzzles,
        "cover_badge": "80 PUZZLES", "palette": "nature", "cover_style": "photo",
        "welcome": raw["welcome"], "closing": raw["closing"],
        "accessible_sections": [{k: v for k, v in s.items() if k != "puzzles"} for s in raw["sections"]],
        "production_provenance": {"text": "AI-generated and edited", "human_content_approval": "pending",
                                  "source": str(Path(path).resolve())}}
    report = evaluate(data)
    if not report["passed"]:
        raise ValueError("; ".join(report["errors"]))
    return data
