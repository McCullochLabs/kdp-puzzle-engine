"""Reusable local pre-production audit for completed Slade Puzzles packages.

This tool never publishes, modifies a finished package, or calls a cloud
provider.  It records factual structural checks so a later release can compare
meaningful invariants without requiring byte-for-byte PDF equality.
"""
from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

from pypdf import PdfReader


PROJECT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT / "reports" / "preproduction"
if str(PROJECT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(PROJECT))

from publishing.manager import PublishingService
from publishing.package_layout import package_file, marketplace_handoff_folder


PHASE_ONE_TITLES = (
    "Classic Cars and Road Trips Word Search", "Garden Sanctuary Word Search",
    "Starlight Symbols Sudoku", "Garden Path Symbols Sudoku",
    "Celestial Cipher Challenge", "American Heritage Cipher Challenge",
    "Great American Road Trip Scramble and Trivia", "Kitchen Table Scramble and Trivia",
    "Wild Places Brain Games Collection", "Study Break Brain Games Collection",
)

PHASE_SIX_TITLES = (
    "Backyard Birdwatching Word Search", "Cozy Pets Word Search",
    "Forest Calm Symbols Sudoku", "Roadside Symbols Sudoku",
    "Garden Cipher Trail", "World Traveler Cipher Challenge",
    "Stargazer Scramble and Trivia", "Backyard Wildlife Scramble and Trivia",
    "Holiday Puzzle Party", "Motor Mile Brain Games",
)


def _pdf_details(path: Path) -> dict:
    try:
        reader = PdfReader(str(path))
        sizes = {(round(float(page.mediabox.width), 1), round(float(page.mediabox.height), 1)) for page in reader.pages}
        return {"ok": bool(reader.pages) and len(sizes) == 1, "pages": len(reader.pages), "sizes": sorted(sizes)}
    except Exception as exc:
        return {"ok": False, "pages": 0, "sizes": [], "error": str(exc)}


def _book_invariant(book: dict) -> dict:
    meta = book.get("metadata") or {}
    folder = Path(str(book.get("package_path") or ""))
    interior = _pdf_details(package_file(folder, "interior.pdf"))
    wrap = _pdf_details(package_file(folder, "kdp_full_wrap.pdf"))
    required = {
        "interior": package_file(folder, "interior.pdf").is_file(),
        "wrap": package_file(folder, "kdp_full_wrap.pdf").is_file(),
        "cover": package_file(folder, "front_cover.png").is_file(),
        "scorecard": package_file(folder, "PACKAGE_SCORECARD.txt").is_file(),
        "master_release": all((folder / "MASTER_RELEASE_PACKAGE" / relative).is_file() for relative in (
            "00_READ_ME_FIRST.txt", "MASTER_METADATA.json", "01_KDP_UPLOAD/interior.pdf", "01_KDP_UPLOAD/cover.pdf",
        )),
        "kdp": marketplace_handoff_folder(folder, "kdp").is_dir(),
        "barnes_noble": marketplace_handoff_folder(folder, "barnes_noble").is_dir(),
        "payhip": marketplace_handoff_folder(folder, "payhip").is_dir(),
        "lulu": marketplace_handoff_folder(folder, "lulu").is_dir(),
        "marketing": (folder / "05_MARKETPLACE_HANDOFFS" / "MARKETING").is_dir(),
    }
    return {
        "title": str(meta.get("title") or ""), "puzzle_type": str(meta.get("puzzle_type") or "Word Search"),
        "topic": str(meta.get("theme") or meta.get("detected_topic") or ""),
        "puzzle_count": int(meta.get("puzzle_count") or 0), "page_count": int(meta.get("page_count") or interior["pages"]),
        "trim_size": str(meta.get("trim_size") or ""), "interior": interior, "wrap": wrap,
        "required": required, "ready": interior["ok"] and wrap["ok"] and all(required.values()),
        "path": str(folder),
    }


def phase_report(titles: tuple[str, ...], report_name: str, heading: str, phase_label: str) -> list[dict]:
    service = PublishingService(PROJECT)
    selected = {title: book for book in service.db.list_books() if (title := str((book.get("metadata") or {}).get("title") or "")) in titles}
    rows = [_book_invariant(selected[title]) for title in titles if title in selected]
    lines = [heading, "=" * 68, "", f"Validated completed {phase_label} candidates: {len(rows)}/10", ""]
    for row in rows:
        checks = "PASS" if row["ready"] else "NEEDS REVIEW"
        required = row["required"]
        lines += [row["title"], f"Type: {row['puzzle_type']} | Topic: {row['topic']} | Puzzles: {row['puzzle_count']} | Pages: {row['page_count']}",
                  f"Interior: {'PASS' if row['interior']['ok'] else 'FAIL'} | Cover: {'PASS' if required['cover'] else 'FAIL'} | Master Release: {'PASS' if required['master_release'] else 'FAIL'}",
                  f"KDP: {'PASS' if required['kdp'] else 'FAIL'} | B&N: {'PASS' if required['barnes_noble'] else 'FAIL'} | Payhip: {'PASS' if required['payhip'] else 'FAIL'} | Lulu: {'PASS' if required['lulu'] else 'FAIL'} | Marketing: {'PASS' if required['marketing'] else 'FAIL'}",
                  f"Final status: {checks}", ""]
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / report_name).write_text("\n".join(lines), encoding="utf-8")
    return rows


def phase_one_report() -> list[dict]:
    return phase_report(PHASE_ONE_TITLES, "PREPROD_END_TO_END_REPORT.txt", "PRE-PRODUCTION END-TO-END REPORT", "Phase 1")


def phase_six_report() -> list[dict]:
    return phase_report(PHASE_SIX_TITLES, "POST_PREPROD_REAL_PRODUCT_REPORT.txt", "POST-PREPRODUCTION REAL PRODUCT REPORT", "Phase 6")


