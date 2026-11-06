"""One non-destructive read model for the Publishing Center catalog.

The SQLite catalog deliberately retains theme ideas, historical source aliases,
and completed packages.  Operators should not have to understand that storage
model.  This module collapses records that point to the same buyer-facing book
and gives every visible row one truthful kind, status, and next action.

Nothing here writes to the database or removes a source/package file.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

from .package_layout import missing_core_package_files


CATALOG_VIEWS = ("Completed books", "Book ideas", "Needs attention", "All records")

_STATUS_RANK = {
    "Published": 6,
    "Uploaded": 5,
    "Ready": 4,
    "Prepared — Final Cover Needed": 3,
    "Needs Review": 2,
    "Error": 1,
    "Not Prepared": 0,
}


def _clean(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def _package_identity(raw: object) -> str:
    value = str(raw or "").strip()
    if not value:
        return ""
    try:
        return str(Path(value).resolve()).casefold()
    except OSError:
        return value.casefold()


def _idea_identity(book: dict[str, Any]) -> str:
    meta = book.get("metadata") or {}
    fields = tuple(_clean(meta.get(field)) for field in ("title", "subtitle", "author"))
    # An untitled draft is not a buyer-facing identity: otherwise many
    # unrelated drafts with the same default author/subtitle collapse.
    if fields[0]:
        return "|".join(fields)
    return _clean(book.get("source_key")) or str(book.get("book_id") or "")


def _canonical_score(book: dict[str, Any]) -> tuple[int, int, int, str]:
    statuses = book.get("statuses") or {}
    marketplace_progress = max((_STATUS_RANK.get(str(value), 0) for value in statuses.values()), default=0)
    source = Path(str(book.get("source_key") or ""))
    return (
        marketplace_progress,
        int(bool(book.get("metadata_locked"))),
        int(source.is_file()),
        str(book.get("updated_at") or ""),
    )


def record_kind(book: dict[str, Any]) -> str:
    """Return a stable machine-readable record kind."""
    package_value = str(book.get("package_path") or "").strip()
    if package_value:
        package = Path(package_value)
        if not package.is_dir():
            return "missing_package"
        return "book_package" if not missing_core_package_files(package) else "book_in_progress"
    source_value = str(book.get("source_key") or "").strip()
    if source_value and not source_value.startswith("package:") and not Path(source_value).is_file():
        return "missing_source"
    production = str((book.get("metadata") or {}).get("production_status") or "").casefold()
    if production in {"passed", "passed with notes", "ready"}:
        return "ready_book_idea"
    if production == "blocked":
        return "blocked_book_idea"
    return "theme_idea"


def record_kind_label(kind: str) -> str:
    return {
        "book_package": "Book package",
        "book_in_progress": "Incomplete package",
        "missing_package": "Missing package",
        "missing_source": "Missing source",
        "ready_book_idea": "Ready book idea",
        "blocked_book_idea": "Blocked idea",
        "theme_idea": "Theme / idea",
    }.get(kind, "Catalog record")


def collapse_catalog_books(books: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse package aliases and exact buyer-identity idea duplicates.

    The chosen canonical record is the one with the strongest marketplace
    progress, then a metadata lock, a live source, and the newest timestamp.
    Alias ids stay attached for audit/display purposes.
    """
    groups: dict[str, list[dict[str, Any]]] = {}
    for book in books:
        package = _package_identity(book.get("package_path"))
        key = f"package:{package}" if package else f"idea:{_idea_identity(book)}"
        groups.setdefault(key, []).append(book)
    result: list[dict[str, Any]] = []
    for key, candidates in groups.items():
        canonical = max(candidates, key=_canonical_score)
        visible = dict(canonical)
        visible["metadata"] = dict(canonical.get("metadata") or {})
        visible["statuses"] = dict(canonical.get("statuses") or {})
        visible["catalog_alias_ids"] = tuple(
            str(item.get("book_id") or "") for item in candidates
            if item.get("book_id") != canonical.get("book_id")
        )
        visible["catalog_alias_count"] = len(candidates) - 1
        visible["catalog_group_key"] = key
        visible["catalog_kind"] = record_kind(visible)
        result.append(visible)
    return sorted(result, key=lambda book: str((book.get("metadata") or {}).get("title") or "").casefold())


