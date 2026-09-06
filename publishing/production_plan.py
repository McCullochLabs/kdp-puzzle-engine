"""Small, shared helpers for the guided production flow.

These functions intentionally contain no Tkinter or file-writing code.  That
makes the promises shown in the interface easy to test and keeps every entry
point (Guided Builder, Book Studio, and Publishing Center) consistent.
"""
from __future__ import annotations

from math import floor


def content_capacity(unique_words: int, puzzle_count: int, words_per_puzzle: int,
                     target_books: int = 2) -> dict[str, int | bool | str]:
    """Describe repeat-free capacity using plain publishing language."""
    unique_words = max(0, int(unique_words))
    puzzle_count = max(1, int(puzzle_count))
    words_per_puzzle = max(1, int(words_per_puzzle))
    target_books = max(1, int(target_books))
    words_per_book = puzzle_count * words_per_puzzle
    full_books = floor(unique_words / words_per_book)
    target_words = words_per_book * target_books
    missing_for_target = max(0, target_words - unique_words)
    if full_books >= target_books:
        message = f"Ready for {full_books} complete no-repeat books at this size."
    elif full_books >= 1:
        message = (f"Ready for 1 complete no-repeat book; add {missing_for_target} more "
                   f"words to support {target_books} at this size.")
    else:
        message = f"Add {words_per_book - unique_words} more words to make this complete no-repeat book."
    return {
        "unique_words": unique_words,
        "words_per_book": words_per_book,
        "full_books": full_books,
        "target_books": target_books,
        "target_words": target_words,
        "missing_for_target": missing_for_target,
        "one_book_ready": full_books >= 1,
        "target_ready": full_books >= target_books,
        "message": message,
    }


def production_plan_summary(*, title: str, subtitle: str, difficulty: str,
                            puzzle_count: int, words_per_puzzle: int,
                            pages: int, price: float, palette: str, layout: str,
                            folder: str, capacity: dict[str, int | bool | str]) -> str:
    """Return the final, human-readable plan shown before approval."""
    return (
        f"TITLE\n{title}\n\nSUBTITLE\n{subtitle}\n\n"
        f"BOOK DETAILS\n{difficulty} • {puzzle_count} puzzles • {words_per_puzzle} words each • No repeated words\n"
        f"Estimated interior: {pages} pages • Suggested starting price: ${price:.2f}\n\n"
        f"CONTENT GUARANTEE\n{capacity['message']}\n\n"
        f"COVER DIRECTION\n{palette.replace('-', ' ').title()} colors / {layout.replace('-', ' ').title()} layout\n\n"
        f"PACKAGE PLAN\n{folder}\nAmazon KDP files will be created first. Etsy and other marketplace handoffs stay available in Publishing Center when you choose them."
    )
