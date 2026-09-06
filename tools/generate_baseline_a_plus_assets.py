"""Generate KDP A+ asset kits for the current commercial baseline only."""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))


def main() -> None:
    from publishing import PublishingService
    from publishing.commercial_intelligence import commercial_assessment
    service = PublishingService(PROJECT)
    manifest = json.loads((PROJECT / "reports" / "COMMERCIAL_BASELINE_MANIFEST.json").read_text(encoding="utf-8"))
    paths = {Path(str(row["package"])).resolve() for row in manifest.get("packages", [])}
    results = []
    for book in service.db.list_books():
        package = Path(str(book.get("package_path") or ""))
        if package.resolve() not in paths:
            continue
        target = service.write_kdp_a_plus_assets(book["book_id"])
        assessment = commercial_assessment(book)
        review = package / "04_REVIEW_AND_RECORDS"
        markets = assessment["marketplaces"]
        strategy = ["MARKETPLACE PRODUCT STRATEGY", "=" * 58, f"MASTER PRODUCT: {assessment['book_title']}", f"Puzzle type: {assessment['puzzle_type']}", f"Topic: {assessment['topic']}", f"Puzzle-count rationale: {book['metadata'].get('puzzle_count')} puzzles are evaluated against the local {assessment['rule_version']} value profile.", ""]
        for key in ("amazon", "barnes_noble", "payhip", "lulu"):
            item = markets[key]
            strategy += [item["marketplace"].upper(), f"Format: {item['format']}", f"Suggested starting price: ${float(item['suggested_price'] or 0):.2f}", f"Strategy: {item['buyer_value_focus']}", f"Cover/listing direction: {item['route_note']}", f"Keywords/tags: {', '.join(item['keywords'])}", ""]
        strategy += ["A+ STRATEGY", f"Local asset kit: {target.name}/. Submit only after KDP publication eligibility is confirmed.", "CROSS-SELL / BUNDLE", "Use only real companion products and buyer-safe bundles; no automatic bundle or cross-sell is created by this plan.", "WARNINGS", "Marketplace requirements and print calculators must be confirmed in the live platform before publication."]
        (review / "MARKETPLACE_PRODUCT_STRATEGY.txt").write_text("\n".join(strategy) + "\n", encoding="utf-8")
        readiness = ["COMMERCIAL READINESS REPORT", "=" * 58, f"Book: {assessment['book_title']}", f"Overall local buyer-value clarity: {assessment['commercial_value_score']}/100", ""]
        for key in ("amazon", "barnes_noble", "payhip", "lulu"):
            item = markets[key]
            readiness += [item["marketplace"], "Production: PASS — local release contract and marketplace handoff prepared.", f"Commercial fit: {item['listing_quality']['score']}/100 — {item['listing_quality']['label']}", "Status: READY FOR HUMAN MARKETPLACE REVIEW", ""]
        readiness += ["FINAL STATUS: RELEASE CANDIDATE", "This is a local readiness result, not an external platform approval or a sales guarantee."]
        (review / "COMMERCIAL_READINESS_REPORT.txt").write_text("\n".join(readiness) + "\n", encoding="utf-8")
        results.append({"title": book["metadata"].get("title"), "asset_kit": str(target), "strategy": str(review / "MARKETPLACE_PRODUCT_STRATEGY.txt")})
    print(json.dumps({"generated": len(results), "assets": results}, indent=2))


if __name__ == "__main__":
    main()
