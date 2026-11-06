import json
from pathlib import Path

from publishing.catalog_view import catalog_state, record_kind
from publishing.manager import PublishingService


def test_manifest_pending_status_is_preserved_and_incomplete_package_is_not_ready(tmp_path):
    project = Path(tmp_path)
    package = project / "out" / "review_book"
    (package / "01_PRINT_UPLOADS").mkdir(parents=True)
    (package / "01_PRINT_UPLOADS" / "interior.pdf").write_bytes(b"draft interior")
    (package / "PACKAGE_SOURCE_RECORD.json").write_text(json.dumps({
        "title": "Review-Stage Book",
        "subtitle": "A draft for human review",
        "author": "Jordan M. Slade",
        "puzzle_type": "Word Search",
        "theme": "Test topic",
        "puzzle_count": 80,
        "pages": 160,
        "production_status": "Needs review",
    }), encoding="utf-8")

    service = PublishingService(project)
    assert service.sync_output_packages() == 1
    book = service.db.list_books()[0]

    assert book["metadata"]["production_status"] == "Needs review"
    assert record_kind(book) == "book_in_progress"
    assert catalog_state(book)["status"] == "Incomplete package"


def test_legacy_manifest_without_status_keeps_complete_package_default(tmp_path):
    project = Path(tmp_path)
    package = project / "out" / "legacy_book"
    package.mkdir(parents=True)
    (package / "PACKAGE_SOURCE_RECORD.json").write_text(json.dumps({
        "title": "Legacy Package",
        "subtitle": "Existing package",
        "author": "Jordan M. Slade",
        "puzzle_type": "Word Search",
        "theme": "Test topic",
        "puzzle_count": 80,
        "pages": 160,
    }), encoding="utf-8")

    service = PublishingService(project)
    assert service.sync_output_packages() == 1
    book = service.db.list_books()[0]
    assert book["metadata"]["production_status"] == "Complete package"
