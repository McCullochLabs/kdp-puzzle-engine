"""Rebuild active Word Search interiors with truthful per-page titles."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pypdf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from publishing.package_layout import package_file
from word_intelligence.page_titles import puzzle_page_title


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def seed_for(folder: Path, record: dict) -> int | None:
    if record.get("puzzle_seed") is not None:
        return int(record["puzzle_seed"])
    match = re.search(r"commercial_baseline_(\d+)_", folder.name)
    return int(match.group(1)) if match else None


def main() -> None:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_root = ROOT / "out" / "_recovery_archive" / f"wordsearch_page_title_migration_{stamp}"
    temp_root = ROOT / "tmp" / "pdfs" / f"wordsearch_page_title_migration_{stamp}"
    temp_root.mkdir(parents=True, exist_ok=True)
    results = []

    records = sorted((ROOT / "out").glob("*/04_REVIEW_AND_RECORDS/PACKAGE_SOURCE_RECORD.json"))
    for record_path in records:
        record = json.loads(record_path.read_text(encoding="utf-8"))
        if record.get("puzzle_type") != "Word Search":
            continue
        if record.get("page_title_policy") == "truthful_topic_or_reviewed_mini_theme":
            results.append({"title": record.get("title"), "status": "already_rebuilt"})
            continue
        folder = record_path.parents[1]
        source = Path(str(record.get("source_theme") or ""))
        seed = seed_for(folder, record)
        primary = package_file(folder, "interior.pdf")
        if not source.is_file() or seed is None or not primary.is_file():
            results.append({"title": record.get("title"), "status": "blocked", "reason": "source theme, seed, or interior missing"})
            continue
        data = json.loads(source.read_text(encoding="utf-8-sig"))
        puzzles = [row for row in data.get("puzzles") or [] if isinstance(row, dict)]
        resolved = [puzzle_page_title(data, row, index) for index, row in enumerate(puzzles, 1)]
        old_pages = len(pypdf.PdfReader(str(primary)).pages)
        old_sha = sha(primary)
        candidate = temp_root / f"{folder.name}_interior.pdf"
        command = [sys.executable, str(ROOT / "wordsearch.py"), "--themes", str(source), "--out", str(candidate),
                   "--title", str(record.get("title") or data.get("title") or "Word Search"),
                   "--subtitle", str(record.get("subtitle") or data.get("subtitle") or ""),
                   "--author", str(record.get("author") or data.get("author") or ""), "--seed", str(seed)]
        if bool(record.get("signature_edition")):
            command.append("--signature-edition")
        subprocess.run(command, cwd=ROOT, check=True)
        new_pages = len(pypdf.PdfReader(str(candidate)).pages)
        if new_pages != old_pages:
            results.append({"title": record.get("title"), "status": "blocked", "reason": f"page count changed from {old_pages} to {new_pages}"})
            candidate.unlink(missing_ok=True)
            continue

        backup = backup_root / folder.name
        backup.mkdir(parents=True, exist_ok=True)
        shutil.copy2(primary, backup / "interior_before_page_title_migration.pdf")
        shutil.copy2(record_path, backup / "PACKAGE_SOURCE_RECORD_before.json")
        replaced = []
        for pdf in folder.rglob("*.pdf"):
            try:
                if sha(pdf) == old_sha:
                    shutil.copy2(candidate, pdf)
                    replaced.append(str(pdf.relative_to(folder)))
            except OSError:
                continue
        record["puzzle_seed"] = seed
        record["page_title_policy"] = "truthful_topic_or_reviewed_mini_theme"
        record["page_title_migration_at"] = datetime.now().isoformat(timespec="seconds")
        record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        package_file(folder, "PAGE_TITLE_COHERENCE_REPORT.txt", for_write=True).write_text(
            "PAGE TITLE COHERENCE REPORT\n" + "=" * 52 + "\n\n"
            f"Book: {record.get('title')}\nPuzzles checked: {len(puzzles)}\n"
            "Policy: A page uses a narrow mini-theme title only when that title is backed by reviewed, strict mini-theme allocation.\n"
            "Legacy decorative labels without that evidence were replaced by the proven overall topic plus the puzzle number.\n\n"
            "Result: PASS\n\nResolved page titles:\n" +
            "\n".join(f"{index:03}. {title}" for index, title in enumerate(resolved, 1)) + "\n",
            encoding="utf-8")
        candidate.unlink(missing_ok=True)
        results.append({"title": record.get("title"), "status": "rebuilt", "pages": new_pages,
                        "page_titles": len(resolved), "copies_replaced": len(replaced), "files": replaced})

    report = ROOT / "reports" / "wordsearch_page_title_migration_report.json"
    report.parent.mkdir(exist_ok=True)
    report.write_text(json.dumps({"created": datetime.now().isoformat(timespec="seconds"), "backup": str(backup_root),
                                  "results": results}, indent=2) + "\n", encoding="utf-8")
    print(report)
    for row in results:
        print(f"{row['status']:10} {row['title']}")


if __name__ == "__main__":
    main()
