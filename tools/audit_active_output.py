"""Read-only structural and content sanity audit for every active output book."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
sys.path.insert(0, str(ROOT))

from preflight import preflight
from publishing.package_layout import package_file
from publishing.production_intelligence import visual_quality_assessment

SENSITIVE = {"ABORTION", "PORNOGRAPHY", "SUICIDE", "RAPE"}


def source_record(folder: Path) -> Path | None:
    return next(iter(folder.glob("**/PACKAGE_SOURCE_RECORD.json")), None)


def audit(folder: Path) -> dict:
    record_path = source_record(folder)
    record = json.loads(record_path.read_text(encoding="utf-8")) if record_path else {}
    ok, checks = preflight(folder)
    issues: list[str] = []
    source = Path(str(record.get("source_theme") or ""))
    words: list[str] = []
    alpha_lists = 0
    numbered_titles = 0
    if source.is_file():
        data = json.loads(source.read_text(encoding="utf-8-sig"))
        for puzzle in data.get("puzzles", []):
            if re.match(r"^(?:page|puzzle)\s+\d+\s*[:\-]", str(puzzle.get("name") or ""), flags=re.I):
                numbered_titles += 1
            bank = [str(value).strip() for value in puzzle.get("words", []) if str(value).strip()]
            words.extend(bank)
            if len(bank) >= 8 and bank == sorted(bank, key=str.casefold):
                alpha_lists += 1
            if len(bank) < 12:
                issues.append(f"Puzzle '{puzzle.get('name', 'Untitled')}' has only {len(bank)} words.")
    normalized = [re.sub(r"[^A-Z]", "", value.upper()) for value in words]
    duplicates = len(normalized) - len(set(normalized))
    flagged = sorted({word for word in normalized if word in SENSITIVE})
    if duplicates:
        issues.append(f"Source has {duplicates} repeated normalized word(s).")
    if alpha_lists:
        issues.append(f"Source has {alpha_lists} alphabetically ordered puzzle list(s).")
    if numbered_titles:
        issues.append(f"Source has {numbered_titles} puzzle title(s) containing provider page-number prefixes.")
    if flagged and not any(token in f"{record.get('title','')} {record.get('theme','')}".casefold() for token in ("adult", "after dark")):
        issues.append("Unexpected sensitive term(s): " + ", ".join(flagged))
    interior = package_file(folder, "interior.pdf")
    if interior.is_file():
        reader = PdfReader(str(interior))
        # A deliberately blank final verso is valid and keeps the physical
        # sheet count aligned with the calculated cover spine.
        blanks = sum(not (page.extract_text() or "").strip() for page in reader.pages[:-1])
        if blanks:
            issues.append(f"Interior has {blanks} page(s) with no extractable text; visually verify intentional pages.")
    visual = visual_quality_assessment(ROOT, folder, record)
    issues.extend(str(item) for item in visual.get("hard_failures", []))
    return {"folder": folder.name, "title": record.get("title", folder.name), "type": record.get("puzzle_type", "Unknown"),
            "preflight": ok, "checks": checks, "source_words": len(words), "issues": issues,
            "visual_attention": visual.get("needs_review", []), "pass": ok and not issues and not visual.get("hard_failures")}


def main() -> None:
    rows = [audit(folder) for folder in sorted(OUT.iterdir()) if folder.is_dir() and not folder.name.startswith("_") and source_record(folder)]
    payload = {"books": len(rows), "passed": sum(row["pass"] for row in rows), "needs_review": sum(not row["pass"] for row in rows), "rows": rows,
               "scope": "Technical structure and automated visual checks only; pass is not approval for sale.",
               "editorial_report": "reports/EDITORIAL_SALE_READINESS.json"}
    target = ROOT / "reports" / "ACTIVE_OUTPUT_AUDIT.json"; target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("Technical audit only — a pass is not approval for sale. See reports/EDITORIAL_SALE_READINESS.json for active word-search editorial holds.")
    print(json.dumps({key: payload[key] for key in ("books", "passed", "needs_review")}, indent=2))
    for row in rows:
        if not row["pass"]:
            print(f"REVIEW: {row['title']} :: {' | '.join(row['issues'])}")


if __name__ == "__main__":
    main()
