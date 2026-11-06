"""Explicit collection exception; never converts a no-repeat promise into a pass.

Authorized by the operator on 2026-10-08 following the older-adult production
audit. This is a vocabulary check, not topic, editorial, cover or release approval.
The limits are code-owned so a theme cannot lower them to pass production.
"""
from itertools import combinations
import re

POLICY_ID = "older_adult_memories_v1"
BOOK_IDS = frozenset({"growing_up_50s_60s", "kitchen_table_memories", "summer_days_remembered"})


def requested(data: dict) -> bool:
    return "repetition_policy" in data


def normalize(value: object) -> str:
    return re.sub(r"[^A-Z]", "", str(value or "").upper())


def evaluate(data: dict) -> dict:
    """Return measured evidence and fail closed for unknown/malformed policies."""
    errors = []
    policy = data.get("repetition_policy")
    if not isinstance(policy, dict) or policy != {"id": POLICY_ID}:
        errors.append("Unknown or modified repetition policy; use the approved collection policy unchanged.")
    if data.get("collection_id") != POLICY_ID or data.get("collection_book_id") not in BOOK_IDS:
        errors.append("Controlled repetition is authorized only for the three older-adult collection books.")
    if data.get("no_repeat_words") is not False:
        errors.append("Controlled repetition requires no_repeat_words=false; it cannot carry a no-repeat promise.")
    claim_text = " ".join(str(data.get(key) or "") for key in
                          ("title", "subtitle", "cover_badge", "badge", "description", "back_blurb"))
    if re.search(r"\bno[ -]+repeat|\brepeat[ -]+free|\bwithout repeat", claim_text, re.I):
        errors.append("Remove the no-repeat claim from this controlled-repetition book.")
    puzzles = data.get("puzzles")
    if not isinstance(puzzles, list):
        puzzles = []
    if len(puzzles) != 80:
        errors.append("The approved collection format requires exactly 80 puzzles.")
    groups, locations, names, prompts = [], {}, [], []
    for number, puzzle in enumerate(puzzles, 1):
        if not isinstance(puzzle, dict) or not isinstance(puzzle.get("words"), list):
            errors.append(f"Puzzle {number}: malformed word list.")
            continue
        raw = puzzle["words"]
        words = [normalize(word) for word in raw]
        if len(words) != 12:
            errors.append(f"Puzzle {number}: this production format requires 12 words.")
        if any(not isinstance(word, str) or not clean for word, clean in zip(raw, words)):
            errors.append(f"Puzzle {number}: blank or malformed target.")
        if len(words) != len(set(words)):
            errors.append(f"Puzzle {number}: duplicate targets after normalization.")
        groups.append((number, set(words)))
        for word in words:
            locations.setdefault(word, []).append(number)
        names.append(" ".join(str(puzzle.get("name") or "").casefold().split()))
        prompt = " ".join(str(puzzle.get("reflection_prompt") or "").casefold().split())
        if prompt:
            prompts.append(prompt)
    if len(names) != len(set(names)):
        errors.append("Puzzle topics must have distinct names.")
    if len(prompts) != len(set(prompts)):
        errors.append("Reflection prompts must not repeat.")
    total = sum(len(numbers) for numbers in locations.values())
    unique = len(locations)
    ratio = unique / total if total else 0.0
    if unique * 4 < total * 3 or not total:
        errors.append(f"Vocabulary variety is {ratio:.1%}; at least 75% of targets must be unique.")
    excessive = {word: numbers for word, numbers in locations.items() if len(numbers) > 3}
    if excessive:
        errors.append("Targets may appear at most three times: " + ", ".join(sorted(excessive)[:12]) + ".")
    overlaps = []
    for (left, a), (right, b) in combinations(groups, 2):
        shared = a & b
        if shared and len(shared) * 2 > min(len(a), len(b)):
            overlaps.append({"puzzles": [left, right], "shared_words": sorted(shared)})
    if overlaps:
        errors.append(f"{len(overlaps)} puzzle pair(s) share more than half their targets.")
    return {"policy_id": POLICY_ID, "passed": not errors, "errors": errors,
            "total_targets": total, "unique_targets": unique, "unique_fraction": ratio,
            "reused_words": {word: numbers for word, numbers in sorted(locations.items()) if len(numbers) > 1},
            "excessive_occurrences": excessive, "near_duplicate_groups": overlaps,
            "scope": "Vocabulary only; topic relevance and human review remain required."}
