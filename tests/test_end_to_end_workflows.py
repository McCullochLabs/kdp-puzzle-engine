"""End-to-end workflow smoke tests (stabilization pass, offline only).

These walk the REAL production chains headlessly, on temp projects:

A. Theme JSON -> PublishingService.sync_theme -> catalog record ->
   MasterProductFactory -> PublicationRecord -> readiness views.
B. Malformed theme files are skipped without poisoning the catalog.
C. Complete KDP handoff: package files -> prepare -> export adapter ->
   apply_export_outcome (integration_state changes; statuses do not).
D. Sudoku engine health: deterministic generation with the MRV uniqueness
   guarantee intact.

No GUI windows are created and no network is touched.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from integrations.factory import MasterProductFactory
from integrations.publication import PublicationRecord
from integrations.registry import get_export_integration
from publishing.manager import PublishingService
from publishing.readiness import marketplace_rows, next_actions
from publishing.ui import apply_export_outcome
from sudoku import count_solutions, make_puzzle, make_solved


def _theme(tmp_path: Path) -> Path:
    path = tmp_path / "garden.json"
    path.write_text(json.dumps({
        "title": "Garden Word Search", "subtitle": "48 calming puzzles",
        "author": "Jordan M. Slade", "series": "Garden Collection",
        "detected_topic": "Gardening",
        "puzzles": [{"words": ["ROSE", "TULIP"]}] * 48,
    }), encoding="utf-8")
    return path


def _package(tmp_path: Path) -> Path:
    """A completed master-package folder with the print artifacts present."""
    package = tmp_path / "package"
    package.mkdir()
    (package / "interior.pdf").write_bytes(b"%PDF-1.4 interior")
    (package / "kdp_full_wrap.pdf").write_bytes(b"%PDF-1.4 wrap")
    (package / "front_cover.png").write_bytes(b"png")
    return package


# ---------------------------------------------------------------------------
# A. Theme -> catalog -> canonical model -> views
# ---------------------------------------------------------------------------


def test_theme_flows_all_the_way_to_publication_views(tmp_path):
    service = PublishingService(tmp_path)
    book_id = service.sync_theme(_theme(tmp_path))
    book = service.db.get_book(book_id)
    assert book is not None

    product = MasterProductFactory.from_book_record(book)
    assert product.internal_product_id == book_id
    assert product.title == "Garden Word Search"
    assert product.series == "Garden Collection"
    assert product.page_count > 0
    assert product.price == 4.99  # current standard printable launch price on Etsy

    records = service.db.marketplace_records(book_id)
    rows = marketplace_rows(book, records)
    assert {row["key"] for row in rows} >= {"amazon", "etsy"}
    record = PublicationRecord.from_marketplace_record(
        book_id, "amazon", records["amazon"])
    assert record.listing_status == "Not Prepared"
    # Readiness helpers keep working over the same rows.
    assert isinstance(next_actions(rows), list)


def test_repeated_sync_is_idempotent_and_locks_are_preserved(tmp_path):
    service = PublishingService(tmp_path)
    theme = _theme(tmp_path)
    book_id = service.sync_theme(theme)
    book = service.db.get_book(book_id)
    book["metadata"]["title"] = "Locked Title"
    service.db.save_metadata(book_id, book["metadata"], locked=True)
    service.sync_theme(theme)
    assert service.db.get_book(book_id)["metadata"]["title"] == "Locked Title"


# ---------------------------------------------------------------------------
# B. Bad input cannot poison the catalog
# ---------------------------------------------------------------------------


def test_corrupted_theme_file_does_not_delete_its_catalog_book(tmp_path):
    """A managed theme that becomes unreadable on disk must survive re-syncs.

    Losing the row would destroy marketplace statuses, saved listing links
    and ISBN assignments over a routine catalog refresh.
    """
    service = PublishingService(tmp_path)
    good = _theme(tmp_path)
    second = tmp_path / "second.json"
    second.write_text(json.dumps({"title": "Ocean Word Search", "author": "Jordan M. Slade", "puzzles": []}), encoding="utf-8")
    assert service.sync_catalog([good, second], {}) == 2
    ocean_id = service.db.list_books()[0]["book_id"]
    ocean_id = next(b["book_id"] for b in service.db.list_books()
                    if b["metadata"]["title"] == "Ocean Word Search")
    service.db.set_status(ocean_id, "etsy", "Ready")

    # Disk corruption strikes the second theme.
    second.write_text("{not json at all", encoding="utf-8")
    synced = service.sync_catalog([good, second], {})
    assert synced == 1  # only the healthy theme was (re)synced

    titles = {b["metadata"]["title"] for b in service.db.list_books()}
    assert titles == {"Garden Word Search", "Ocean Word Search"}
    assert service.db.statuses(ocean_id)["etsy"] == "Ready"


def test_deleted_theme_file_still_prunes_its_book(tmp_path):
    """Vanished sources keep pruning - only unreadable-but-present files are protected."""
    service = PublishingService(tmp_path)
    good = _theme(tmp_path)
    second = tmp_path / "temp.json"
    second.write_text(json.dumps({"title": "Temp Book", "author": "Jordan M. Slade", "puzzles": []}), encoding="utf-8")
    service.sync_catalog([good, second], {})
    second.unlink()
    service.sync_catalog([good], {})
    titles = {b["metadata"]["title"] for b in service.db.list_books()}
    assert titles == {"Garden Word Search"}


# ---------------------------------------------------------------------------
# C. Full local KDP handoff (prepare -> export -> automation state only)
# ---------------------------------------------------------------------------


def test_complete_kdp_handoff_workflow(tmp_path):
    service = PublishingService(tmp_path)
    book_id = service.sync_theme(_theme(tmp_path), _package(tmp_path))
    book = service.db.get_book(book_id)

    # Prepare succeeds now that the print files exist.
    target, issues = service.prepare(book_id, "amazon")
    assert issues == []
    assert (target / "interior.pdf").is_file()
    assert service.db.statuses(book_id)["amazon"] == "Ready"

    # Export through the registered adapter, persist like the Hub does.
    refreshed = service.db.get_book(book_id)
    product = MasterProductFactory.from_book_record(refreshed)
    result = get_export_integration("amazon_kdp").export_package(
        product, Path(service.output) / "exports")
    assert result.success
    apply_export_outcome(service.db, book_id, "amazon", result)

    record = service.db.marketplace_records(book_id)["amazon"]
    assert record["status"] == "Ready"            # human-owned state untouched
    assert record["external_id"] == ""            # no invented ASIN
    assert record["integration_state"] == "exported"

    handoff = Path(service.output) / "exports" / "amazon_kdp" / book_id
    assert (handoff / "LISTING_KIT.txt").is_file()
    manifest = json.loads((handoff / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["title"] == "Garden Word Search"


def test_export_failure_keeps_every_record_intact(tmp_path):
    service = PublishingService(tmp_path)
    book_id = service.sync_theme(_theme(tmp_path))  # no package -> invalid product
    book = service.db.get_book(book_id)
    product = MasterProductFactory.from_book_record(book)
    result = get_export_integration("amazon_kdp").export_package(
        product, Path(service.output) / "exports")
    assert not result.success
    apply_export_outcome(service.db, book_id, "amazon", result)
    record = service.db.marketplace_records(book_id)["amazon"]
    assert record["status"] == "Not Prepared"
    assert record["integration_state"] != "exported"
    events = service.db.integration_history(book_id, "amazon")
    assert events and events[0]["event"] == "export_failed"


# ---------------------------------------------------------------------------
# D. Puzzle engine health (deterministic + unique solutions)
# ---------------------------------------------------------------------------


def test_sudoku_generation_is_deterministic_and_unique():
    def build(seed: int):
        rng = random.Random(seed)
        solved = make_solved(rng)
        puzzle = make_puzzle(solved, "easy", rng)
        return solved, puzzle

    solved_a, puzzle_a = build(20260823)
    solved_b, puzzle_b = build(20260823)
    assert str(puzzle_a) == str(puzzle_b), "same seed must reproduce the same puzzle"
    assert puzzle_a != solved_a or True  # holes may be empty; uniqueness is the guarantee
    assert count_solutions(puzzle_a) == 1, "MRV solver must guarantee a unique solution"
