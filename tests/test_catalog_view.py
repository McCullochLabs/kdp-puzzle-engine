"""Catalog display must be truthful without deleting its underlying history."""
from pathlib import Path

from publishing.catalog_view import (
    catalog_counts, catalog_state, collapse_catalog_books, in_catalog_view,
)


def book(book_id, *, title="Garden Word Search", package="", source="", production="Passed", statuses=None,
         updated="2026-09-20T12:00:00"):
    return {
        "book_id": book_id, "source_key": source, "package_path": str(package),
        "updated_at": updated, "metadata_locked": 0,
        "metadata": {"title": title, "subtitle": "48 themed puzzles", "author": "Jordan M. Slade",
                     "production_status": production},
        "statuses": statuses or {"amazon": "Not Prepared"},
    }


def complete_package(folder):
    folder.mkdir()
    for name in ("interior.pdf", "front_cover.png", "kdp_full_wrap.pdf"):
        (folder / name).write_bytes(b"sample")


def test_same_physical_package_is_one_visible_book_without_losing_aliases(tmp_path):
    package = tmp_path / "garden_package"
    complete_package(package)
    theme = tmp_path / "garden.json"
    theme.write_text("{}", encoding="utf-8")
    rows = collapse_catalog_books([
        book("older", package=package, source=str(theme), updated="2026-09-19T12:00:00"),
        book("newer", package=package, source=str(theme), statuses={"amazon": "Published"}),
    ])
    assert len(rows) == 1
    assert rows[0]["book_id"] == "newer"
    assert rows[0]["catalog_alias_ids"] == ("older",)
    assert catalog_counts(rows)["aliases_hidden"] == 1
    assert catalog_state(rows[0])["status"] == "Published"
    assert in_catalog_view(rows[0], "Completed books")
    assert not in_catalog_view(rows[0], "Book ideas")


def test_missing_package_and_source_are_not_claimed_as_completed(tmp_path):
    package = tmp_path / "gone_package"
    source = tmp_path / "gone_theme.json"
    rows = collapse_catalog_books([
        book("package", package=package),
        book("source", source=str(source), title="Missing Theme"),
    ])
    assert {item["catalog_kind"] for item in rows} == {"missing_package", "missing_source"}
    assert not any(in_catalog_view(item, "Completed books") for item in rows)
    assert all(in_catalog_view(item, "Needs attention") for item in rows)
    assert catalog_counts(rows)["missing"] == 2


def test_ideas_are_separate_and_no_untitled_records_are_falsely_merged(tmp_path):
    first = book("first", title="", source="", production="Needs content check")
    second = book("second", title="", source="", production="Needs content check")
    rows = collapse_catalog_books([first, second])
    assert len(rows) == 2
    assert all(in_catalog_view(row, "Book ideas") for row in rows)
    assert all(catalog_state(row)["status"] == "Needs content check" for row in rows)


def test_one_next_action_follows_real_stage_and_current_review(tmp_path):
    package = tmp_path / "finished"
    complete_package(package)
    row = collapse_catalog_books([book("b", package=package, statuses={"amazon": "Ready"})])[0]
    assert catalog_state(row, gate={"ready": False}) == {
        "status": "Needs attention", "next_action": "Fix the reported production issue"}
    assert catalog_state(row, gate={"ready": True}, final_review=False)["status"] == "Needs final proof"
    assert catalog_state(row, gate={"ready": True}, contract_ready=False)["next_action"] == "Fix the package or cover proof"
    assert catalog_state(row, gate={"ready": True}, final_review=True)["status"] == "Ready to publish"
    assert in_catalog_view(row, "Needs attention", catalog_state(row, gate={"ready": True}, final_review=False))
    assert not in_catalog_view(row, "Needs attention", catalog_state(row, gate={"ready": True}, final_review=True))


def test_partial_folder_is_attention_not_completed_book(tmp_path):
    folder = tmp_path / "partial"
    folder.mkdir()
    (folder / "interior.pdf").write_bytes(b"sample")
    row = collapse_catalog_books([book("partial", package=folder)])[0]
    assert row["catalog_kind"] == "book_in_progress"
    assert catalog_state(row)["status"] == "Incomplete package"
    assert not in_catalog_view(row, "Completed books")
    assert in_catalog_view(row, "Needs attention")
    assert catalog_counts([row])["in_progress"] == 1


def test_live_listing_with_lost_local_files_is_still_flagged(tmp_path):
    row = collapse_catalog_books([
        book("live", package=tmp_path / "lost", statuses={"amazon": "Published"})
    ])[0]
    assert catalog_state(row)["status"] == "Live listing — files missing"
    assert in_catalog_view(row, "Needs attention")


def test_idea_cannot_claim_ready_when_shared_gate_blocks_it(tmp_path):
    source = tmp_path / "saved.json"
    source.write_text("{}", encoding="utf-8")
    row = collapse_catalog_books([book("b", source=str(source))])[0]
    assert row["catalog_kind"] == "ready_book_idea"
    assert catalog_state(row, gate={"ready": False}) == {
        "status": "Needs content", "next_action": "Fix the reviewed content gap"}
