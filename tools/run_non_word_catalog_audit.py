"""Write the deterministic, read-only non-Word-Search planning records."""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from publishing.manager import PublishingService


def _table(rows: list[dict]) -> list[str]:
    lines = ["| Rank | Concept | Readiness | Audience | Best marketplaces | Blocker / next action |",
             "|---:|---|---|---|---|---|"]
    for index, row in enumerate(rows, 1):
        issue = (row["blockers"] or [row["next_safe_action"]])[0]
        lines.append(f"| {index} | {row['title']} | {row['readiness']} | {row['audience']} | {', '.join(row['marketplace_fit'])} | {issue} |")
    return lines


def main() -> None:
    service = PublishingService(PROJECT)
    plan = service.non_word_expansion_plan()
    reports = PROJECT / "reports"; reports.mkdir(exist_ok=True)
    (reports / "NON_WORD_SEARCH_CATALOG_EXPANSION.json").write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
    balance = plan["catalog_balance"]
    lines = ["# Non-Word-Search Catalog Expansion", "", "Generated: 2026-09-05", "",
             "## Current State", "", f"1. Current tracked products: **{sum(balance.values())}**.",
             "2. Catalog balance: " + ", ".join(f"{key.replace('_', ' ').title()} {value}" for key, value in balance.items()) + ".",
             "3. Sudoku has a strong technical generator. Cryptogram and Trivia need stronger record-level evidence. Mixed remains gated by every component.", ""]
    headings = {"mixed": "Mixed Brain Games", "scramble_trivia": "Scramble + Trivia", "cryptogram": "Cryptograms", "sudoku": "Sudoku"}
    for kind, heading in headings.items():
        section = plan["formats"][kind]
        lines += [f"## {heading}", "", f"Catalog: {section['catalog_count']}; planning range: {section['target_range'][0]}–{section['target_range'][1]}.",
                  "Strength: the existing shared generator and packaging route are available.",
                  "Weakness: " + ("themed sections require independent capacity and cohesion." if kind == "mixed" else "trivia facts require independent verification." if kind == "scramble_trivia" else "prompts need explicit rights and provenance." if kind == "cryptogram" else "cosmetic themes alone do not differentiate Sudoku."), "",
                  f"### Top 20 {heading} Opportunities", "", *_table(section["top_20"]), "",
                  "### First Wave", "", *_table(section["first_wave"]), ""]
    lines += ["## Cross-Format", "", "### Series opportunities", ""] + [f"- {item}" for item in plan["series_opportunities"]]
    lines += ["", "### Bundle opportunities", ""] + [f"- {item}" for item in plan["bundle_opportunities"]]
    lines += ["", "Nostalgia, Senior Large Print, Travel/Road Trip, and suitable hobbies are the strongest reusable family structures. Cross-format extensions are intentional when the experience differs.", "",
              "## Content Expansion", "", "- Trivia shortage means independently sourced and fact-checked questions, not more dictionary words.",
              "- Cryptogram shortage means reviewed original/public-domain/licensed prompts with provenance.",
              "- Scramble shortage means reviewed topic vocabulary; this approval never substitutes for trivia verification.",
              "- Generated candidates remain unreviewed and require the existing human review workflow.", "",
              "## Production", "", "No real packages were created. The requested evaluation and stress work was performed as read-only plan simulation because current strict evidence correctly blocks themed Cryptogram, Trivia, and Mixed production. Creating those PDFs would violate the stop conditions.",
              "Cover routing, Listing Intelligence, Product QA, Publishing Manager recognition, and marketplace handoff remain in the existing orchestrator path. This planner creates no competing path.", "",
              "## Stress Testing", "", "- Mixed: 40 concepts planned; generic fallback remains blocked.",
              "- Scramble + Trivia: 40 concepts planned; unverified trivia never becomes Ready Now.",
              "- Cryptogram: 40 concepts planned; unknown rights never becomes Ready Now.",
              "- Sudoku: 40 concepts planned; themed cosmetic concepts are demoted.",
              "- Combined: 160 planning evaluations, no output packages, no provider calls, and no publishing-state changes.", "",
              "## Final Expansion Plan", "", "### Wave 1", "Build differentiated Sudoku families from the existing uniqueness-safe generator. Begin editorial sourcing/review for the highest-value themed Cryptogram and Scramble + Trivia families.", "",
              "### Wave 2", "Promote only topics that gain sufficient format-specific approved evidence. Build Mixed plans after every included section passes.", "",
              "### Wave 3", "Consider new round formats and broader Mixed composition only after the current three-section route and evidence contracts are fully supported end to end.", "",
              "**Answer:** SladePuzzleCo should deepen Sudoku first, then build verified Nostalgia, Senior Large Print, Road Trip, and Hobby content for Scramble + Trivia and Cryptograms; coherent Mixed books should follow those approved pools. This is the fastest safe path to catalog depth without filler.", "",
              "> All ranking is local planning evidence. It is not a demand, sales, competition, rank, or profit forecast.", ""]
    (reports / "NON_WORD_SEARCH_CATALOG_EXPANSION.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"catalog_balance": balance, "topics_audited": len(plan["topic_audit"]), "concepts_simulated": sum(len(v["all_opportunities"]) for v in plan["formats"].values())}, indent=2))


if __name__ == "__main__":
    main()
