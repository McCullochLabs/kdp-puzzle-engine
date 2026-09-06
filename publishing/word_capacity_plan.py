"""Truthful production-capacity planning for repeat-free Word Search series."""
from __future__ import annotations

import hashlib
import re
from typing import Iterable


STANDARD_PUZZLES = 48
SIGNATURE_PUZZLES = 100
DEFAULT_WORDS_PER_PUZZLE = 12
STANDARD_BOOK_COUNT = 2


def normalize(word: object) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(word).upper())


def unique_words(words: Iterable[object]) -> list[str]:
    """Return stable, display-friendly unique entries by normalized spelling."""
    seen: set[str] = set()
    result: list[str] = []
    for raw in words:
        display = " ".join(str(raw).upper().split())
        key = normalize(display)
        if key and key not in seen:
            seen.add(key)
            result.append(display)
    return result


def required_words(words_per_puzzle: int = DEFAULT_WORDS_PER_PUZZLE) -> int:
    words_per_puzzle = max(1, int(words_per_puzzle))
    return (STANDARD_BOOK_COUNT * STANDARD_PUZZLES + SIGNATURE_PUZZLES) * words_per_puzzle


def build_plan(topic: str, words: Iterable[object], words_per_puzzle: int = DEFAULT_WORDS_PER_PUZZLE) -> dict:
    """Allocate stable, non-overlapping pools for two standard books and one Signature Edition.

    The returned word lists make the promise inspectable.  A caller can use a
    named allocation directly instead of choosing from a shared pool and
    discovering a collision only after a book has been produced.
    """
    words_per_puzzle = max(1, int(words_per_puzzle))
    cleaned = unique_words(words)
    # A deterministic topic-specific order avoids repeatedly giving every
    # topic the same alphabetic first slice while keeping regeneration stable.
    salt = str(topic).casefold().encode("utf-8")
    ordered = sorted(cleaned, key=lambda item: hashlib.sha256(salt + b"|" + normalize(item).encode("utf-8")).hexdigest())
    standard_size = STANDARD_PUZZLES * words_per_puzzle
    signature_size = SIGNATURE_PUZZLES * words_per_puzzle
    first = ordered[:standard_size]
    second = ordered[standard_size:standard_size * 2]
    signature = ordered[standard_size * 2:standard_size * 2 + signature_size]
    reserve = ordered[standard_size * 2 + signature_size:]
    needed = required_words(words_per_puzzle)
    return {
        "topic": str(topic),
        "words_per_puzzle": words_per_puzzle,
        "required_words": needed,
        "available_words": len(ordered),
        "gap": max(0, needed - len(ordered)),
        "portfolio_ready": len(ordered) >= needed,
        "standard_book_ready": len(first) == standard_size,
        "second_standard_book_ready": len(second) == standard_size,
        "signature_ready": len(signature) == signature_size,
        "allocations": {
            "standard_book_1": first,
            "standard_book_2": second,
            "signature_edition": signature,
            "future_reserve": reserve,
        },
    }

