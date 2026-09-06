"""Write the final human-facing Gemini-first listing audit report."""
from __future__ import annotations

import json
from pathlib import Path

PROJECT=Path(__file__).resolve().parents[1]
REPORTS=PROJECT/"reports"


def main() -> None:
    baseline=json.loads((REPORTS/"PUBLISHING_INTELLIGENCE_REPAIR_BASELINE.json").read_text(encoding="utf-8"))
    repaired=json.loads((REPORTS/"PUBLISHING_INTELLIGENCE_REPAIR_RESULTS.json").read_text(encoding="utf-8"))
    preserved=json.loads((REPORTS/"PUBLISHING_INTELLIGENCE_REPAIR_VERIFICATION.json").read_text(encoding="utf-8"))
    stress=json.loads((REPORTS/"LISTING_INTELLIGENCE_STRESS_REPORT.json").read_text(encoding="utf-8"))
    lines=["SLADEPUZZLECO — GEMINI-FIRST PUBLISHING INTELLIGENCE AUDIT", "="*78,
           "SYSTEM AUDIT", "1. Previous generation: canonical metadata_service templates generated baseline descriptions, keywords, tags, and marketplace descriptions.", "2. Gemini existed but was only used for an in-memory copy action; normal package preparation refreshed deterministic metadata first.", "3. Marketplace handoffs independently reread deterministic marketplace_content, allowing stronger AI drafts to be bypassed.", "4. Quality loss came from those disconnected paths plus generic deterministic template phrasing and keyword reuse.", "",
           "CHANGES", "- publishing/listing_intelligence.py: richer verified product brief, Gemini-first structured prompt, semantic keyword de-duplication, bounded timeout fallback, optional Gemini critic/review, field-level repair, and human ownership protection.", "- publishing/manager.py: one central listing-intelligence refresh is now available and enabled for normal handoff preparation when the project setting is enabled.", "- publishing/payhip_product.py: Payhip now consumes the canonical platform-specific description.", "- data/listing_intelligence_settings.json: Gemini → local fallback policy, with human-edit protection enabled.", "- Marketplace handoffs use the saved canonical listing fields instead of independently flattening them.", "",
           "GEMINI-FIRST ROUTING", "Verified facts → Gemini primary draft → local factual/semantic validation → optional Gemini critic and field-level repair → marketplace adaptation → handoff files.", "If Gemini is unavailable, times out, fails validation, or is not configured: verified facts → specific local fallback → same validation and handoff path.", "Titles remain unchanged; subtitle changes are stored as suggestions. Explicit human/locked fields are never overwritten.", "",
           "LIVE GEMINI STATUS", "Gemini credentials were configured, but the safe verified connection request timed out. The connector now classifies that condition as a normal fallback instead of an unhandled failure. No key was displayed or written to package files.", "For this repair run: Gemini primary successes 0; timed-out/fallback runs 10; local field repairs 0. This is an availability result, not a claim that Gemini was skipped.", "",
           "TEN-BOOK REPAIR", f"Exact packages processed: {len(repaired)}", ""]
    baseline_by_id={item["book_id"]:item for item in baseline["packages"]}
    for row in repaired:
        old=baseline_by_id[row["book_id"]]["metadata"]
        lines += [f"- {row['title']}", f"  Package: {row['package']}", f"  Source: {row['source']} — {row['fallback']}", f"  Changed automated fields: {', '.join(row['changed'])}", f"  Old description: {str(old.get('description') or '')[:140]}…", "  New details, exact keywords, tags, prices, categories, and old-vs-new comparison: 04_REVIEW_AND_RECORDS/PUBLISHING_INTELLIGENCE_REPORT.txt", ""]
    lines += ["PRESERVATION", f"All protected interiors, covers, and KDP wraps unchanged: {preserved['all_protected_files_unchanged']}", "No packages were deleted, duplicated, regenerated, published, uploaded, or otherwise externally changed.", "",
            "MARKETPLACE HANDOFFS", "Refreshed locally for KDP, Etsy, Payhip, Lulu, Barnes & Noble, IngramSpark, BookVault, and Direct Website. Each retains platform-specific manual/template/ISBN/preview decisions as human steps.", "",
            "TESTING", "Pre-change full suite: 538 passed.", "Focused post-change listing/publishing/marketplace suite: 32 passed.", f"Stress test: {stress['records']} concepts across {stress['by_type']}; fallback count {stress['fallback_count']}; duplicate keyword sets {stress['duplicate_keyword_sets']}; short descriptions {stress['short_descriptions']}.", "",
            "REMAINING LIMITATIONS", "The configured Gemini endpoint must respond successfully before real Gemini-written copy can replace the local fallback. Check the API key's model access, account quota, network/firewall, and endpoint availability in the Gemini setup screen.", "Platform previewers, final printer templates, ISBN choice, live price calculators, and publication remain manual platform checks.", "No real search-volume, competition, sales, CPC, or ranking data is claimed because no verified external market-data source is connected.", "",
            "RECOMMENDED NEXT IMPROVEMENT", "Once the Gemini connection succeeds, use the Book Assistant/Publishing Manager refresh action on a single non-live package first, inspect the generated report, then enable the Gemini-written copy for future production. The system will preserve manual edits and retain local fallback if Gemini becomes unavailable."]
    (REPORTS/"GEMINI_FIRST_LISTING_INTELLIGENCE_AUDIT_REPORT.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("Wrote Gemini-first listing audit report")


if __name__=="__main__": main()
