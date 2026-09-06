"""Commercial book simulations over the REAL intelligence store (PART K).

Deterministic seeds; read-only against production data.  Writes a JSON
report into out/word_intelligence_reports/.

    .venv\\Scripts\\python.exe tools\\run_wi2_simulations.py
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

# Requested simulations (spec PART K): topic -> (puzzles, words per puzzle).
SIMULATIONS = {
    "national_parks": [(100, 20)],
    "gardening": [(100, 20), (48, 12), (50, 15)],
    "christmas": [(100, 20)],
    "ocean_life": [(100, 20), (48, 15)],
    "nature": [(100, 20)],
}


def main() -> None:
    from word_intelligence.pipeline import load_or_build_store, load_taxonomy
    from word_intelligence.pool_builder import PoolRequest, build_word_pool
    from word_intelligence.book_quality import score_book

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    tax = load_taxonomy(ROOT)
    loaded = load_or_build_store(tax, ROOT)
    store = loaded[0] if isinstance(loaded, tuple) else loaded

    results = []
    for topic_id, requests in SIMULATIONS.items():
        cid = tax.resolve(topic_id)
        if not cid:
            results.append({"topic": topic_id, "resolved": False})
            continue
        for puzzle_count, words_per in requests:
            t0 = time.perf_counter()
            request = PoolRequest(
                topic_id=cid,
                puzzle_count=puzzle_count,
                words_per_puzzle=words_per,
                seed=20260824,               # deterministic across runs
                strictness="balanced",
                max_word_reuse=1,            # controlled reuse allowed
            )
            built = build_word_pool(store, tax, request)
            quality = score_book(
                store, tax, cid, built.puzzles,
                puzzle_clusters=built.puzzle_clusters,
                repetition_pressure=built.repetition_pressure)
            results.append({
                "topic": cid,
                "request": {"puzzles": puzzle_count, "words_per_puzzle": words_per},
                "built_puzzles": len(built.puzzles),
                "shortfall": built.shortfall,
                "warnings": built.warnings[:6],
                "repetition_pressure": built.repetition_pressure,
                "capacity": built.capacity,
                "quality": quality.to_dict(),
                "seconds": round(time.perf_counter() - t0, 2),
            })

    payload = {"generated_at": stamp, "seed": 20260824,
               "simulations": results}
    path = REPORT_DIR / f"wi2_simulations-{stamp}.json"
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=1, ensure_ascii=False, default=str)
    print("WROTE", path)
    for row in results:
        if not row.get("resolved", True):
            print(f"{row['topic']:<22} UNRESOLVED")
            continue
        q = row["quality"]
        print(f"{row['topic']:<22} {row['request']['puzzles']:>3}x"
              f"{row['request']['words_per_puzzle']:<3}"
              f" built={row['built_puzzles']:>3}"
              f" purity={q['topic_purity']:.1%}"
              f" unique={q['unique_vocabulary']:>5}"
              f" rep={row['repetition_pressure']:.0%}"
              f" grade={q['overall']}")


if __name__ == "__main__":
    main()
