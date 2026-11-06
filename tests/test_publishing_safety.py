"""Phase 1 safety tests: protected statuses, audit trail, persisted errors."""
import json
import os
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from publishing.database import PROTECTED_STATUSES, PublishingDatabase
from publishing.manager import PublishingService
from publishing.marketplaces import PUBLISHERS
def test_new_rebuild_replaces_locally_ready_draft_but_not_uploaded_book(tmp_path):
    database = PublishingDatabase(tmp_path / "catalog.db")
    old, new = tmp_path / "old_package", tmp_path / "new_package"
    old.mkdir(); new.mkdir()
    os.utime(old, (1000, 1000)); os.utime(new, (2000, 2000))
    for book_id, folder in (("old", old), ("new", new)):
        database.upsert_book(book_id, "package:" + str(folder), {"title": "Into the Woods Sudoku"}, str(folder))
    database.transition_status("old", "amazon", "Ready", source="prepare")
    assert database.prune_duplicate_unpublished_package_titles() == 1
    assert database.get_book("old") is None
    assert database.get_book("new") is not None

    database.upsert_book("old", "package:" + str(old), {"title": "Into the Woods Sudoku"}, str(old))
    database.transition_status("old", "amazon", "Uploaded", external_id="B0LIVE", source="manual")
    assert database.prune_duplicate_unpublished_package_titles() == 1
    assert database.get_book("old") is not None
    assert database.get_book("new") is None


def _theme(tmp_path: Path) -> Path:
    path = tmp_path / "sample.json"
    path.write_text(json.dumps({"title": "Garden Word Search", "subtitle": "48 calming puzzles", "author": "Jordan M. Slade", "series": "Garden Collection", "detected_topic": "Gardening", "puzzles": [{"words": ["ROSE"]}] * 48}), encoding="utf-8")
    return path


def _service_with_package(tmp_path: Path) -> tuple[PublishingService, str, Path]:
    """A catalog book whose print files exist, so validation passes."""
    service = PublishingService(tmp_path)
    package = tmp_path / "finished"
    package.mkdir(parents=True, exist_ok=True)
    for name in ("interior.pdf", "kdp_full_wrap.pdf"):
        (package / name).write_bytes(b"pdf")
    book_id = service.sync_theme(_theme(tmp_path), package)
    return service, book_id, package


def _audit(service: PublishingService, book_id: str) -> list[dict]:
    return service.db.audit_history(book_id=book_id)


def test_ready_transition_still_works_and_audits_once(tmp_path):
    service, book_id, package = _service_with_package(tmp_path)
    folder, issues = service.prepare(book_id, "amazon")
    assert issues == []
    assert service.db.statuses(book_id)["amazon"] == "Ready"
    assert (folder / "interior.pdf").is_file()
    history = _audit(service, book_id)
    assert len(history) == 1
    assert history[0]["old_status"] == "Not Prepared"
    assert history[0]["new_status"] == "Ready"
    assert history[0]["source"] == "prepare"
    # Re-preparing an unchanged Ready record writes nothing new.
    service.prepare(book_id, "amazon")
    assert len(_audit(service, book_id)) == 1


@pytest.mark.parametrize("status", ["Uploaded", "Published"])
def test_prepare_never_downgrades_protected_statuses_or_loses_ids(tmp_path, status):
    assert status in PROTECTED_STATUSES
    service, book_id, _package = _service_with_package(tmp_path)
    link = f"https://www.example.com/dp/{status}"
    service.db.update_marketplace_record(book_id, "amazon", status, "B0TEST123", link)
    before = service.db.marketplace_records(book_id)["amazon"]
    folder, issues = service.prepare(book_id, "amazon")
    assert any("nothing was changed" in issue.lower() and status in issue for issue in issues)
    after = service.db.marketplace_records(book_id)["amazon"]
    assert after["status"] == status
    assert after["external_id"] == "B0TEST123"
    assert after["url"] == link
    assert not (Path(folder) / "kdp").exists() or before["updated_at"] == after["updated_at"]
    # A protected no-op must not create any audit row, let alone a downgrade.
    assert _audit(service, book_id)[-1]["new_status"] == status


def test_each_actual_change_writes_exactly_one_audit_row(tmp_path):
    service, book_id, _package = _service_with_package(tmp_path)
    service.prepare(book_id, "amazon")  # Not Prepared -> Ready
    service.db.update_marketplace_record(book_id, "amazon", "Uploaded", "B0X", "https://example.com/x")
    history = _audit(service, book_id)
    assert [(row["old_status"], row["new_status"]) for row in reversed(history)] == [
        ("Not Prepared", "Ready"), ("Ready", "Uploaded")]
    assert history[0]["external_id"] == "B0X"
    assert history[0]["listing_url"] == "https://example.com/x"
    # Saving identical values again is a no-op with no duplicate audit row.
    service.db.update_marketplace_record(book_id, "amazon", "Uploaded", "B0X", "https://example.com/x")
    assert len(_audit(service, book_id)) == 2


