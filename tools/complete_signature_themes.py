"""Safely complete buyer-facing Signature Edition source themes to 100 puzzles.

It intentionally leaves standard books that only carry old Signature design
notes alone.  Only themes that say "Signature" in their title/file name and
already have a matching Master Library topic are completed.
"""
from __future__ import annotations

import json
import re
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
THEMES = PROJECT / "themes"
MASTER = PROJECT / "word_banks" / "Guided_Builder_Master_Word_Bank.json"
TARGET = 100


def key(value: object) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value).upper())


def buyer_facing_signature(path: Path, data: dict) -> bool:
    edition = data.get("signature_edition")
    wording = f"{path.stem} {data.get('title', '')} {data.get('subtitle', '')}".casefold()
    return isinstance(edition, dict) and bool(edition.get("enabled")) and "signature" in wording


def complete(path: Path, topics: dict) -> int:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not buyer_facing_signature(path, data):
        return 0
    puzzles = data.get("puzzles") if isinstance(data.get("puzzles"), list) else []
    topic = str(data.get("detected_topic") or "")
    pool = topics.get(topic)
    if not isinstance(pool, list):
        raise ValueError(f"{path.name}: no exact Master Library topic for '{topic}'.")
    # Keep the first valid occurrence of each 12-word puzzle.  This also
    # repairs an interrupted/older completion attempt without changing any
    # original, unique source puzzle.
    retained = []
    used: set[str] = set()
    for puzzle in puzzles:
        words = puzzle.get("words") if isinstance(puzzle, dict) else None
        keys = [key(word) for word in words] if isinstance(words, list) else []
        if len(words or []) == 12 and all(keys) and not (set(keys) & used):
            retained.append(puzzle)
            used.update(keys)
    puzzles = retained
    available = []
    for word in pool:
        clean = key(word)
        if clean and clean not in used:
            used.add(clean)
            available.append(str(word))
    needed = (TARGET - len(puzzles)) * 12
    if len(available) < needed:
        edition = data.get("signature_edition") if isinstance(data.get("signature_edition"), dict) else {}
        data["signature_edition"] = {**edition, "enabled": False, "candidate": True,
                                     "reason": f"Needs {needed - len(available)} more topic-linked words before it can be a 100-puzzle Signature Edition."}
        data["production_status"] = "Signature candidate — expand word bank before publishing"
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"CANDIDATE: {path.name}: needs {needed} linked words, only {len(available)} are unused.")
        return 0
    prefix = re.sub(r"\s+", " ", str(data.get("title") or "Signature Collection").replace("Signature Edition", "").strip())
    starting_count = len(puzzles)
    for offset, index in enumerate(range(starting_count, TARGET)):
        start = offset * 12
        puzzles.append({"name": f"{prefix} {index + 1}", "words": available[start:start + 12]})
    data["puzzles"] = puzzles
    data["no_repeat_words"] = True
    data["signature_edition"] = {**data.get("signature_edition", {}), "enabled": True, "puzzle_target": TARGET}
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return TARGET


def main() -> int:
    bank = json.loads(MASTER.read_text(encoding="utf-8-sig"))
    topics = bank.get("topics") if isinstance(bank.get("topics"), dict) else {}
    changed = []
    for path in sorted(THEMES.rglob("*.json")):
        try:
            if complete(path, topics):
                changed.append(path.relative_to(PROJECT))
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            print(f"SKIPPED: {exc}")
    for path in changed:
        print(f"COMPLETED: {path}")
    print(f"Completed {len(changed)} Signature Edition theme(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
