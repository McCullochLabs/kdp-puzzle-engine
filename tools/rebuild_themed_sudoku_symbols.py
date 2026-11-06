"""Safely migrate active Sudoku packages to topic-aware symbol pages."""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pypdf
from publishing.package_layout import package_file
from puzzle_book_studio import listing, make_interior, production_proof_gate
from sudoku_symbols import pack_label, symbol_pack_for_theme


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def job_seeds() -> dict[str, set[int]]:
    found: dict[str, set[int]] = {}
    for path in (ROOT / "data" / "production_jobs").glob("*.json"):
        try:
            context = json.loads(path.read_text(encoding="utf-8")).get("context") or {}
            title = str(context.get("title") or "").strip()
            seed = int(context.get("puzzle_seed"))
            if title: found.setdefault(title, set()).add(seed)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            continue
    return found


def main() -> None:
    seeds = job_seeds()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_root = ROOT / "out" / "_recovery_archive" / f"sudoku_symbol_migration_{stamp}"
    temp_root = ROOT / "tmp" / "pdfs" / f"sudoku_symbol_migration_{stamp}"
    temp_root.mkdir(parents=True, exist_ok=True)
    results = []

    for record_path in sorted((ROOT / "out").glob("*/04_REVIEW_AND_RECORDS/PACKAGE_SOURCE_RECORD.json")):
        record = json.loads(record_path.read_text(encoding="utf-8"))
        if record.get("puzzle_type") != "Sudoku":
            continue
        folder = record_path.parents[1]
        theme = str(record.get("theme") or "General Starter")
        pack = symbol_pack_for_theme(theme)
        # A general book intentionally retains the classic symbols.
        if pack == "classic":
            results.append({"title": record.get("title"), "status": "unchanged", "pack": pack})
            continue
        title = str(record.get("title") or "")
        seed_values = seeds.get(title, set())
        seed = record.get("puzzle_seed")
        if seed is None and len(seed_values) == 1:
            seed = next(iter(seed_values))
        if seed is None:
            results.append({"title": title, "status": "blocked", "reason": "original seed was not recoverable"})
            continue

        primary = package_file(folder, "interior.pdf")
        if not primary.is_file():
            results.append({"title": title, "status": "blocked", "reason": "primary interior is missing"})
            continue
        old_pages = len(pypdf.PdfReader(str(primary)).pages)
        old_sha = sha(primary)
        candidate = temp_root / f"{folder.name}_interior.pdf"
        make_interior("Sudoku", title, str(record.get("subtitle") or ""), str(record.get("author") or ""),
                      int(record.get("puzzle_count") or 0), str(record.get("difficulty") or "Mixed"),
                      int(seed), candidate, theme, str(record.get("interior_style") or "Studio Classic"),
                      list(record.get("reader_bonus_pages") or []))
        new_pages = len(pypdf.PdfReader(str(candidate)).pages)
        if new_pages != old_pages:
            results.append({"title": title, "status": "blocked", "reason": f"page count changed from {old_pages} to {new_pages}"})
            candidate.unlink(missing_ok=True)
            continue

        backup = backup_root / folder.name
        backup.mkdir(parents=True, exist_ok=True)
        shutil.copy2(primary, backup / "interior_before_symbol_migration.pdf")
        shutil.copy2(record_path, backup / "PACKAGE_SOURCE_RECORD_before.json")

        replaced = []
        for pdf in folder.rglob("*.pdf"):
            try:
                if sha(pdf) == old_sha:
                    shutil.copy2(candidate, pdf)
                    replaced.append(str(pdf.relative_to(folder)))
            except OSError:
                continue
        record["puzzle_seed"] = int(seed)
        record["sudoku_symbol_pack"] = pack
        record["symbol_pack_label"] = pack_label(pack)
        record["symbol_migration_at"] = datetime.now().isoformat(timespec="seconds")
        record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")

        package_file(folder, "KDP_LISTING_KIT.txt", for_write=True).write_text(
            listing("Sudoku", title, str(record.get("subtitle") or ""), str(record.get("author") or ""),
                    int(record.get("puzzle_count") or 0), str(record.get("difficulty") or "Mixed"),
                    new_pages, theme), encoding="utf-8")
        plan = package_file(folder, "AUTOMATIC_BOOK_PLAN.txt", for_write=True)
        if plan.is_file():
            text = plan.read_text(encoding="utf-8")
            if "Sudoku symbol pack:" not in text:
                text = text.rstrip() + f"\nSudoku symbol pack: {pack_label(pack).title()}\n"
            plan.write_text(text, encoding="utf-8")

        proof_ok, proof_text = production_proof_gate(folder, "Sudoku", title, str(record.get("subtitle") or ""),
                                                     int(record.get("puzzle_count") or 0), new_pages)
        package_file(folder, "PRODUCTION_PROOF_GATE.txt", for_write=True).write_text(proof_text, encoding="utf-8")
        results.append({"title": title, "status": "rebuilt" if proof_ok else "needs_review", "pack": pack,
                        "pages": new_pages, "copies_replaced": len(replaced), "files": replaced})
        candidate.unlink(missing_ok=True)

    report = ROOT / "reports" / "sudoku_symbol_migration_report.json"
    report.write_text(json.dumps({"created": datetime.now().isoformat(timespec="seconds"),
                                  "backup": str(backup_root), "results": results}, indent=2) + "\n", encoding="utf-8")
    print(report)
    for item in results:
        print(f"{item['status']:12} {item.get('pack','-'):15} {item['title']}")


if __name__ == "__main__":
    main()
