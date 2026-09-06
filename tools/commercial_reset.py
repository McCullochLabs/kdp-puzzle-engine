"""Create an auditable clean-production reset without touching source assets.

Run without arguments to capture the reset manifest.  Run with --apply only after
reviewing that manifest.  The tool intentionally preserves themes, word banks,
background assets, credentials, user preferences, production history, and any
catalog rows that carry an Uploaded or Published marketplace status.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT = Path(__file__).resolve().parents[1]
OUT = PROJECT / "out"
DATA = PROJECT / "data"
REPORTS = PROJECT / "reports"
DB = DATA / "books.db"
MANIFEST_JSON = REPORTS / "PRE_PRODUCTION_RESET_MANIFEST.json"
MANIFEST_TEXT = REPORTS / "PRE_PRODUCTION_RESET_MANIFEST.txt"
RESET_JSON = REPORTS / "PRODUCTION_RESET_REPORT.json"
RESET_TEXT = REPORTS / "PRODUCTION_RESET_REPORT.txt"
PROTECTED_STATUSES = {"Uploaded", "Published"}


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT.resolve()))
    except ValueError:
        return str(path)


def package_summary(folder: Path) -> dict[str, Any]:
    """Read only minimal package facts from the various supported layouts."""
    result: dict[str, Any] = {"path": relative(folder), "kind": "directory"}
    manifest_paths = list(folder.rglob("PACKAGE_SOURCE_RECORD.json"))
    if manifest_paths:
        raw = read_json(manifest_paths[0])
        if isinstance(raw, dict):
            result["source_record"] = relative(manifest_paths[0])
            for key in ("title", "puzzle_type", "book_type", "interior_pages", "pages", "ready"):
                if key in raw:
                    result[key] = raw[key]
    release_paths = list(folder.rglob("RELEASE_CONTRACT.json"))
    if release_paths:
        raw = read_json(release_paths[0])
        if isinstance(raw, dict):
            result["release_contract"] = relative(release_paths[0])
            result["release_ready"] = bool(raw.get("ready", False))
    result["file_count"] = sum(1 for candidate in folder.rglob("*") if candidate.is_file())
    return result


def build_manifest() -> dict[str, Any]:
    REPORTS.mkdir(exist_ok=True)
    out_items: list[dict[str, Any]] = []
    if OUT.exists():
        for item in sorted(OUT.iterdir(), key=lambda candidate: candidate.name.lower()):
            if item.is_symlink():
                out_items.append({"path": relative(item), "kind": "symlink", "reset_safe": False})
            elif item.is_dir():
                details = package_summary(item)
                details["reset_safe"] = True
                out_items.append(details)
            else:
                out_items.append({"path": relative(item), "kind": "file", "reset_safe": False})

    catalog: list[dict[str, Any]] = []
    protected: list[str] = []
    if DB.exists():
        connection = sqlite3.connect(DB)
        try:
            rows = connection.execute(
                "SELECT book_id, source_key, package_path, metadata_json FROM books ORDER BY created_at"
            ).fetchall()
            for book_id, source_key, package_path, metadata_json in rows:
                statuses = connection.execute(
                    "SELECT marketplace, status FROM marketplace_status WHERE book_id=? ORDER BY marketplace",
                    (book_id,),
                ).fetchall()
                under_out = False
                if package_path:
                    try:
                        Path(package_path).resolve().relative_to(OUT.resolve())
                        under_out = True
                    except (ValueError, OSError):
                        pass
                if source_key.startswith("package:"):
                    under_out = True
                if not under_out:
                    continue
                metadata = read_json(Path("not-a-file"))
                try:
                    metadata = json.loads(metadata_json)
                except (TypeError, json.JSONDecodeError):
                    metadata = {}
                row = {
                    "book_id": book_id,
                    "source_key": source_key,
                    "package_path": package_path,
                    "title": metadata.get("title", ""),
                    "marketplace_statuses": {market: status for market, status in statuses},
                    "protected": any(status in PROTECTED_STATUSES for _, status in statuses),
                }
                catalog.append(row)
                if row["protected"]:
                    protected.append(book_id)
        finally:
            connection.close()

    state_files = [
        PROJECT / "release_catalog.json",
        PROJECT / "launch_batch_tracker.json",
        PROJECT / "production_lock.json",
        DATA / "production_ledger.json",
        PROJECT / "production_history.json",
        DATA / "word_reservations.json",
        PROJECT / "recent_themes.json",
    ]
    state = []
    for path in state_files:
        value = read_json(path) if path.exists() else None
        state.append({
            "path": relative(path),
            "exists": path.exists(),
            "json_kind": type(value).__name__ if value is not None else "unreadable_or_missing",
            "entries": len(value) if isinstance(value, (dict, list)) else None,
        })
    checkpoints = sorted(DATA.joinpath("production_autopilot").glob("*.json")) if DATA.joinpath("production_autopilot").exists() else []

    return {
        "created_at": now(),
        "project": str(PROJECT),
        "database_sha256": sha256(DB) if DB.exists() else "",
        "out_items": out_items,
        "catalog_rows_linked_to_out": catalog,
        "protected_catalog_book_ids": protected,
        "state_files": state,
        "autopilot_checkpoints": [relative(path) for path in checkpoints],
        "preserved": [
            "themes and word banks",
            "cover/background assets and rights ledger",
            "credentials and user preferences",
            "production_history.json and word_reservations.json for repeat prevention",
            "any catalog row with Uploaded or Published marketplace status",
            "marketplace audit history",
        ],
        "planned_reset": [
            "top-level generated folders in out/ that are not symlinks",
            "unprotected catalog rows linked to old out/ packages",
            "unprotected queue and release-lock records linked to those rows",
            "release catalog, launch tracker, production lock, production ledger, and autopilot checkpoints",
        ],
    }


def write_manifest(manifest: dict[str, Any]) -> None:
    MANIFEST_JSON.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    lines = [
        "PRE-PRODUCTION RESET MANIFEST",
        f"Created (UTC): {manifest['created_at']}",
        f"Database SHA-256: {manifest['database_sha256']}",
        "",
        f"Generated out/ items scheduled for reset: {len(manifest['out_items'])}",
    ]
    for item in manifest["out_items"]:
        lines.append(f"- {item['path']} [{item['kind']}] reset_safe={item['reset_safe']}")
    lines.extend(["", f"Catalog rows linked to out/: {len(manifest['catalog_rows_linked_to_out'])}"])
    for row in manifest["catalog_rows_linked_to_out"]:
        lines.append(f"- {row['title'] or row['book_id']} | protected={row['protected']} | {row['package_path']}")
    lines.extend(["", "Preserved:"])
    lines.extend(f"- {entry}" for entry in manifest["preserved"])
    MANIFEST_TEXT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def reset_json_file(path: Path) -> None:
    current = read_json(path)
    if isinstance(current, list):
        replacement: Any = []
    elif isinstance(current, dict):
        replacement = {}
    else:
        replacement = {}
    path.write_text(json.dumps(replacement, indent=2) + "\n", encoding="utf-8")


def apply_reset(manifest: dict[str, Any]) -> dict[str, Any]:
    unsafe = [item["path"] for item in manifest["out_items"] if not item["reset_safe"]]
    if unsafe:
        raise RuntimeError("Reset stopped: unexpected files or symlinks in out/: " + ", ".join(unsafe))

    removed_folders: list[str] = []
    for item in OUT.iterdir() if OUT.exists() else []:
        if item.is_dir() and not item.is_symlink():
            shutil.rmtree(item)
            removed_folders.append(relative(item))

    removed_books: list[str] = []
    preserved_books: list[str] = []
    connection = sqlite3.connect(DB)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        rows = connection.execute("SELECT book_id, source_key, package_path FROM books").fetchall()
        for book_id, source_key, package_path in rows:
            under_out = source_key.startswith("package:")
            if package_path:
                try:
                    Path(package_path).resolve().relative_to(OUT.resolve())
                    under_out = True
                except (ValueError, OSError):
                    pass
            if not under_out:
                continue
            statuses = {status for (status,) in connection.execute(
                "SELECT status FROM marketplace_status WHERE book_id=?", (book_id,)
            )}
            if statuses & PROTECTED_STATUSES:
                preserved_books.append(book_id)
                continue
            connection.execute("DELETE FROM approved_production_queue WHERE book_id=?", (book_id,))
            connection.execute("DELETE FROM release_locks WHERE book_id=?", (book_id,))
            connection.execute("DELETE FROM cover_concepts WHERE book_id=?", (book_id,))
            connection.execute("DELETE FROM marketplace_status WHERE book_id=?", (book_id,))
            connection.execute("DELETE FROM books WHERE book_id=?", (book_id,))
            removed_books.append(book_id)
        connection.commit()
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        connection.close()

    for path in (
        PROJECT / "release_catalog.json",
        PROJECT / "launch_batch_tracker.json",
        PROJECT / "production_lock.json",
        DATA / "production_ledger.json",
    ):
        reset_json_file(path)
    checkpoint_dir = DATA / "production_autopilot"
    removed_checkpoints = []
    if checkpoint_dir.exists():
        for checkpoint in checkpoint_dir.glob("*.json"):
            checkpoint.unlink()
            removed_checkpoints.append(relative(checkpoint))

    report = {
        "completed_at": now(),
        "manifest": relative(MANIFEST_JSON),
        "removed_generated_folders": removed_folders,
        "removed_unprotected_catalog_rows": removed_books,
        "preserved_protected_catalog_rows": preserved_books,
        "removed_autopilot_checkpoints": removed_checkpoints,
        "database_integrity": integrity,
        "out_is_empty": not any(OUT.iterdir()),
        "preserved_repeat_prevention": ["production_history.json", "data/word_reservations.json"],
    }
    RESET_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "PRODUCTION RESET REPORT",
        f"Completed (UTC): {report['completed_at']}",
        f"Removed generated output folders: {len(removed_folders)}",
        f"Removed unprotected catalog rows: {len(removed_books)}",
        f"Preserved protected catalog rows: {len(preserved_books)}",
        f"Removed autopilot checkpoints: {len(removed_checkpoints)}",
        f"Database integrity: {integrity}",
        f"out/ empty: {report['out_is_empty']}",
        "Repeat-prevention history was retained.",
    ]
    RESET_TEXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="remove only manifest-approved generated state")
    args = parser.parse_args()
    manifest = build_manifest()
    write_manifest(manifest)
    print(f"Manifest written: {MANIFEST_TEXT}")
    if args.apply:
        report = apply_reset(manifest)
        print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
