"""Safe planning support for expanding topic libraries.

This module never inserts unreviewed words into the Master Library.  It shows
the exact capacity gap, the currently linked source topics, and a research
brief the publisher can review before bringing new vocabulary into the app.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .content_capacity import FAMILY_PACKS, TOPIC_GROUPS, WORDSEARCH_BOOK_SIZE, topic_capacity

WORDS_PER_WORDSEARCH_PUZZLE = 12
TWO_BOOK_WORD_TARGET = WORDSEARCH_BOOK_SIZE * WORDS_PER_WORDSEARCH_PUZZLE * 2


def expansion_plan(project: Path, topic: str) -> dict:
    """Return an honest, no-write expansion plan for one topic family."""
    project = Path(project)
    row = next((item for item in topic_capacity(project) if item["topic"] == topic), None)
    if not row:
        raise ValueError("Choose a topic family from Content capacity first.")
    current = int(row.get("words") or 0)
    source_topics = list(FAMILY_PACKS.get(topic, TOPIC_GROUPS.get(topic, ())))
    missing = max(0, TWO_BOOK_WORD_TARGET - current)
    terms = [
        f"{topic} vocabulary glossary",
        f"{topic} terminology list",
        f"{topic} beginner guide vocabulary",
        f"{topic} facts and reference terms",
    ]
    state = "Two-book ready" if missing == 0 else f"Needs {missing:,} additional reviewed words for two 48-puzzle Word Search books."
    return {
        "topic": topic,
        "current_words": current,
        "target_words": TWO_BOOK_WORD_TARGET,
        "missing_words": missing,
        "source_topics": source_topics,
        "research_queries": terms,
        "state": state,
        "next_step": row.get("next_step") or "Review linked sources.",
    }


def save_research_brief(project: Path, topic: str) -> Path:
    """Save a small review brief, never changing the Master Library itself."""
    plan = expansion_plan(project, topic)
    folder = Path(project) / "word_banks" / "research_briefs"
    folder.mkdir(parents=True, exist_ok=True)
    safe = "".join(char.lower() if char.isalnum() else "_" for char in topic).strip("_") or "topic"
    target = folder / f"{safe}_expansion_brief.json"
    target.write_text(json.dumps({"created": datetime.now().isoformat(timespec="seconds"), **plan}, indent=2) + "\n", encoding="utf-8")
    return target
