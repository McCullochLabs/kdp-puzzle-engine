"""Small, shared decisions for the calm, one-workflow production surface.

This module never writes catalog data or bypasses a quality gate.  It only
turns the existing publishing records into a short, plain-English next step.
Keeping it independent from Tkinter makes it easy to test with large catalog
fixtures and prevents the home screen from becoming another source of truth.
"""
from __future__ import annotations

from typing import Any

from .production_gate import book_gate


VISIBLE_STATUSES = (
    "Draft", "Creating", "Needs Attention", "Needs Review", "Approved",
    "Ready to Publish", "Published", "Completed", "Blocked",
)


def book_stage(book: dict[str, Any]) -> str:
    """Return one stable, user-facing stage from the existing book record."""
    statuses = {str(value) for value in (book.get("statuses") or {}).values()}
    if "Published" in statuses:
        return "Published"
    if "Uploaded" in statuses:
        return "Ready to Publish"
    package_path = str(book.get("package_path") or "")
    if package_path:
        try:
            gate = book_gate(book)
        except (KeyError, TypeError, ValueError):
            gate = {"ready": False}
        if gate.get("ready"):
            return "Approved" if "Ready" not in statuses else "Ready to Publish"
        return "Needs Attention"
    production = str((book.get("metadata") or {}).get("production_status") or "").casefold()
    if production in {"passed", "passed with notes"}:
        return "Needs Review"
    if production in {"complete package", "ready"}:
        return "Needs Review"
    return "Needs Attention"


def next_action(books: list[dict[str, Any]]) -> dict[str, Any]:
    """Choose exactly one honest next action from actual catalog state."""
    if not books:
        return {
            "kind": "create", "book_id": "", "label": "Create your first book",
            "detail": "Choose a book type and topic. The studio will apply its checked defaults.",
        }
    staged = [(book_stage(book), book) for book in books]
    for target, kind, label, detail in (
        ("Needs Attention", "review", "Fix the next book that needs attention", "Review the one item blocking a complete package."),
        ("Needs Review", "review", "Review the next planned book", "Confirm the plan and let the usual quality checks run."),
        ("Approved", "publish", "Prepare the next approved book", "Its package is ready for a marketplace handoff."),
        ("Ready to Publish", "publish", "Review the next marketplace handoff", "The local files are ready; uploading remains your decision."),
    ):
        match = next((book for stage, book in staged if stage == target), None)
        if match:
            return {"kind": kind, "book_id": str(match.get("book_id") or ""), "label": label, "detail": detail}
    return {
        "kind": "create", "book_id": "", "label": "Create another book",
        "detail": "Your active catalog is clear. Start from a checked topic and the studio will apply the best defaults.",
    }


def home_summary(books: list[dict[str, Any]]) -> dict[str, Any]:
    """Return a compact status tally plus the one recommended action."""
    counts = {status: 0 for status in VISIBLE_STATUSES}
    for book in books:
        counts[book_stage(book)] = counts.get(book_stage(book), 0) + 1
    return {"counts": counts, "next": next_action(books)}
