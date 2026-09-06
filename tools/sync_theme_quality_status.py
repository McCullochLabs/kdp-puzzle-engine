"""Persist the latest Word Intelligence fail status into legacy source themes.

This is a safety bridge: a theme that fails the deep content audit receives a
small, readable ``quality_review`` marker so the normal final package gate can
stop it.  Existing files are backed up before any marker is written.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    reports = sorted((ROOT / "out" / "word_intelligence_reports").glob("wi2_validation-*.json"))
    if not reports:
        raise SystemExit("No Word Intelligence validation report was found.")
    report_path = reports[-1]
    report = json.loads(report_path.read_text(encoding="utf-8"))
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_root = ROOT / "backups" / "theme_quality_status" / stamp
    marked = 0
    for item in report.get("themes", []):
        if item.get("verdict") != "FAIL":
            continue
        path = Path(str(item.get("file") or ""))
        if not path.exists() or path.suffix.lower() != ".json":
            continue
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        review = data.get("quality_review") if isinstance(data.get("quality_review"), dict) else {}
        if review.get("production_ready") is False and review.get("verdict") == "FAIL":
            continue
        relative = path.relative_to(ROOT)
        backup = backup_root / relative
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup)
        data["quality_review"] = {
            "checked_at": stamp,
            "source": report_path.name,
            "verdict": "FAIL",
            "production_ready": False,
            "message": "This legacy word bank needs a curated topic rebuild before production.",
        }
        temporary = path.with_suffix(path.suffix + ".quality-status.tmp")
        temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        temporary.replace(path)
        marked += 1
    print(f"Marked {marked} legacy theme(s) as needing curated content review.")
    print(f"Backups: {backup_root}")


if __name__ == "__main__":
    main()
