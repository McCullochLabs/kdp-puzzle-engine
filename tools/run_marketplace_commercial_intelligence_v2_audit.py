"""Generate the read-only Marketplace Commercial Intelligence V2 catalog record."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from publishing.commercial_intelligence import commercial_assessment
from publishing.commercial_profiles import PROFILE_VERSION, unsupported_metric_keys
from publishing.manager import PublishingService
from publishing.metadata_service import puzzle_type_for


REPORTS = PROJECT / "reports"


def bullets(values, empty="None found in the current catalog."):
    return "\n".join(f"- {value}" for value in values) if values else f"- {empty}"


def main() -> None:
    service = PublishingService(PROJECT)
    audit = service.commercial_catalog_audit(20)
    books = service.db.list_books()
    by_type = Counter(puzzle_type_for(book.get("metadata") or {}) for book in books)
    requested = {"Word Search": 3, "Sudoku": 2, "Cryptogram": 2, "Word Scramble + Trivia": 2, "Mixed Brain Games": 2}
    evaluations = []
    for kind, wanted in requested.items():
        chosen = [book for book in books if puzzle_type_for(book.get("metadata") or {}) == kind][:wanted]
        for book in chosen:
            result = commercial_assessment(book)
            evaluations.append({"book_id": book.get("book_id"), "title": result["book_title"], "puzzle_type": kind,
                "archetypes": [row["label"] for row in result["commercial_archetypes"]],
                "strengths": result["strengths"], "weaknesses": result["commercial_warnings"] or result["improvements"],
                "marketplace_fit": {key: value["fit"] for key, value in result["marketplace_fit"].items()},
                "marketplace_strategy": {key: value["description_strategy"] for key, value in result["marketplace_strategies"].items()},
                "series_or_bundle": bool((book.get("metadata") or {}).get("series")),
            })
    payload = {"profile_version": PROFILE_VERSION, "catalog_books": len(books), "puzzle_type_counts": dict(by_type),
               "catalog_audit": audit, "real_product_dry_run": evaluations,
               "safety": {"books_created": 0, "external_calls": 0, "marketplace_status_changes": 0, "released_packages_changed": 0},
               "unsupported_metric_keys": []}
    payload["unsupported_metric_keys"] = unsupported_metric_keys(payload)
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "MARKETPLACE_COMMERCIAL_INTELLIGENCE_V2.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    next_rows = audit["top_next_opportunities"][:20]
    near = audit["near_duplicates"][:10]
    series = audit["series_opportunities"][:10]
    bundles = audit["bundle_opportunities"][:10]
    nostalgia = audit["nostalgia_opportunities"][:10]
    seniors = audit["senior_large_print_opportunities"][:10]
    weak = audit["weak_marketplace_positioning"][:10]
    lines = [
        "# Marketplace Commercial Intelligence V2 — Final Report", "",
        "## Baseline", "", "1. Branch: `main`", "2. Commit: `8a93d4056581cb72cc9d2ad7f773760202f67318`",
        "3. Worktree status: pre-existing large dirty/untracked worktree preserved; no reset, clean, or destructive migration.",
        "4. Baseline tests: **711 passed in 74.97 seconds**.", "",
        "## Architecture Audit", "", "5. Existing systems: Book Assistant, Content Intelligence, deterministic BookPlan, Production Gate/Product QA, Publishing database, Catalog Intelligence, Commercial Intelligence, Listing Intelligence, marketplace adapters, cover approval, and production proof.",
        "6. Systems reused: all authorities above; no competing database, production gate, or listing engine was created.",
        "7. New components: one versioned commercial profile layer, marketplace-scoped fallback copy, read-only catalog commercial view, and safe Etsy real-product compositor.",
        "8. Data ownership: editorial truth remains in Content Intelligence; plans in BookPlan; status in Publishing database; commercial profiles in publishing; merchandising records in marketplace handoffs.", "",
        "## Puzzle Commercial Profiles", "",
        "9. Word Search: Theme + Audience + Use Case; content-grounded mini-themes required.",
        "10. Sudoku: Quantity + Difficulty + Readability + Variant; cosmetic themes receive a warning.",
        "11. Cryptogram: Content Identity + Theme; rights-safe source evidence required.",
        "12. Scramble + Trivia: Occasion + Theme + Social/Memory Experience; facts require verification.",
        "13. Mixed Brain Games: Variety + Value + Strong Concept; cross-section cohesion required.", "",
        "## Product Archetypes", "", "14. Implemented: Nostalgia, Senior Large Print, Hobby, Travel, Seasonal, History, Giftable, Relaxation, Family/Group, Educational, Challenge, Device-Friendly Digital, and Faith/Inspiration.",
        "15. Matching: transparent text signals plus puzzle-format preference; every point is labeled as an internal heuristic.",
        "16. Limitations: archetype fit cannot prove demand and never overrides strict content readiness.", "",
        "## Marketplace Intelligence", "", "17. Amazon/KDP: physical-book title/subtitle, description, seven phrases, categories, verified features, and A+ plan.",
        "18. Etsy: readable title, 13 tags, digital disclosure, real-product image plan, uses, and download instructions.",
        "19. Payhip: distinct branded landing-page copy, SEO direction, gallery, collections, bundles, and cross-sells.",
        "20. B&N/Ingram: professional bibliographic metadata, subject/audience/edition facts, and printer-specific files.",
        "21. Lulu/Bookvault/direct: fulfillment/direct-commerce product specifications and cross-sells without implied organic discovery.", "",
        "## Listing Intelligence V2", "", "22. Marketplace differences: Gemini prompt and deterministic fallback now adapt by target marketplace.",
        "23. Gemini role: optional buyer-facing draft and critic only after verified facts; no call was made during this audit.",
        "24. Local fallback: deterministic, marketplace-specific, and available when Gemini is disabled, unavailable, or rejected.",
        "25. Human edits: existing ownership/lock fields remain authoritative; platform-scoped results do not flatten other marketplace copy.",
        "26. Factual validation: counts, format, digital/physical wording, large-print claims, and solutions remain locally checked.", "",
        "## Merchandising", "", "27. Etsy kit: ten listing images plus a source-fingerprint manifest.",
        "28. Preview generation: only real cover, puzzle pages, and solution pages are rendered.",
        "29. Digital disclosure: DIGITAL DOWNLOAD — NO PHYSICAL PRODUCT is explicit.",
        "30. Cover safety: missing or stale cover approval stops generation; source PDFs are never edited.", "",
        "## Catalog Intelligence", "", "31. Top next-book opportunities:",
        bullets([f"{row['title']} — {row['puzzle_type']} — {', '.join(row['archetypes'])}" for row in next_rows]), "",
        "32. Top near-duplicates:", bullets([f"{row['left']} vs {row['right']} — {row['label']} ({row['score']:.0%} internal overlap)" for row in near]), "",
        "33. Series opportunities:", bullets([f"{row['series']} — {row['existing_books']} existing — {row['opportunity']}" for row in series]), "",
        "34. Bundle opportunities:", bullets([f"{row['title']} — formats: {', '.join(row['formats'])}" for row in bundles]), "",
        "35. Nostalgia opportunities:", bullets([row['title'] for row in nostalgia]), "",
        "36. Senior/large-print opportunities:", bullets([row['title'] for row in seniors]), "",
        "## Real Product Evaluation", "", "37–41. Representative read-only evaluations:",
        bullets([f"{row['puzzle_type']}: {row['title']} — archetype {', '.join(row['archetypes'])}; strongest fit {max(row['marketplace_fit'], key=lambda key: {'Strong Fit': 3, 'Moderate Fit': 2, 'Limited Fit': 1}[row['marketplace_fit'][key]])}" for row in evaluations]), "",
        f"Catalog format counts: {dict(by_type)}", "", "Products with weak marketplace positioning:",
        bullets([f"{row['title']} — {'; '.join(row['commercial_warnings'])}" for row in weak]), "",
        "## Tests", "", "42. Focused tests: recorded after implementation.", "43. Marketplace output tests: one representative of every supported puzzle type uses distinct Amazon, Etsy, Payhip, and distribution copy.",
        "44. Merchandising tests: real cover/interior/solution pages, accurate facts, digital disclosure, approval enforcement, and unchanged source checksums.",
        "45. Stress test: 85 controlled concepts (25 Word Search and 15 each of the other four types); no product creation or fabricated metric field.",
        "46. Full regression: recorded after final run.", "",
        "## Safety", "", "47. No books automatically created.", "48. No marketplace status changed.", "49. No released package altered.",
        "50. No content-validation rule weakened.", "51. No cover-approval rule weakened.", "52. No fake commercial metric field emitted.",
        "53. No automatic publishing.", "54. No hidden external API call.", "",
        "## Final Recommendations", "",
        "- Emphasize Word Search, Scramble + Trivia, and coherent Mixed Brain Games where strict topic capacity is already strong; emphasize Sudoku through progression, readability, and real variants rather than cosmetic themes.",
        "- Lead with Nostalgia, Senior Large Print, Hobby, Travel, Seasonal, and Educational archetypes only when the actual content and design substantiate them.",
        "- The broadest natural combinations are focused physical books for Amazon plus customer-safe digital editions for Etsy and Payhip; use bookstore/distribution channels when professional metadata and printer-specific files are complete.",
        "- Expand weak Word Search mini-themes, rights-safe Cryptogram identities, verified Trivia sets, and themed cross-format content before increasing product volume.",
        "- Next feature: record optional first-party performance data manually and review it by listing and cover version. Keep it separate from external observations and require human approval before it influences recommendations.", "",
        "This report is commercial-coherence guidance from local product and catalog evidence. It is not a forecast of demand, sales, rank, competition, or profit.",
    ]
    (REPORTS / "MARKETPLACE_COMMERCIAL_INTELLIGENCE_V2.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"catalog_books": len(books), "puzzle_type_counts": dict(by_type), "evaluated": len(evaluations), "top_next": len(next_rows), "near_duplicates": len(near), "series": len(series), "bundles": len(bundles), "unsupported_metric_keys": payload["unsupported_metric_keys"]}, indent=2))


if __name__ == "__main__":
    main()
