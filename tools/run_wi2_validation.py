"""Real-data validation runner for Word Intelligence 2.0.

Read-only over production data; writes JSON reports into
out/word_intelligence_reports/.  Run with:

    .venv\\Scripts\\python.exe tools\\run_wi2_validation.py
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
REPORT_DIR = ROOT / "out" / "word_intelligence_reports"

BASELINE = {
    "verdicts": {"FAIL": 171, "PASS_WITH_NOTES": 15, "PASS": 53},
    "causes": {"off_topic": 47179, "trademark_contamination": 103,
               "low_puzzle_worthiness": 3},
    "perf_s": {"taxonomy": 0.349, "store_cached": 1.706, "index": 0.159,
               "single_audit": 0.073, "inventory_239": 37.032},
}


def main() -> None:
    from word_intelligence.pipeline import load_taxonomy, load_or_build_store
    from word_intelligence.theme_audit import audit_all_themes

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out: dict = {"generated_at": stamp, "baseline": BASELINE}

    t0 = time.perf_counter()
    tax = load_taxonomy(ROOT)
    out["taxonomy_seconds"] = round(time.perf_counter() - t0, 3)
    loaded = load_or_build_store(tax, ROOT)
    store = loaded[0] if isinstance(loaded, tuple) else loaded
    out["records"] = len(store.records)
    out["dictionary_words"] = len(store.dictionary_words)

    t1 = time.perf_counter()
    res = audit_all_themes(ROOT / "themes", store, tax)
    out["inventory_seconds"] = round(time.perf_counter() - t1, 1)
    out["verdicts"] = res["verdicts"]
    statuses: dict[str, int] = {}
    per_theme = []
    for rep in res["reports"]:
        for f in rep.findings:
            statuses[f.status] = statuses.get(f.status, 0) + 1
        per_theme.append({
            "file": rep.theme_file, "title": rep.title,
            "verdict": rep.verdict, "words": rep.word_count,
            "counts": {s: c for s, c in sorted(
                (lambda d: d)( {ff.status: sum(
                    1 for x in rep.findings if x.status == ff.status)
                    for ff in rep.findings}).items())},
        })
    out["finding_statuses"] = statuses
    out["themes"] = per_theme
    out["themes_scanned"] = res["themes_scanned"]
    path = REPORT_DIR / f"wi2_validation-{stamp}.json"
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(out, handle, indent=1, ensure_ascii=False, default=str)
    print("WROTE", path)
    print("VERDICTS", json.dumps(res["verdicts"]))
    print("STATUSES", json.dumps(statuses))


if __name__ == "__main__":
    main()
