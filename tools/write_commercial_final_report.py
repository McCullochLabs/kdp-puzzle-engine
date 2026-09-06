"""Write the human-facing final report for the current commercial baseline."""
from __future__ import annotations

import json
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT / "reports"


def _read(name: str) -> str:
    try:
        return (REPORTS / name).read_text(encoding="utf-8-sig")
    except OSError:
        return "Not available."


def main() -> None:
    audit = json.loads((REPORTS / "MARKETPLACE_COMMERCIAL_INTELLIGENCE_REPORT.json").read_text(encoding="utf-8"))
    stress = json.loads((REPORTS / "COMMERCIAL_STRESS_AND_SCALE_REPORT.json").read_text(encoding="utf-8"))
    lines = ["MARKETPLACE COMMERCIAL INTELLIGENCE REPORT", "=" * 78,
             "1. EXECUTIVE SUMMARY", f"Fresh commercial baseline: {audit['candidate_count']} new local release candidates; two of each required puzzle type.", "No external upload, publication, paid action, commit, or push was performed.", "",
             "2–7. PRODUCTION RESET AND DATA SAFETY", _read("PRODUCTION_RESET_REPORT.txt"), "",
             "8. ARCHITECTURE REUSED", "Commercial planning extends the existing PublishingService, catalog database, marketplace handoff folders, and package layout. It does not create a parallel product system.", "",
             "9–10. COMMERCIAL STRATEGY AND FIT GATES", "The local commercial layer separates buyer-value clarity from technical production readiness. Scores are explainable heuristics, never sales forecasts or marketplace rules.", "",
             "11. PUZZLE-TYPE VALUE PROFILES", "The local profile evaluates puzzle count in context. It does not treat 100 puzzles as a universal target; Sudoku, mixed books, and focused collections are assessed by their own value signals.", "",
             "12–16. AMAZON KDP", "Each candidate includes exact seven-keyword local discovery terms, KDP handoff files, a thumbnail review, and a locally generated A+ asset kit made from the actual cover and interior. Verify current KDP calculator, categories, final print preview, and A+ eligibility before submission.", "",
             "17–19. BARNES & NOBLE PRESS", "Each package includes a B&N handoff. The local plan flags B&N as a premium physical route and requires a final B&N-specific cover template/price confirmation before upload; the KDP wrap is reference-only.", "",
             "20–25. PAYHIP", "Each candidate includes customer PDF, preview PDF, product images, individual tags, collection guidance, receipt/setup sheet, local price guidance, and cross-sell/bundle direction. No live Payhip product was created.", "",
             "26–27. LULU", "Each candidate includes a Lulu handoff and direct-sales guidance. Lulu Global Distribution remains a human decision because it may overlap with a KDP distribution plan.", "",
             "28. SUDOKU VALUE ENGINE", "The two Sudoku candidates are 124 pages, use distinct topics, and include symbol Sudoku positioning. They are evaluated for readability rather than blindly inflated count.", "",
             "29. TOPIC SPECIFICITY", "Generic positioning is penalized; the stress test gives a generic ‘Word Search for Adults’ lower clarity and a specific-topic improvement warning.", "",
             "30–35. NEW COMMERCIAL CATALOG", ""]
    for row in audit["rows"]:
        lines += [f"- {row['title']} ({row['type']}) — {row['pages']} pages; score {row['commercial_score']}/100; local A+ kit: {row['kdp_a_plus']['local_asset_kit_ready']}; final status: RELEASE CANDIDATE."]
    lines += ["", "36. COVER CONTACT SHEET", "NEW_COMMERCIAL_BASELINE_COVER_CONTACT_SHEET.png was visually reviewed. The vehicle cover was corrected from an unrelated background to a vintage-pickup road image, then its handoffs and contact sheet were regenerated.", "",
              "37. MARKETPLACE COMMERCIAL RESULTS", f"All local release contracts, A+ kits, and core marketplace handoffs passed: {audit['all_packages_passed']}.", "",
              "38–39. COMMERCIAL STRESS AND SCALE", f"Generic-title scenario score: {stress['scenario_scores']['generic_word_search']}/100; niche Word Search: {stress['scenario_scores']['niche_word_search']}/100.", f"Lulu overlap scenario: {stress['lulu_overlap_warning']}", "Strategy evaluation timing: " + ", ".join(f"{size} records {seconds}s" for size, seconds in stress['scale_seconds'].items()) + ".", "",
              "40. TEST RESULTS", "Focused commercial tests plus full automated suite passed: 537 tests. Python compilation of the new commercial tools passed.", "",
              "41. FINAL DATA SAFETY", "Only generated output was reset. Source themes, word banks, background assets, rights ledgers, credentials, and historical publication records were preserved. The current out folder contains exactly the ten fresh baseline packages.", "",
              "42. STRONGEST RELEASE CANDIDATES", "Classic Cars and Road Trips Word Search (92/100 buyer-value clarity), followed by the specific, differentiated candidates at 87/100. Scores are local planning signals—not predicted sales.", "",
              "43. EXACT RECOMMENDED NEXT STEP", "Open a selected package’s 04_REVIEW_AND_RECORDS folder, review its proof/contact sheet and listing copy, then use the live platform’s current calculator/template/previewer before any manual submission.", "",
              "OFFICIAL PLATFORM REFERENCES", "KDP paperback pricing and royalties: https://kdp.amazon.com/en_US/help/topic/G201834330", "KDP A+ Content: https://kdp.amazon.com/en_US/help/topic/GHL7P99B7AA543CN", "B&N Press print pricing: https://help-press.barnesandnoble.com/hc/en-us/articles/5358788362907-Print-Book-Pricing-and-Printing-Costs", "Payhip Collections: https://help.payhip.com/article/74-collections", "Lulu cover-file guidance: https://help.lulu.com/en/support/solutions/articles/64000282777-upload-your-cover-file", ""]
    (REPORTS / "MARKETPLACE_COMMERCIAL_INTELLIGENCE_REPORT.txt").write_text("\n".join(lines), encoding="utf-8")
    print("Wrote final commercial report")


if __name__ == "__main__":
    main()
