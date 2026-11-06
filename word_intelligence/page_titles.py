"""Truthful reader-facing titles for Word Search puzzle pages.

Legacy themes often contain decorative page names that were created before
mini-theme evidence was tracked.  A page may use a narrow title only when the
source explicitly records that the words were allocated from that reviewed
mini-theme.  Otherwise the reader sees an honest book-topic label.
"""
from __future__ import annotations

import re


TOPIC_LABELS = {
    "bible and faith": "BIBLE & FAITH WORDS",
    "vehicles & automotive": "CARS & ROAD TRIPS",
    "american history": "AMERICAN HISTORY MIX",
    "grade school vocabulary": "GRADE SCHOOL VOCABULARY",
    "grade 5 vocabulary": "GRADE 5 VOCABULARY",
    "middle school vocabulary": "MIDDLE SCHOOL VOCABULARY",
    "high school vocabulary": "HIGH SCHOOL VOCABULARY",
}


def topic_page_label(data: dict) -> str:
    raw = str(data.get("detected_topic") or data.get("topic") or data.get("series") or data.get("title") or "WORD SEARCH").strip()
    known = TOPIC_LABELS.get(raw.casefold())
    if known:
        return known
    raw = re.sub(r"\bword\s*search\b", "", raw, flags=re.I)
    raw = re.sub(r"\s+", " ", raw).strip(" -:|") or "WORD SEARCH"
    return f"{raw.upper()} WORD MIX"


def puzzle_page_title(data: dict, puzzle: dict, number: int) -> str:
    """Return a narrow title only when its mini-theme origin is auditable."""
    basis = str(puzzle.get("page_title_basis") or "").casefold()
    verified = bool(puzzle.get("page_title_verified")) or basis in {
        "reviewed_mini_theme", "strict_mini_theme_allocation", "editorial_review"
    }
    mini_theme = str(puzzle.get("mini_theme") or "").strip()
    if verified and mini_theme:
        return mini_theme
    if verified and str(puzzle.get("name") or "").strip():
        return str(puzzle["name"]).strip()
    return f"{topic_page_label(data)} {number:02d}"


def title_is_truthful(data: dict, puzzle: dict, number: int) -> bool:
    """A narrow legacy label is truthful only when evidence accompanies it."""
    rendered = puzzle_page_title(data, puzzle, number)
    return bool(rendered)
