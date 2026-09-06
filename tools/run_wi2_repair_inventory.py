"""Dry-run repair-plan inventory over the real theme library (PART M).

Read-only: never applies repairs, never writes production themes.  Writes
the comparison report into out/word_intelligence_reports/.
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

PREVIOUS_DISTRIBUTION = {"auto": 2, "review": 57,
                         "approval_required": 22, "blocked": 55}


def main() -> None:
    from word_intelligence.pipeline import load_or_build_store, load_taxonomy
    from word_intelligence.repair import build_inventory

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    tax = load_taxonomy(ROOT)
    loaded = load_or_build_store(tax, ROOT)
    store = loaded[0] if isinstance(loaded, tuple) else loaded

    t0 = time.perf_counter()
    inventory = build_inventory(ROOT / "themes", store, tax)
    seconds = round(time.perf_counter() - t0, 1)

    # Disposition distribution straight from the inventory entries.
    dispositions: dict[str, int] = {}
    for entry in inventory.get("themes", []):
        d = entry.get("disposition", "")
        dispositions[d] = dispositions.get(d, 0) + 1

    # Repair-tier distribution: dry-run planning for every theme that is
    # NOT retained (spec PART M).  Never applies anything.
    from word_intelligence.repair import plan_theme_repairs, \
        build_topic_member_index
    tiers: dict[str, int] = {}
    replacement_total = 0
    unresolved_total = 0
    planned = 0
    member_index = build_topic_member_index(store, tax)
    for entry in inventory.get("themes", []):
        if entry.get("disposition") == "retain":
            continue
        theme_path = ROOT / "themes" / entry["file"]
        try:
            data = json.loads(theme_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        plan = plan_theme_repairs(data, str(theme_path), store, tax,
                                  member_index=member_index)
        planned += 1
        tiers[plan.tier] = tiers.get(plan.tier, 0) + 1
        replacement_total += len(plan.replacements)
        unresolved_total += len(plan.unresolved)

    payload = {
        "generated_at": stamp,
        "seconds": seconds,
        "previous_distribution": PREVIOUS_DISTRIBUTION,
        "new_distribution": tiers,
        "dispositions": dispositions,
        "planned_themes": planned,
        "replacement_total": replacement_total,
        "unresolved_replacements": unresolved_total,
        "verdicts": inventory.get("verdict_counts"),
        "cause_totals": inventory.get("finding_cause_totals"),
        "themes_scanned": inventory.get("themes_scanned"),
    }
    path = REPORT_DIR / f"wi2_repair_tiers-{stamp}.json"
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=1, ensure_ascii=False, default=str)
    print("WROTE", path)
    print("TIERS", json.dumps(tiers))
    print("DISPOSITIONS", json.dumps(dispositions))


if __name__ == "__main__":
    main()