def test_prepare_many_reports_protected_record_without_touching_it(tmp_path):
    service, book_id, _package = _service_with_package(tmp_path)
    service.db.update_marketplace_record(book_id, "amazon", "Published", "B0LIVE", "https://example.com/live")
    report = service.prepare_many([book_id], ["amazon"])
    assert report == [(book_id, "amazon", "Already Published")]
    record = service.db.marketplace_records(book_id)["amazon"]
    assert record["status"] == "Published" and record["external_id"] == "B0LIVE"
    assert _audit(service, book_id)[-1]["new_status"] == "Published"


def test_prepare_failure_persists_error_text_exactly_once(tmp_path, monkeypatch):
    service, book_id, _package = _service_with_package(tmp_path)
    original_prepare = PUBLISHERS["amazon"].prepare

    def boom(book, target):
        raise OSError("the cover file could not be copied")

    monkeypatch.setattr(PUBLISHERS["amazon"], "prepare", boom)
    with pytest.raises(OSError):
        service.prepare(book_id, "amazon")
    record = service.db.marketplace_records(book_id)["amazon"]
    assert record["status"] == "Error"
    assert "cover file could not be copied" in record["error_message"]
    # The batch fallback must deduplicate, not double-audit the same failure.
    report = service.prepare_many([book_id], ["amazon"])
    assert report[0][2].startswith("Error:")
    history = _audit(service, book_id)
    assert len(history) == 1 and history[0]["new_status"] == "Error"
    assert "cover file could not be copied" in history[0]["error_message"]
    # A later success clears the stale preparation error.
    monkeypatch.setattr(PUBLISHERS["amazon"], "prepare", original_prepare)
    service.prepare(book_id, "amazon")
    assert service.db.marketplace_records(book_id)["amazon"]["status"] == "Ready"
    assert service.db.marketplace_records(book_id)["amazon"]["error_message"] == ""


def test_local_scan_still_marks_ready_but_respects_confirmed_states(tmp_path):
    service, book_id, package = _service_with_package(tmp_path)
    (package / "kdp").mkdir()
    (package / "etsy").mkdir()
    service.db.update_marketplace_record(book_id, "etsy", "Published", "LISTING1", "https://www.etsy.com/listing/1")
    updated = service.detect_local_marketplace_status()
    statuses = service.db.statuses(book_id)
    assert updated == 1 and statuses["amazon"] == "Ready"
    etsy = service.db.marketplace_records(book_id)["etsy"]
    assert etsy["status"] == "Published" and etsy["external_id"] == "LISTING1"
    scan_rows = [row for row in _audit(service, book_id) if row["source"] == "local_scan"]
    assert len(scan_rows) == 1 and scan_rows[0]["new_status"] == "Ready"


def test_legacy_database_migrates_additively_without_losing_rows(tmp_path):
    db_path = tmp_path / "legacy_books.db"
    legacy = sqlite3.connect(db_path)
    legacy.executescript("""
        CREATE TABLE books (book_id TEXT PRIMARY KEY, source_key TEXT UNIQUE NOT NULL, metadata_json TEXT NOT NULL, metadata_locked INTEGER NOT NULL DEFAULT 0, package_path TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE marketplace_status (book_id TEXT NOT NULL, marketplace TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Not Prepared', external_id TEXT DEFAULT '', url TEXT DEFAULT '', updated_at TEXT NOT NULL, PRIMARY KEY (book_id, marketplace), FOREIGN KEY(book_id) REFERENCES books(book_id));
        CREATE TABLE isbns (isbn TEXT PRIMARY KEY, book_id TEXT, title TEXT, format TEXT, source TEXT, assigned_at TEXT);
        CREATE TABLE bundles (bundle_id TEXT PRIMARY KEY, title TEXT NOT NULL, book_ids_json TEXT NOT NULL, metadata_json TEXT NOT NULL, output_path TEXT NOT NULL, created_at TEXT NOT NULL);
        INSERT INTO books VALUES('abc123', 'legacy-theme.json', '{"title": "Legacy Book"}', 0, '', '2026-01-01T00:00:00', '2026-01-01T00:00:00');
        INSERT INTO marketplace_status VALUES('abc123', 'amazon', 'Published', 'B0OLD', 'https://example.com/old', '2026-01-02T00:00:00');
    """)
    legacy.commit(); legacy.close()

    db = PublishingDatabase(db_path)
    record = db.marketplace_records("abc123")["amazon"]
    assert record["status"] == "Published"
    assert record["external_id"] == "B0OLD"
    assert record["url"] == "https://example.com/old"
    assert record["error_message"] == ""
    with sqlite3.connect(db_path) as check:
        assert check.execute("SELECT COUNT(*) FROM books").fetchone()[0] == 1
        tables = {name for (name,) in check.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"marketplace_audit"} <= tables
        assert check.execute("SELECT COUNT(*) FROM marketplace_audit").fetchone()[0] == 0
    # The migrated database keeps working through the guarded path.
    db.transition_status("abc123", "etsy", "Ready", source="prepare")
    assert db.audit_history(book_id="abc123")[0]["new_status"] == "Ready"


def test_transition_rejects_unknown_marketplace(tmp_path):
    db = PublishingDatabase(tmp_path / "books.db")
    with pytest.raises(ValueError):
        db.transition_status("whatever", "not_a_store", "Ready")
