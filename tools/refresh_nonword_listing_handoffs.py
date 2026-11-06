"""Refresh active non-word listing metadata through the safe local writer.

This migration is deliberately deterministic. It replaces weak legacy AI
keywords and marketplace descriptions without changing titles, subtitles,
contributors, interiors, covers, or explicitly human-locked fields.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from publishing import PublishingService
from publishing.database import MARKETPLACES
from publishing.listing_intelligence import (
    apply_listing_intelligence,
    local_fallback_content,
    verified_facts,
)
from publishing.listing_copy import recommended_prices


def main() -> int:
    service = PublishingService(ROOT)
    service.sync_output_packages()
    active = []
    for book in service.db.list_books():
        package = Path(str(book.get("package_path") or ""))
        if not package.is_dir() or package.parent.resolve() != (ROOT / "out").resolve():
            continue
        if str(book.get("metadata", {}).get("puzzle_type") or "") == "Word Search":
            continue
        active.append(book)

    rows = []
    for book in active:
        metadata = dict(book.get("metadata") or {})
        changed = []
        for marketplace in MARKETPLACES:
            working = {**book, "metadata": metadata}
            facts = verified_facts(working, marketplace)
            content = local_fallback_content(working, facts)
            record = {
                "provider": "Deterministic local listing",
                "platform": marketplace,
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "validation": "local commercial-readiness refresh",
                "content": content,
                "critic_notes": [
                    "Refreshed from verified package facts; contributor names and unrelated puzzle types are excluded from discovery phrases."
                ],
            }
            metadata, fields = apply_listing_intelligence(metadata, record)
            changed.extend(fields)
        metadata["price"] = recommended_prices(metadata)
        service.db.save_metadata(book["book_id"], metadata)
        rows.append({
            "book_id": book["book_id"],
            "title": metadata.get("title"),
            "changed_fields": sorted(set(changed)),
        })

    results = service.prepare_many(
        [book["book_id"] for book in active],
        list(MARKETPLACES),
    )
    by_book = {row["book_id"]: row for row in rows}
    for book_id, marketplace, status in results:
        by_book[book_id].setdefault("marketplaces", {})[marketplace] = status

    target = ROOT / "reports" / "NONWORD_LISTING_HANDOFF_REFRESH.json"
    target.write_text(json.dumps({
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "books": rows,
    }, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "books": len(rows),
        "marketplace_results": len(results),
        "errors": [item for item in results if str(item[2]).startswith("Error")],
        "report": str(target),
    }, indent=2))
    return 0 if not any(str(item[2]).startswith("Error") for item in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
