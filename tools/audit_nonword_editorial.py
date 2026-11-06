"""Read-only editorial triage for the non-word-search books in out/.

Technical preflight is deliberately separate from editorial approval.  This
report inspects the *printed* solution pages, not just current content packs.
"""
from __future__ import annotations

import json
import hashlib
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
MECHANICAL_MARKERS = (
    "CURIOSITY MAKES ", "A CAREFUL LOOK AT ", " CAN OPEN A NEW PATH TO ",
    " IS ONE PART OF A BIGGER STORY", " INVITES PATIENT THINKING",
    " PUZZLE CAN BEGIN WITH ", "CURIOUS MINDS NOTICE ",
    " STORY HAS ROOM FOR ", "THE STORY OF ",
    "CURIOUS MINDS KEEP LOOKING TOWARD ", "A SPACE EXPLORER CAN LEARN FROM ",
)


def _decoded_messages(pages: list[str]) -> list[str]:
    messages: list[str] = []
    for text in pages:
        if "DECODED MESSAGES" not in text:
            continue
        body = text.split("DECODED MESSAGES", 1)[1]
        for piece in re.split(r"(?m)^\s*\d+\.\s*$", body)[1:]:
            lines = [line.strip() for line in piece.splitlines() if line.strip()]
            # The printed footer is a page number, not part of the answer.
            if lines and lines[-1].isdigit():
                lines.pop()
            if lines:
                messages.append(" ".join(lines).upper())
    return messages


def report() -> dict:
    rows = []
    for record_path in sorted(OUT.glob("*/04_REVIEW_AND_RECORDS/PACKAGE_SOURCE_RECORD.json")):
        data = json.loads(record_path.read_text(encoding="utf-8"))
        kind = str(data.get("puzzle_type") or "")
        if kind == "Word Search":
            continue
        folder = record_path.parents[1]
        interior = folder / "01_PRINT_UPLOADS" / "interior.pdf"
        row = {
            "folder": str(folder), "title": data.get("title"), "puzzle_type": kind,
            "promised_puzzles": data.get("puzzle_count"), "topic": data.get("theme"),
            "seed": data.get("puzzle_seed"), "issues": [],
        }
        if not interior.is_file():
            row["issues"].append("Interior PDF is missing.")
            row["status"] = "EDITORIAL HOLD"
            rows.append(row)
            continue
        pages = [(page.extract_text() or "") for page in PdfReader(str(interior)).pages]
        row["interior_sha256"] = hashlib.sha256(interior.read_bytes()).hexdigest()
        row["interior_pages"] = len(pages)
        promised = int(data.get("puzzle_count") or 0)
        if kind == "Sudoku":
            printed = {int(n) for text in pages if "SUDOKU SOLUTIONS" not in text
                       for n in re.findall(r"\bPUZZLE\s+(\d+)\b", text)}
            solutions = {int(n) for text in pages if "SUDOKU SOLUTIONS" in text
                         for n in re.findall(r"\bPUZZLE\s+(\d+)\b", text)}
            row["printed_puzzles"] = len(printed)
            row["printed_solutions"] = len(solutions)
            if kind != "Mixed Brain Games" and (printed != set(range(1, promised + 1)) or solutions != printed):
                row["issues"].append("Printed Sudoku puzzle numbers and solution numbers do not match the promised count.")
        if kind in {"Cryptogram", "Mixed Brain Games"}:
            answers = _decoded_messages(pages)
            mechanical = [answer for answer in answers if any(marker in answer for marker in MECHANICAL_MARKERS)]
            printed = {int(n) for text in pages if "BREAK THE CODE" in text
                       for n in re.findall(r"\bCRYPTOGRAM\s+(\d+)\b", text)}
            row["printed_cryptograms"] = len(printed)
            row["decoded_message_count"] = len(answers)
            row["mechanical_message_count"] = len(mechanical)
            row["mechanical_examples"] = mechanical[:5]
            if mechanical:
                row["issues"].append(
                    f"{len(mechanical)} printed decoded messages use word-substitution templates rather than authored topic content."
                )
            if len(answers) != (int(data.get("puzzle_count") or 0) if kind == "Cryptogram" else 20):
                row["issues"].append("Decoded answer count needs manual reconciliation with the interior.")
            if len(printed) != len(answers):
                row["issues"].append("Printed cryptogram count differs from decoded answer count.")
        if kind == "Sudoku":
            row["symbol_pack"] = data.get("sudoku_symbol_pack")
            row["automated_scope"] = "Source seed and PDF existence checked; exact printed-grid uniqueness and theme art still require proof review."
        if kind in {"Word Scramble + Trivia", "Mixed Brain Games"}:
            printed = {int(n) for text in pages for n in re.findall(r"\b(\d+)\.\s*UNSCRAMBLE:", text)}
            solved = {
                int(n)
                for text in pages if "ANSWER KEY" in text
                for n in re.findall(r"\b(\d+)\.\s+[A-Z][A-Z0-9]+\b", text)
            }
            row["printed_scrambles"] = len(printed)
            row["printed_scramble_answers"] = len(solved)
            expected = promised if kind == "Word Scramble + Trivia" else 20
            if printed != set(range(1, expected + 1)):
                row["issues"].append("Printed scramble numbers do not match the promised section count.")
            if solved != printed:
                row["issues"].append("Printed scramble answer numbers do not match the printed puzzle numbers.")
            row["automated_scope"] = "Question and answer presence checked by technical preflight; independent factual and topic review remains required."
        if kind == "Word Scramble + Trivia":
            combined = "\n".join(pages).casefold()
            title = str(data.get("title") or "").casefold()
            if "american road trip" in title:
                unrelated = [term for term in ("passport", "international", "airline", "airport", "flight", "cruise", "visa")
                             if term in combined]
                if unrelated:
                    row["issues"].append("American road-trip title is narrower than printed international/air-travel content: " +
                                         ", ".join(unrelated) + ". Rework the title or the question pool.")
            if "kitchen table" in title:
                row["review_note"] = "Printed questions include bedroom, closet, and laundry topics; decide whether the broad Food & Home subtitle sufficiently sets expectations."
        row["status"] = "EDITORIAL HOLD" if row["issues"] else "NEEDS HUMAN EDITORIAL SIGN-OFF"
        row["sale_ready"] = False
        rows.append(row)
    return {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "scope": "Active non-word-search books in out/; printed answers and package records",
        "books": rows,
        "editorial_holds": sum(row["status"] == "EDITORIAL HOLD" for row in rows),
        "note": "No book is declared sale-ready by this automated audit. KDP Print Previewer and a physical proof remain required.",
    }


def main() -> None:
    result = report()
    path = ROOT / "reports" / "NONWORD_EDITORIAL_SALE_READINESS.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Non-word books: {len(result['books'])}; editorial holds: {result['editorial_holds']}")
    for row in result["books"]:
        print(f"{row['status']}: {row['title']} | " + "; ".join(row["issues"]))
    print(path)


if __name__ == "__main__":
    main()
