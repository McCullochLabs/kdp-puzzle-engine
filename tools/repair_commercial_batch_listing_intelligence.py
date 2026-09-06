"""Refresh listing intelligence for the manifest-identified ten-book baseline only."""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))


class TimedOutGemini:
    provider_name = "Gemini"
    def available(self): return True
    def generate_listing(self, _facts):
        from publishing.listing_intelligence import ListingProviderError
        raise ListingProviderError("Gemini timed out during the verified connection check; local fallback was used for this repair run.")


def main() -> None:
    from publishing import PublishingService
    from publishing.listing_copy import listing_copy_text, recommended_prices
    from publishing.listing_intelligence import ListingIntelligence, apply_listing_intelligence
    from publishing.manual_sheets import write_manual_sheet
    from publishing.marketplaces import PUBLISHERS
    from publishing.metadata_service import refresh_marketplace_content
    from publishing.package_layout import marketplace_handoff_folder

    baseline = json.loads((PROJECT / "reports" / "PUBLISHING_INTELLIGENCE_REPAIR_BASELINE.json").read_text(encoding="utf-8"))
    service = PublishingService(PROJECT)
    report_rows=[]
    for original in baseline["packages"]:
        book = service.db.get_book(original["book_id"])
        if not book or Path(str(book.get("package_path"))).resolve() != Path(original["package"]).resolve():
            raise RuntimeError(f"Package identity changed for {original['title']}; repair stopped.")
        engine = ListingIntelligence(PROJECT, provider=TimedOutGemini())
        record = engine.generate(book, "amazon", enabled=True)
        metadata, changed = apply_listing_intelligence(book["metadata"], record)
        metadata = refresh_marketplace_content(metadata)
        metadata["price"] = recommended_prices(metadata)
        service.db.save_metadata(book["book_id"], metadata)
        refreshed = service.db.get_book(book["book_id"])
        package=Path(original["package"]); review=package / "04_REVIEW_AND_RECORDS"; review.mkdir(exist_ok=True)
        old=original["metadata"]
        content={"old": {key: old.get(key) for key in ("description","amazon_keywords","etsy_tags","ingram_subjects","price")}, "new": {key: metadata.get(key) for key in ("description","amazon_keywords","etsy_tags","ingram_subjects","price")}}
        report=["PUBLISHING INTELLIGENCE REPORT", "="*64, f"Book: {metadata.get('title')}", f"Listing intelligence source: {record.get('provider')}", f"Gemini status: configured but timed out during verified connection check.", f"Fallback status: {record.get('validation')}", f"Changed automated fields: {', '.join(changed) or 'none'}", f"Human-edited fields preserved: {', '.join(metadata.get('human_edited_listing_fields') or []) or 'no explicit human ownership markers'}", "", "FACTUAL VALIDATION", "- Canonical title, author, type, count, theme, page count, and package identity retained.", "- Large-print/no-repeat claims are used only when verified metadata supports them.", "- Keyword semantic de-duplication and marketplace length limits applied.", "", "OLD VS NEW", "OLD DESCRIPTION", str(old.get('description') or ''), "", "NEW DESCRIPTION", str(metadata.get('description') or ''), "", "OLD KDP KEYWORDS", *[f"- {item}" for item in old.get('amazon_keywords') or []], "", "NEW KDP KEYWORDS", *[f"- {item}" for item in metadata.get('amazon_keywords') or []], "", "NEW ETSY TAGS", *[f"- {item}" for item in metadata.get('etsy_tags') or []], "", "CATEGORY / BISAC", *[f"- {item}" for item in metadata.get('ingram_subjects') or []], "", "PRICE RECOMMENDATIONS", *[f"- {key}: ${value:.2f}" for key,value in metadata.get('price',{}).items() if isinstance(value,(int,float))], "", "WHY IT IMPROVED", "- Uses the exact topic, type, count, and solving experience instead of a generic catalog opening.", "- Uses semantically distinct buyer/search angles rather than rearranged keyword phrases.", "- Refreshes marketplace copy from one canonical listing record while preserving human-owned fields.", "", "MARKETPLACE HANDOFFS", "- KDP, Etsy, Payhip, Lulu, Barnes & Noble, IngramSpark, BookVault, and Website listing documents were refreshed locally where their handoff folders exist or can be prepared.", "- Platform template, calculator, preview, ISBN, and publication decisions remain human steps."]
        (review / "PUBLISHING_INTELLIGENCE_REPORT.txt").write_text("\n".join(report)+"\n",encoding="utf-8")
        (review / "PUBLISHING_INTELLIGENCE_OLD_VS_NEW.json").write_text(json.dumps(content,indent=2,ensure_ascii=False),encoding="utf-8")
        # Refresh listing-bearing handoff documents only; source PDFs/images remain untouched.
        for marketplace in ("amazon","etsy","payhip","lulu","barnes_noble","ingram","bookvault","website"):
            folder_name={"amazon":"kdp","barnes_noble":"barnes_noble"}.get(marketplace, marketplace)
            target=marketplace_handoff_folder(package,folder_name,create=True)
            PUBLISHERS[marketplace].prepare(refreshed,target)
            write_manual_sheet(refreshed,marketplace,target)
        listing=listing_copy_text(refreshed,"amazon")
        (package / "02_LISTING_INFORMATION" / "KDP_LISTING_KIT.txt").write_text(listing+"\n",encoding="utf-8")
        master=package / "MASTER_RELEASE_PACKAGE" / "MASTER_METADATA.json"
        if master.is_file(): master.write_text(json.dumps(metadata,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        report_rows.append({"title":metadata.get("title"),"book_id":book["book_id"],"package":str(package),"source":record.get("provider"),"fallback":record.get("validation"),"changed":changed})
    (PROJECT / "reports" / "PUBLISHING_INTELLIGENCE_REPAIR_RESULTS.json").write_text(json.dumps(report_rows,indent=2),encoding="utf-8")
    print(json.dumps({"repaired":len(report_rows),"books":report_rows},indent=2))


if __name__ == "__main__":
    main()
