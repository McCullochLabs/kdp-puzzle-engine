"""Shared visual directions for every puzzle creator.

These presets are intentionally small, named in plain English, and safe for
black-and-white interiors.  A creator can use them without needing separate
theme files or a manual design decision for every book.
"""
from __future__ import annotations

INTERIOR_PRESETS = {
    "Studio Classic": {"header": "clean uppercase headers", "accent": (0.10, 0.10, 0.10), "divider": "simple line", "answer_key": "clear numbered key"},
    "Calm Modern": {"header": "quiet modern headers", "accent": (0.12, 0.28, 0.33), "divider": "soft rule", "answer_key": "spacious answer key"},
    "Playful Learning": {"header": "friendly bold headers", "accent": (0.20, 0.38, 0.58), "divider": "rounded badge", "answer_key": "easy-scan answer key"},
    "Signature Collection": {"header": "premium collection headers", "accent": (0.31, 0.20, 0.08), "divider": "double rule", "answer_key": "premium answer key"},
}

BONUS_PAGE_OPTIONS = (
    "Completion certificate",
    "Puzzle progress tracker",
    "About this topic facts",
    "Extra challenge page",
    "Next-book preview",
)

def preset(name: str | None) -> dict:
    return INTERIOR_PRESETS.get(str(name or ""), INTERIOR_PRESETS["Studio Classic"])

def default_preset(kind: str, signature: bool = False) -> str:
    if signature: return "Signature Collection"
    return "Playful Learning" if kind in {"Word Scramble + Trivia", "Mixed Brain Games"} else "Calm Modern"

def automatic_bonus_pages(kind: str, topic: str, signature: bool = False) -> list[str]:
    """Choose useful extras from the existing bonus set, without new UI work."""
    low = str(topic or "").casefold()
    selected = ["Completion certificate", "Puzzle progress tracker"]
    if signature or any(word in low for word in ("history", "space", "nature", "garden", "travel", "bible", "school")):
        selected.append("About this topic facts")
    if kind in {"Sudoku", "Cryptogram", "Mixed Brain Games"}:
        selected.append("Extra challenge page")
    if kind in {"Word Scramble + Trivia", "Mixed Brain Games"} or signature:
        selected.append("Next-book preview")
    return [item for item in BONUS_PAGE_OPTIONS if item in selected]

def bonus_page_titles(selected: list[str] | tuple[str, ...] | None, topic: str) -> list[str]:
    names = [item for item in (selected or []) if item in BONUS_PAGE_OPTIONS]
    topic = str(topic or "this topic").upper()
    mapping = {
        "Completion certificate": "COMPLETION CERTIFICATE",
        "Puzzle progress tracker": "MY PUZZLE PROGRESS",
        "About this topic facts": f"ABOUT {topic}",
        "Extra challenge page": "BONUS CHALLENGE",
        "Next-book preview": "MORE PUZZLES TO EXPLORE",
    }
    return [mapping[item] for item in names]
