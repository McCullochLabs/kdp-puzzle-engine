"""Shared, explainable ranking for the next production decision."""
from __future__ import annotations

from pathlib import Path

from .metadata_service import marketplace_copy_quality
from .production_gate import book_gate


def production_candidates(service, limit: int = 12) -> list[dict]:
    """Rank only locally ready catalog records; never imply demand or sales."""
    rows: list[dict] = []
    for book in service.db.list_books():
        meta = book.get("metadata") or {}
        gate = book_gate(book)
        if not gate.get("ready"):
            continue
        files = meta.get("files") if isinstance(meta.get("files"), dict) else {}
        has_package = bool(files.get("print_interior") and files.get("print_cover") and Path(str(files["print_interior"])).is_file() and Path(str(files["print_cover"])).is_file())
        audits = [marketplace_copy_quality(meta, platform) for platform in ("amazon", "etsy", "ingram")]
        copy_score = round(sum(item["score"] for item in audits) / len(audits))
        puzzles = int(meta.get("puzzle_count") or 0)
        score = 35 + min(25, puzzles // 4) + round(copy_score * .25)
        if has_package:
            score += 15
        if meta.get("series"):
            score += 5
        cover_ok = bool(files.get("front_cover"))
        if cover_ok:
            score += 5
        reason = ["passes the shared production gate", f"{copy_score}/100 marketplace-copy quality"]
        if has_package: reason.append("package files present")
        else: reason.append("ready to build")
        if meta.get("series"): reason.append("series connection")
        rows.append({"book": book, "score": score, "copy_score": copy_score, "has_package": has_package, "cover_ok": cover_ok, "reason": " • ".join(reason), "action": "Prepare marketplace handoffs" if has_package else "Create complete package"})
    return sorted(rows, key=lambda item: (-item["score"], str(item["book"]["metadata"].get("title") or "")))[:limit]


def production_attention(service, limit: int = 12) -> list[dict]:
    """Return the clearest local blockers first, never a marketplace claim."""
    rows: list[dict] = []
    for book in service.db.list_books():
        gate = book_gate(book)
        if gate.get("ready"):
            continue
        metadata = book.get("metadata") or {}
        blockers = [str(item) for item in gate.get("blockers") or []]
        if not blockers:
            blockers = ["This saved record needs a local review before it can be built."]
        rows.append({
            "book": book,
            "issue": blockers[0],
            "count": len(blockers),
            "next": "Open the book details and follow the listed fix.",
            "sort": (len(blockers), str(metadata.get("title") or "")),
        })
    return sorted(rows, key=lambda item: item["sort"])[:limit]
