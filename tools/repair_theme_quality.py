"""Repair theme word banks from the verified Word Intelligence pools.

This tool is intentionally conservative in its default mode: it only writes
when ``--apply`` is supplied, creates a dated backup of every edited JSON file,
and records a plain-English report.  It is designed for the legacy themes that
pre-date the current topic and safety checks.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json_atomic(path: Path, data: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".quality-repair.tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                         encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair legacy theme word banks safely")
    parser.add_argument("--apply", action="store_true", help="write safe repairs after making backups")
    parser.add_argument("--limit", type=int, default=0, help="process at most this many failing themes")
    parser.add_argument("--offset", type=int, default=0, help="skip this many failures (for safe, resumable batches)")
    parser.add_argument("--validation-report", default="", help="optional saved wi2_validation report; avoids re-auditing every theme")
    args = parser.parse_args()

    from word_intelligence.pipeline import load_or_build_store, load_taxonomy
    from word_intelligence.repair import (apply_plan, build_topic_member_index,
                                          plan_theme_repairs, production_readiness)
    from word_intelligence.theme_audit import VERDICT_FAIL, audit_theme

    taxonomy = load_taxonomy(ROOT)
    loaded = load_or_build_store(taxonomy, ROOT)
    store = loaded[0] if isinstance(loaded, tuple) else loaded
    member_index = build_topic_member_index(store, taxonomy)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_root = ROOT / "backups" / "theme_quality_repair" / stamp
    report_root = ROOT / "out" / "word_intelligence_reports"
    report_root.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    failing: list[Path] = []
    report_candidates = sorted((ROOT / "out" / "word_intelligence_reports").glob("wi2_validation-*.json"))
    source_report = Path(args.validation_report) if args.validation_report else (report_candidates[-1] if report_candidates else None)
    if source_report and source_report.exists():
        try:
            validation = json.loads(source_report.read_text(encoding="utf-8"))
            failing = [Path(item["file"]) for item in validation.get("themes", [])
                       if item.get("verdict") == VERDICT_FAIL and Path(item.get("file", "")).exists()]
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            rows.append({"file": str(source_report), "outcome": "validation_report_unreadable", "detail": str(exc)})
    if not failing:
        for path in sorted((ROOT / "themes").rglob("*.json")):
            try:
                data = load_json(path)
                report = audit_theme(data, str(path), store, taxonomy)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                rows.append({"file": str(path.relative_to(ROOT)), "outcome": "unreadable", "detail": str(exc)})
                continue
            if report.verdict == VERDICT_FAIL:
                failing.append(path)
                # A limited run is a true fast preflight: do not spend a minute
                # auditing the rest of the library merely to test three repairs.
                if args.limit and len(failing) >= args.limit:
                    break
    if args.offset:
        failing = failing[max(0, args.offset):]
    if args.limit:
        failing = failing[:args.limit]
    for path in failing:
        relative = path.relative_to(ROOT)
        data = load_json(path)
        before = audit_theme(data, str(path), store, taxonomy)
        plan = plan_theme_repairs(data, str(path), store, taxonomy, member_index)
        row = {
            "file": str(relative), "title": str(data.get("title") or path.stem),
            "before": before.verdict, "tier": plan.tier,
            "replacements": plan.replacement_count, "unresolved": len(plan.unresolved),
        }
        if not plan.replacements or plan.unresolved:
            row.update({"outcome": "needs_curated_rebuild", "detail": "; ".join(plan.blockers) or "No verified replacement pool"})
            rows.append(row)
            continue
        try:
            repaired, changes = apply_plan(data, plan)
        except ValueError as exc:
            row.update({"outcome": "needs_curated_rebuild", "detail": str(exc)})
            rows.append(row)
            continue
        after = audit_theme(repaired, str(path), store, taxonomy)
        ready = production_readiness(repaired, str(path), store, taxonomy)
        row.update({"after": after.verdict, "ready": bool(ready["ready"]), "changes": len(changes)})
        if after.verdict == VERDICT_FAIL:
            row.update({"outcome": "needs_curated_rebuild", "detail": "Verified replacements improved the bank, but it still fails the quality gate."})
            rows.append(row)
            continue
        row["outcome"] = "repaired" if ready["ready"] else "repaired_needs_review"
        if args.apply:
            backup_path = backup_root / relative
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, backup_path)
            quality = repaired.setdefault("quality_review", {})
            quality.update({
                "checked_at": stamp,
                "source": "verified_word_intelligence_repair",
                "verdict": after.verdict,
                "production_ready": bool(ready["ready"]),
                "changes": len(changes),
            })
            write_json_atomic(path, repaired)
        rows.append(row)

    summary = {
        "generated_at": stamp, "mode": "apply" if args.apply else "dry_run",
        "themes_failed_before": len(failing),
        "repaired": sum(row.get("outcome") == "repaired" for row in rows),
        "needs_review": sum(row.get("outcome") == "repaired_needs_review" for row in rows),
        "needs_curated_rebuild": sum(row.get("outcome") == "needs_curated_rebuild" for row in rows),
        "rows": rows,
        "backup_folder": str(backup_root) if args.apply else "",
    }
    report_path = report_root / f"theme_quality_repair-{stamp}.json"
    report_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items() if key != "rows"}, indent=2))
    print(f"REPORT {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
