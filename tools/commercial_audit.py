"""Audit the new commercial baseline without changing packages or statuses."""
from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))


def main() -> None:
    from publishing import PublishingService
    from publishing.commercial_intelligence import commercial_assessment
    from publishing.package_layout import release_contract
    service = PublishingService(PROJECT)
    manifest_path = PROJECT / "reports" / "COMMERCIAL_BASELINE_MANIFEST.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        expected_paths = {Path(str(item.get("package") or "")).resolve() for item in manifest.get("packages", []) if isinstance(item, dict)}
    except (OSError, json.JSONDecodeError):
        expected_paths = set()
    rows = []
    for book in service.db.list_books():
        package = Path(str(book.get("package_path") or ""))
        if not package.is_dir() or package.resolve() not in expected_paths:
            continue
        contract = release_contract(package)
        assessment = commercial_assessment(book)
        statuses = service.db.marketplace_records(book["book_id"])
        a_plus = package / "06_KDP_A_PLUS"
        a_plus_required = {"whats_inside.png", "sample_puzzles.png", "features.png", "series_comparison.png", "KDP_A_PLUS_PUBLISHING_SHEET.txt", "a_plus_manifest.json"}
        a_plus_missing = sorted(name for name in a_plus_required if not (a_plus / name).is_file())
        row = {
            "title": book["metadata"].get("title"),
            "type": book["metadata"].get("puzzle_type"),
            "pages": book["metadata"].get("page_count"),
            "package": str(package),
            "release_contract": contract,
            "commercial_score": assessment["commercial_value_score"],
            "listing_scores": {key: assessment["marketplaces"][key]["listing_quality"]["score"] for key in assessment["marketplaces"]},
            "marketplace_statuses": {key: statuses[key]["status"] for key in ("amazon", "barnes_noble", "payhip", "lulu")},
            "kdp_a_plus": {"local_asset_kit_ready": not a_plus_missing, "missing": a_plus_missing},
        }
        row["passed"] = bool(contract["ready"]) and not a_plus_missing and all(value == "Ready" for value in row["marketplace_statuses"].values())
        rows.append(row)
    expected = {"Word Search": 2, "Sudoku": 2, "Cryptogram": 2, "Word Scramble + Trivia": 2, "Mixed Brain Games": 2}
    actual = {kind: sum(1 for row in rows if row["type"] == kind) for kind in expected}
    report = {
        "expected_by_type": expected,
        "actual_by_type": actual,
        "candidate_count": len(rows),
        "all_expected_types_present": actual == expected,
        "all_packages_passed": bool(rows) and all(row["passed"] for row in rows),
        "rows": rows,
    }
    target = PROJECT / "reports" / "MARKETPLACE_COMMERCIAL_INTELLIGENCE_REPORT.json"
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    text = PROJECT / "reports" / "MARKETPLACE_COMMERCIAL_INTELLIGENCE_REPORT.txt"
    lines = ["MARKETPLACE COMMERCIAL INTELLIGENCE REPORT", "=" * 68,
             f"Candidates: {report['candidate_count']}",
             f"Expected type mix complete: {report['all_expected_types_present']}",
             f"All release contracts, local A+ kits, and four core local handoffs pass: {report['all_packages_passed']}", ""]
    for row in rows:
        lines += [f"{row['title']} — {row['type']}", f"  Pages: {row['pages']} | Buyer-value clarity: {row['commercial_score']}/100", f"  Contract ready: {row['release_contract']['ready']}", f"  Local A+ asset kit ready: {row['kdp_a_plus']['local_asset_kit_ready']}", f"  Listing scores: {row['listing_scores']}", f"  Local handoffs: {row['marketplace_statuses']}", f"  Result: {'PASS' if row['passed'] else 'REVIEW'}", ""]
    text.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
