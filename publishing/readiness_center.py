"""One shared, read-only production readiness summary for the Publishing Manager."""
from __future__ import annotations

from .marketplaces import PUBLISHERS


def production_readiness(books: list[dict]) -> dict:
    """Classify catalog books into plain-English next steps without writing files."""
    rows: list[dict] = []
    counts = {"ready": 0, "needs_package": 0, "needs_review": 0, "published": 0}
    for book in books:
        metadata = book.get("metadata") or {}
        title = str(metadata.get("title") or "Untitled book")
        statuses = book.get("statuses") or {}
        state = "Needs review"
        detail = "Review the book details and package files."
        if any(status == "Published" for status in statuses.values()):
            state, detail = "Published", "A marketplace already has a confirmed live listing."
        else:
            issues = PUBLISHERS["amazon"].blocking_issues(PUBLISHERS["amazon"].validate(book))
            if not issues:
                state, detail = "Ready for KDP handoff", "Interior and print cover are present. Run KDP Print Previewer after preparing."
            elif not book.get("package_path"):
                state, detail = "Needs package", "Create the complete package first; it supplies the interior and full print cover."
            else:
                state, detail = "Needs review", " ".join(issues)
        key = {"Ready for KDP handoff": "ready", "Needs package": "needs_package", "Needs review": "needs_review", "Published": "published"}[state]
        counts[key] += 1
        rows.append({"book_id": book.get("book_id", ""), "title": title, "state": state, "detail": detail})
    priority = {"Needs review": 0, "Needs package": 1, "Ready for KDP handoff": 2, "Published": 3}
    rows.sort(key=lambda row: (priority[row["state"]], row["title"].casefold()))
    return {"counts": counts, "rows": rows, "total": len(rows)}


def readiness_text(summary: dict) -> str:
    counts = summary["counts"]
    lines = [
        f"{summary['total']} catalog book(s)",
        f"• {counts['ready']} ready for a KDP handoff",
        f"• {counts['needs_package']} need a complete package",
        f"• {counts['needs_review']} need review",
        f"• {counts['published']} already have a confirmed published marketplace record",
    ]
    return "\n".join(lines)
