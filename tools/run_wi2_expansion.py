"""Large-scale dictionary/candidate expansion (WI2 Phase 2).

Funnel (spec PART F / PART AA):
  RAW -> lexical quality -> familiarity -> topic candidate ->
  multi-signal classification -> bands -> precision samples.

Read-only over production data; writes:
  - expanded store backup: word_intelligence_state backup copy
  - funnel report JSON in out/word_intelligence_reports/

Usage:
  python tools/run_wi2_expansion.py [--pilot N]
"""
from __future__ import annotations

import json
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
REPORT_DIR = ROOT / "out" / "word_intelligence_reports"
STATE_DIR = ROOT / "word_banks" / "word_intelligence"

MIN_ZIPF = 2.2          # familiarity floor (rare-but-real niche words keep in)
PILOT_DEFAULT = 2000


def load_catalog() -> dict:
    path = ROOT / "word_banks" / "source_data" / \
        "dwyl_topic_candidate_catalog.json"
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}


def main() -> None:
    args = sys.argv[1:]
    pilot = int(args[args.index("--pilot") + 1]) if "--pilot" in args else None

    from word_intelligence import pipeline
    from word_intelligence.classifier import Classifier
    from word_intelligence.normalization import clean_surface
    from word_intelligence.quality import PuzzleWorthiness, assess_quality
    from word_intelligence.store import DEFAULT_STATE_DIR, build_store

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()
    tax = pipeline.load_taxonomy(ROOT)
    loaded = build_store(ROOT, tax)
    store = loaded[0]
    funnel = {
        "generated_at": stamp,
        "raw_dictionary_entries": None,
        "records_before": len(store.records),
        "stage_lexical_pass": 0,
        "stage_familiarity_pass": 0,
        "stage_topic_candidate": 0,
        "classified": 0,
        "very_high": 0,
        "high": 0,
        "medium": 0,
        "low_or_floor": 0,
        "rejected_existing": len(store.records),
    }

    catalog = load_catalog()
    freq = {k.upper(): float(v)
            for k, v in (catalog.get("frequency_scores") or {}).items()}
    suggestions = catalog.get("suggestions_by_topic") or {}
    suggested_words = {w.upper() for ws in suggestions.values() for w in ws}

    dict_path = ROOT / "word_banks" / "source_data" / "dwyl_words_alpha.txt"
    raw = [ln.strip() for ln in dict_path.read_text(
        encoding="utf-8", errors="replace").splitlines() if ln.strip()]
    funnel["raw_dictionary_entries"] = len(raw)

    # --- Stage 1-3: evidence-based candidate selection ------------------
    # The store already contains every dictionary entry that carries real
    # evidence (zipf cache / curated membership).  The remaining alpha tail
    # has NO familiarity data - exactly the noise the spec says to reject,
    # so expansion targets the classified-but-unconfirmed pool instead of
    # blind raw ingestion.
    funnel["stage_lexical_pass"] = len(store.records)
    targets = []
    rejected_quality = 0
    for norm, record in sorted(store.records.items()):
        if not record.is_unclassified():
            continue
        quality = assess_quality(record)
        if quality.worthiness in (PuzzleWorthiness.EXCLUDE,
                                  PuzzleWorthiness.REVIEW):
            rejected_quality += 1
            continue
        if record.frequency is None:
            rejected_quality += 1     # unfamiliarity = cannot judge value
            continue
        targets.append(record)
    funnel["unclassified_before"] = sum(
        1 for r in store.records.values() if r.is_unclassified())
    funnel["quality_gate_pass"] = len(targets)
    funnel["rejected_by_quality_or_unknown_freq"] = rejected_quality
    if pilot:
        targets = targets[:pilot]

    # --- Stage 4: classification (candidate-narrowed indexes) -----------
    classifier = Classifier(store, tax)
    prep = classifier.prepare(catalog=catalog, themes_dir=ROOT / "themes")
    from word_intelligence.classifier import RunStats
    stats = RunStats()
    t1 = time.perf_counter()
    classifier.classify_many(targets, stats)
    elapsed = time.perf_counter() - t1

    from word_intelligence.records import PROPOSED, band_of
    for record in targets:
        best = ""
        for link in record.topics:
            if link.status == PROPOSED:
                b = band_of(link.confidence)
                best = b if b > best else best
        if best == "very_high":
            funnel["very_high"] += 1
        elif best == "high":
            funnel["high"] += 1
        elif best == "medium":
            funnel["medium"] += 1
        else:
            funnel["low_or_floor"] += 1
    funnel["classified"] = stats.words_classified
    funnel["classification_seconds"] = round(elapsed, 1)
    funnel["candidates_per_second"] = int(stats.words_seen / elapsed) if elapsed else 0
    funnel["prepare"] = prep
    funnel["errors_sample"] = stats.errors[:10]

    # --- Persist ---------------------------------------------------------
    backup = STATE_DIR / f"word_store.pre_expansion-{stamp}.json"
    src_store = STATE_DIR / "word_store.json"
    if src_store.exists():
        shutil.copyfile(src_store, backup)
        funnel["backup"] = backup.name
    store.save(DEFAULT_STATE_DIR)

    report_path = REPORT_DIR / f"wi2_expansion-{stamp}.json"
    with open(report_path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(funnel, handle, indent=1, ensure_ascii=False, default=str)
    print("WROTE", report_path)
    print(json.dumps({k: v for k, v in funnel.items()
                      if k != "errors_sample"}, indent=1))


if __name__ == "__main__":
    main()
