"""Audit and refresh buyer-facing publication information for active books.

Interiors and covers are never changed here. The tool refreshes only canonical
catalog metadata, copy-ready listing documents, marketplace handoffs, and one
central before/after audit report.
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
from publishing.listing_copy import kdp_us_large_trim_estimate, listing_copy_text, recommended_prices
from publishing.metadata_service import marketplace_content, marketplace_copy_quality
from publishing.package_layout import package_file


AUTOMATED_FIELDS = {
    "description", "platform_descriptions", "amazon_keywords", "etsy_tags",
    "website_tags", "ingram_subjects", "categories", "barnes_noble_metadata",
    "amazon_category_directions", "primary_audience", "reading_age",
    "short_description", "marketplace_copy_source", "resolved_topic",
}


def _human_fields(meta: dict) -> set[str]:
    owners = meta.get("listing_field_ownership") if isinstance(meta.get("listing_field_ownership"), dict) else {}
    explicit = meta.get("human_edited_listing_fields") if isinstance(meta.get("human_edited_listing_fields"), list) else []
    return {str(name) for name in explicit} | {str(name) for name, owner in owners.items() if str(owner).casefold() in {"human", "locked", "manual"}}


def _record(folder: Path) -> dict:
    path = package_file(folder, "PACKAGE_SOURCE_RECORD.json")
    return json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else {}


def _refresh_meta(meta: dict, record: dict) -> tuple[dict, list[str]]:
    human = _human_fields(meta)
    seed = {**record, **meta}
    for field in AUTOMATED_FIELDS - human:
        seed.pop(field, None)
    generated = marketplace_content(seed)
    refreshed = dict(meta)
    for field, value in generated.items():
        if field not in human:
            refreshed[field] = value
    if "theme" not in human:
        refreshed["theme"] = generated["resolved_topic"]
    refreshed["categories"] = list(generated["ingram_subjects"])
    refreshed["price"] = recommended_prices(refreshed)
    refreshed["publication_information_reviewed_at"] = datetime.now().isoformat(timespec="seconds")
    refreshed["publication_information_basis"] = "KDP/Etsy/BISAC guidance and comparable pricing reviewed 2026-09-20"
    return refreshed, sorted(human & AUTOMATED_FIELDS)


def main() -> int:
    service = PublishingService(ROOT)
    service.sync_output_packages()
    by_folder: dict[Path, list[dict]] = {}
    for book in service.db.list_books():
        folder = Path(str(book.get("package_path") or ""))
        if folder.is_dir() and folder.parent.resolve() == (ROOT / "out").resolve() and package_file(folder, "PACKAGE_SOURCE_RECORD.json").is_file():
            by_folder.setdefault(folder.resolve(), []).append(book)
    active = []
    duplicate_records = []
    for folder, books in sorted(by_folder.items(), key=lambda item: item[0].name.casefold()):
        # Theme-backed records are the durable catalog source; package-only
        # legacy records are refreshed too, but must not rebuild the same
        # handoff a second time.
        books.sort(key=lambda item: (str(item.get("source_key") or "").startswith("package:"), item["book_id"]))
        active.append(books[0])
        duplicate_records.extend(books[1:])

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    before = ROOT / "reports" / f"PUBLICATION_INFORMATION_BEFORE_{stamp}.json"
    before.write_text(json.dumps([
        {"book_id": book["book_id"], "package_path": book["package_path"], "metadata": book["metadata"]}
        for book in active
    ], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    rows = []
    for book in active:
        folder = Path(book["package_path"])
        old = dict(book["metadata"])
        refreshed, protected = _refresh_meta(old, _record(folder))
        service.db.save_metadata(book["book_id"], refreshed)
        current = service.db.get_book(book["book_id"])
        listing_dir = folder / "02_LISTING_INFORMATION"
        listing_dir.mkdir(parents=True, exist_ok=True)
        (listing_dir / "KDP_LISTING_KIT.txt").write_text(listing_copy_text(current, "amazon") + "\n", encoding="utf-8")
        master = folder / "MASTER_RELEASE_PACKAGE" / "MASTER_METADATA.json"
        if master.parent.is_dir():
            master.write_text(json.dumps(refreshed, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        quality = {platform: marketplace_copy_quality(refreshed, platform) for platform in ("amazon", "etsy", "ingram")}
        rows.append({
            "book_id": book["book_id"], "folder": folder.name, "title": refreshed.get("title"),
            "puzzle_type": refreshed.get("puzzle_type"), "topic": refreshed.get("theme"),
            "page_count": refreshed.get("page_count"), "puzzle_count": refreshed.get("puzzle_count"),
            "prices": refreshed.get("price"), "kdp_estimate": kdp_us_large_trim_estimate(refreshed),
            "amazon_categories": refreshed.get("amazon_category_directions"),
            "bisac": refreshed.get("ingram_subjects"), "keywords": refreshed.get("amazon_keywords"),
            "quality": quality, "protected_human_fields": protected,
        })

    # Keep legacy catalog aliases consistent without treating them as extra
    # physical books or regenerating the same folder twice.
    canonical_by_folder = {Path(book["package_path"]).resolve(): service.db.get_book(book["book_id"])["metadata"] for book in active}
    for duplicate in duplicate_records:
        service.db.save_metadata(duplicate["book_id"], canonical_by_folder[Path(duplicate["package_path"]).resolve()])

    results = service.prepare_many([book["book_id"] for book in active], list(MARKETPLACES))
    failures = [{"book_id": book_id, "marketplace": market, "status": status} for book_id, market, status in results if str(status).startswith("Error")]
    score_failures = [
        {"title": row["title"], "platform": platform, "score": value["score"], "notes": value["notes"]}
        for row in rows for platform, value in row["quality"].items() if int(value["score"]) < 90
    ]
    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "books": len(rows), "catalog_aliases_synchronized": len(duplicate_records), "marketplace_documents": len(results),
        "handoff_failures": failures, "copy_quality_failures": score_failures,
        "pricing_research_basis": [
            "KDP US large-trim black-ink printing costs and 60% royalty threshold checked 2026-09-20.",
            "Comparable 2026 puzzle-book print and Etsy digital pricing reviewed; recommendations are launch prices, not revenue promises.",
            "Final printer cost, tax, discount, and royalty must still be confirmed in each live portal.",
        ],
        "books_detail": rows, "backup": str(before),
    }
    target = ROOT / "reports" / "ACTIVE_PUBLICATION_INFORMATION_AUDIT.json"
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"books": len(rows), "marketplace_documents": len(results), "handoff_failures": len(failures), "copy_quality_failures": len(score_failures), "report": str(target)}, indent=2))
    return 0 if not failures and not score_failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
