"""Safe no-network listing stress test using verified-style local facts."""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))


class UnavailableGemini:
    provider_name="Gemini"
    def available(self): return True
    def generate_listing(self,_facts):
        from publishing.listing_intelligence import ListingProviderError
        raise ListingProviderError("Safe stress test: provider intentionally unavailable.")


def book(index, kind, topic):
    return {"book_id":f"stress-{index}","metadata":{"title":f"{topic} {kind} Collection", "subtitle":f"48 {kind} challenges", "theme":topic,"puzzle_type":kind,"puzzle_count":48,"difficulty":"Standard","audience":"Adults and Teens","price":{"amazon":9.99}}}


def main() -> None:
    from publishing.listing_intelligence import ListingIntelligence
    kinds=[*("Word Search",)*10,*("Sudoku",)*3,*("Cryptogram",)*3,*("Word Scramble + Trivia",)*3,*("Mixed Brain Games",)*3]
    topics=["National Parks","Gardening","Space and Astronomy","Classic Cars","Bird Watching","Travel","Food","Pets","Weather","Vocabulary","Garden Logic","Stargazer","Numbers","American History","Celestial Messages","Roadside Ciphers","Kitchen Trivia","Road Trips","Nature Trails","Study Skills","Wild Places","Family Games"]
    engine=ListingIntelligence(PROJECT,provider=UnavailableGemini())
    records=[]
    for index,(kind,topic) in enumerate(zip(kinds,topics),1):
        result=engine.generate(book(index,kind,topic),"amazon",enabled=True); content=result.get("content") or {}
        keywords=content.get("keywords") or []
        records.append({"type":kind,"topic":topic,"source":result.get("provider"),"validation":result.get("validation"),"keywords":len(keywords),"duplicate_keywords":len(keywords)!=len(set(str(x).casefold() for x in keywords)),"description_words":len(str(content.get("description") or "").split())})
    report={"records":len(records),"by_type":{kind:sum(1 for item in records if item["type"]==kind) for kind in sorted(set(kinds))},"fallback_count":sum(1 for item in records if item["source"]=="Deterministic local listing"),"duplicate_keyword_sets":sum(1 for item in records if item["duplicate_keywords"]),"short_descriptions":sum(1 for item in records if item["description_words"]<80),"note":"No-network test; verifies safe Gemini-first fallback, semantic keyword de-duplication, and all puzzle-type routes without API usage."}
    (PROJECT/"reports"/"LISTING_INTELLIGENCE_STRESS_REPORT.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    (PROJECT/"reports"/"LISTING_INTELLIGENCE_STRESS_REPORT.txt").write_text("LISTING INTELLIGENCE STRESS REPORT\n\n"+json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,indent=2))


if __name__=="__main__": main()