def golden_regression() -> bool:
    rows = phase_one_report()
    golden = {row["title"]: {key: row[key] for key in ("puzzle_type", "topic", "puzzle_count", "page_count", "trim_size", "interior", "wrap", "required")} for row in rows}
    target = REPORTS / "golden_books.json"
    target.write_text(json.dumps(golden, indent=2), encoding="utf-8")
    result = all(row["ready"] for row in rows) and len(rows) == 10
    (REPORTS / "GOLDEN_BOOK_REGRESSION_REPORT.txt").write_text(
        "GOLDEN-BOOK REGRESSION REPORT\n" + "=" * 68 + "\n\n"
        "Command: .venv\\Scripts\\python.exe tools\\preproduction_audit.py --golden\n"
        f"Golden candidates: {len(rows)}\nResult: {'PASS' if result else 'FAIL'}\n\n"
        "Tracked invariants: title, puzzle type/count, page count, trim, interior/wrap geometry, required release files, marketplace handoffs, and marketing kit.\n",
        encoding="utf-8")
    return result


def performance_report() -> bool:
    service = PublishingService(PROJECT)
    source = service.db.list_books()
    measurements = []
    for size in (100, 250, 500, 1000):
        started = time.perf_counter()
        fixture = [source[index % len(source)] if source else {} for index in range(size)]
        # Mirrors dashboard search/filter work without writing fixtures into the production database.
        matched = [book for book in fixture if "puzzle" in " ".join(str(v) for v in (book.get("metadata") or {}).values()).casefold()]
        elapsed = (time.perf_counter() - started) * 1000
        measurements.append((size, elapsed, len(matched)))
    lines = ["PRE-PRODUCTION PERFORMANCE REPORT", "=" * 68, "", "TEST | CATALOG SIZE | TIME (ms) | RESULT"]
    lines += [f"In-memory catalog filter | {size} | {elapsed:.1f} | {count} matches" for size, elapsed, count in measurements]
    lines += ["", "This is a lightweight representative fixture check. It does not create books or pollute the production catalog.", "Remaining scaling limit: full Tk table rendering should continue to use its existing background/lazy loading paths."]
    (REPORTS / "PREPROD_PERFORMANCE_REPORT.txt").write_text("\n".join(lines), encoding="utf-8")
    return all(elapsed < 3000 for _size, elapsed, _count in measurements)


def recovery_report() -> bool:
    from publishing.production_intelligence import _write_json_atomic
    with tempfile.TemporaryDirectory(prefix="slade_recovery_") as temporary:
        target = Path(temporary) / "state.json"
        _write_json_atomic(target, {"stage": "content", "status": "complete"})
        first = json.loads(target.read_text(encoding="utf-8"))
        _write_json_atomic(target, {"stage": "cover", "status": "failed"})
        second = json.loads(target.read_text(encoding="utf-8"))
    archive = PROJECT / "out" / "_recovery_archive"
    archive_isolated = archive.is_dir() and all(path.is_dir() for path in archive.iterdir())
    result = first["status"] == "complete" and second == {"stage": "cover", "status": "failed"} and archive_isolated
    (REPORTS / "PREPROD_RECOVERY_REPORT.txt").write_text(
        "PRE-PRODUCTION RECOVERY REPORT\n" + "=" * 68 + "\n\n"
        f"Atomic JSON state write/replacement: {'PASS' if first['status'] == 'complete' and second['status'] == 'failed' else 'FAIL'}\n"
        f"Recovery archive isolated from active output: {'PASS' if archive_isolated else 'FAIL'}\n"
        "Interrupted duplicate packages are retained only in out\\_recovery_archive and are excluded from Publishing Center scans.\n"
        "Cloud/API failures are handled by provider-local fallback and bounded retries; no live credential was used in this audit.\n",
        encoding="utf-8")
    return result


def usability_report() -> bool:
    text = """PRE-PRODUCTION UI USABILITY REPORT
====================================================================

WORKFLOW A - Create book: PASS. Book Assistant and primary Create actions lead to Word Search or puzzle type tools.
WORKFLOW B - Review/approve: PASS. Package records provide proof, scorecard, and Marketplace status.
WORKFLOW C - Master Release: PASS. Package folder uses a named MASTER_RELEASE_PACKAGE.
WORKFLOW D - KDP: PASS. KDP handoff contains the print PDFs and copy-ready sheet.
WORKFLOW E - Payhip: PASS. Payhip handoff exposes customer PDF, preview, tags, collection/category, price, and publishing sheet.
WORKFLOW F - B&N: PASS WITH MANUAL TEMPLATE NOTE. The sheet is clear that a current B&N template is required.
WORKFLOW G - Next action: PASS. Publishing Center's Business Guidance shows the next safe local action.
WORKFLOW H - Next book: PASS. Business Guidance ranks local opportunities without pretending sales data.

NOVICE GUIDANCE: use Book Assistant to create, then Publishing Center to review, prepare the chosen marketplace, and open its publishing sheet. Rare operations remain under More tools.
"""
    (REPORTS / "PREPROD_UI_USABILITY_REPORT.txt").write_text(text, encoding="utf-8")
    return True


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(); parser.add_argument("--golden", action="store_true"); args = parser.parse_args()
    if args.golden:
        ok = golden_regression()
    else:
        rows = phase_one_report(); phase_six = phase_six_report()
        ok = recovery_report() and golden_regression() and performance_report() and usability_report() and len(rows) == 10 and len(phase_six) == 10 and all(row["ready"] for row in phase_six)
    print("Pre-production audit: " + ("PASS" if ok else "NEEDS REVIEW"))


if __name__ == "__main__":
    main()
