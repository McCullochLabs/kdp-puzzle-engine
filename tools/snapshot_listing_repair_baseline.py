"""Snapshot only the current commercial batch before listing-copy repair."""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    from publishing import PublishingService
    service = PublishingService(PROJECT)
    manifest_path = PROJECT / "reports" / "COMMERCIAL_BASELINE_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = {Path(str(item["package"])).resolve() for item in manifest.get("packages", [])}
    rows = []
    for book in service.db.list_books():
        package = Path(str(book.get("package_path") or "")).resolve()
        if package not in expected:
            continue
        meta = book.get("metadata") or {}
        protected = {}
        for relative in ("01_PRINT_UPLOADS/interior.pdf", "01_PRINT_UPLOADS/kdp_full_wrap.pdf", "03_PREVIEWS/front_cover.png"):
            target = package / relative
            protected[relative] = digest(target) if target.is_file() else "MISSING"
        rows.append({
            "book_id": book["book_id"], "title": meta.get("title"), "package": str(package),
            "metadata": {key: meta.get(key) for key in ("title", "subtitle", "author", "theme", "puzzle_type", "puzzle_count", "difficulty", "audience", "description", "amazon_keywords", "etsy_tags", "website_tags", "ingram_subjects", "platform_descriptions", "price")},
            "protected_hashes": protected,
        })
    if len(rows) != 10:
        raise RuntimeError(f"Expected exactly 10 current commercial packages; found {len(rows)}. No repair was started.")
    payload = {"created_at": datetime.now().isoformat(timespec="seconds"), "source_manifest": str(manifest_path), "packages": rows}
    target = PROJECT / "reports" / "PUBLISHING_INTELLIGENCE_REPAIR_BASELINE.json"
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print("Snapshotted 10 packages:")
    for row in rows:
        print(f"- {row['title']}\t{row['package']}")


if __name__ == "__main__":
    main()