def catalog_state(book: dict[str, Any], gate: dict[str, Any] | None = None,
                  final_review: bool = False, contract_ready: bool | None = None) -> dict[str, str]:
    """Return exactly one operator status and next action for a visible row."""
    statuses = {str(value) for value in (book.get("statuses") or {}).values()}
    kind = str(book.get("catalog_kind") or record_kind(book))
    if kind == "missing_package" and "Published" in statuses:
        return {"status": "Live listing — files missing", "next_action": "Restore the local book package"}
    if kind == "book_in_progress" and "Published" in statuses:
        return {"status": "Live listing — files incomplete", "next_action": "Restore the missing book files"}
    if "Published" in statuses:
        return {"status": "Published", "next_action": "Open or verify the live listing"}
    if "Uploaded" in statuses:
        return {"status": "Uploaded — verify live", "next_action": "Confirm the marketplace listing"}
    if kind == "missing_package":
        return {"status": "Missing package", "next_action": "Locate or safely rebuild the package"}
    if kind == "missing_source":
        return {"status": "Missing source", "next_action": "Locate the theme source or review its history"}
    if kind == "book_in_progress":
        return {"status": "Incomplete package", "next_action": "Review the missing book files"}
    if kind == "book_package":
        if gate is not None and not gate.get("ready"):
            return {"status": "Needs attention", "next_action": "Fix the reported production issue"}
        if contract_ready is False:
            return {"status": "Needs attention", "next_action": "Fix the package or cover proof"}
        if not final_review:
            return {"status": "Needs final proof", "next_action": "Review and approve the exact files"}
        if "Ready" in statuses:
            return {"status": "Ready to publish", "next_action": "Open the prepared marketplace handoff"}
        return {"status": "Approved", "next_action": "Prepare the chosen marketplace"}
    production = str((book.get("metadata") or {}).get("production_status") or "").casefold()
    if gate is not None and not gate.get("ready"):
        return {"status": "Needs content", "next_action": "Fix the reviewed content gap"}
    if kind == "ready_book_idea":
        return {"status": "Ready to create", "next_action": "Review the plan and create the book"}
    if kind == "blocked_book_idea" or production == "blocked":
        return {"status": "Needs content", "next_action": "Fix the reviewed content gap"}
    if production in {"needs content check", ""}:
        return {"status": "Needs content check", "next_action": "Run the book-readiness check"}
    return {"status": "Needs review", "next_action": "Review the source and book plan"}


def in_catalog_view(book: dict[str, Any], view: str, state: dict[str, str] | None = None) -> bool:
    kind = str(book.get("catalog_kind") or record_kind(book))
    if view == "Completed books":
        return kind == "book_package"
    if view == "Book ideas":
        return kind in {"ready_book_idea", "blocked_book_idea", "theme_idea"}
    if view == "Needs attention":
        status = (state or catalog_state(book))["status"]
        return status in {
            "Missing package", "Missing source", "Incomplete package", "Live listing — files missing",
            "Live listing — files incomplete", "Needs attention", "Needs final proof", "Needs content",
            "Needs content check", "Needs review", "Uploaded — verify live",
        }
    return True


def catalog_counts(books: Iterable[dict[str, Any]]) -> dict[str, int]:
    rows = list(books)
    return {
        "records": len(rows),
        "packages": sum(record_kind(row) == "book_package" for row in rows),
        "in_progress": sum(record_kind(row) == "book_in_progress" for row in rows),
        "ideas": sum(record_kind(row) in {"ready_book_idea", "blocked_book_idea", "theme_idea"} for row in rows),
        "missing": sum(record_kind(row) in {"missing_package", "missing_source"} for row in rows),
        "aliases_hidden": sum(int(row.get("catalog_alias_count") or 0) for row in rows),
    }
