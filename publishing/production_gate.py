"""One truthful production gate shared by the Publishing Center screens."""
from __future__ import annotations

import json
from pathlib import Path

from .content_capacity import blueprint, topic_capacity
from .word_capacity_plan import required_words
from .review import review_result


def _read_source(book: dict) -> dict:
    try:
        return json.loads(Path(str(book.get("source_key") or "")).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def book_gate(book: dict) -> dict:
    """Return a small, UI-ready source/package/proof status without writing."""
    meta = book.get("metadata") or {}
    source = _read_source(book)
    blockers: list[str] = []
    notes: list[str] = []
    title = str(meta.get("title") or source.get("title") or "").strip()
    author = str(meta.get("author") or source.get("author") or "").strip()
    puzzles = source.get("puzzles") if isinstance(source.get("puzzles"), list) else []
    quality_review = source.get("quality_review")
    if isinstance(quality_review, dict) and quality_review.get("production_ready") is False:
        blockers.append(str(quality_review.get("editorial_hold_reason") or
                            "This theme's verified word-quality review needs a curated topic rebuild before production."))
    if not title:
        blockers.append("Add a book title.")
    if not author:
        blockers.append("Add an author or pen name.")
    if source and len(puzzles) < 1:
        blockers.append("This source has no puzzles yet.")
    if puzzles:
        empty = sum(1 for item in puzzles if not isinstance(item, dict) or not item.get("words"))
        if empty:
            blockers.append(f"{empty} puzzle(s) have no words.")
        words = [str(word).strip().upper() for item in puzzles if isinstance(item, dict) for word in item.get("words", []) if str(word).strip()]
        # Older imported themes did not declare the no-repeat promise.  Do not
        # retroactively block those records here; new automatic blueprints do.
        from .repetition_policy import requested as repetition_requested, evaluate as evaluate_repetition
        if repetition_requested(source):
            blockers.extend(evaluate_repetition(source)["errors"])
        elif source.get("no_repeat_words") is True and words and len(words) != len(set(words)):
            blockers.append("This source repeats words; rebuild it before automatic packaging.")
    if source and str(meta.get("production_status") or "") not in {"Passed", "Complete package"}:
        notes.append("Run the book-quality check before final packaging; this keeps old or changed sources from slipping through.")
    package = bool(book.get("package_path"))
    proof = review_result(book, "amazon") if package else None
    if proof and not proof["ready"]:
        blockers.extend(proof["blockers"])
    stage = "Ready to prepare" if proof and proof["ready"] else "Ready to create package" if not blockers else "Needs attention"
    return {"ready": not blockers, "stage": stage, "blockers": list(dict.fromkeys(blockers)), "notes": notes, "has_package": package, "proof": proof}


def topic_gate(project: Path, topic: str) -> dict:
    """Capacity-backed gate for a new automatic Word Search blueprint."""
    row = next((row for row in topic_capacity(Path(project)) if row["topic"] == topic), None)
    plan = blueprint(topic, "Word Search")
    needed = int(plan["puzzle_count"]) * 12
    words = int((row or {}).get("words") or 0)
    can_build = words >= needed
    two_book_ready = words >= needed * 2
    portfolio_needed = required_words()
    portfolio_ready = words >= portfolio_needed
    return {"topic": topic, "plan": plan, "words": words, "needed": needed, "ready": can_build,
            "two_book_ready": two_book_ready, "portfolio_needed": portfolio_needed,
            "portfolio_ready": portfolio_ready, "portfolio_gap": max(0, portfolio_needed - words),
            "message": ("Ready for two standard books plus a 100-puzzle Signature Edition." if portfolio_ready else
                        "Ready for two standard books; expand it before promising a Signature Edition." if two_book_ready else
                        "Ready for one repeat-free 48-puzzle Word Search; expand it before scheduling a second." if can_build else
                        f"Needs {needed - words} more topic-linked words before a repeat-free 48-puzzle book.")}


def gate_text(gate: dict) -> str:
    lines = [f"PRODUCTION GATE — {gate['stage']}"]
    if gate["blockers"]:
        lines += ["", "FIX BEFORE CONTINUING"] + [f"• {item}" for item in gate["blockers"]]
    else:
        lines += ["", "• Source details are complete and no known hard stop was found."]
    if gate["notes"]:
        lines += ["", "REVIEW NOTES"] + [f"• {item}" for item in gate["notes"]]
    return "\n".join(lines)


def production_proof_gate(project: Path, plan, package: Path, **kwargs) -> dict:
    """Phase 4 additive unified proof entry point; legacy gates remain intact."""
    from .production_proof import build_production_proof
    return build_production_proof(project, plan, package, **kwargs).to_dict()
