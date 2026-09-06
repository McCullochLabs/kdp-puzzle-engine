"""Phase 2 Steps 1+2 tests: readiness logic, report classification, history text."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from publishing.database import MARKETPLACES
from publishing.marketplaces import PUBLISHERS
from publishing.readiness import (
    classify_prepare_report,
    format_history,
    marketplace_rows,
    next_actions,
    online_state_text,
    whats_left,
)


@pytest.fixture
def book_factory(tmp_path):
    """A catalog-shaped book whose package files really exist on disk."""
    def make(with_files: bool = True) -> dict:
        files = {}
        if with_files:
            for name in ("interior.pdf", "kdp_full_wrap.pdf", "front_cover.png"):
                target = tmp_path / name
                target.write_bytes(b"x")
                files[{"interior.pdf": "print_interior", "kdp_full_wrap.pdf": "print_cover",
                       "front_cover.png": "front_cover"}.get(name, name)] = str(target)
            files["printable_pdf"] = ""
        return {"book_id": "testbook", "package_path": str(tmp_path) if with_files else "",
                "metadata": {"title": "Garden Word Search", "author": "Jordan M. Slade",
                             "series": "", "theme": "Gardening", "isbn": "", "files": files}}
    return make


def full_records(**overrides: dict) -> dict:
    records = {key: {"marketplace": key, "status": "Not Prepared", "external_id": "",
                     "url": "", "updated_at": "", "error_message": ""} for key in MARKETPLACES}
    for key, patch in overrides.items():
        records[key].update(patch)
    return records


def row(rows: list[dict], key: str) -> dict:
    return next(item for item in rows if item["key"] == key)


def test_readiness_labels_cover_all_underlying_states(book_factory):
    book = book_factory()
    cases = {
        "amazon": ("Published", "Live — listing recorded", "ok"),
        "etsy": ("Uploaded", "Uploaded — confirm when live", "ok"),
        "ingram": ("Error", "Needs attention", "attention"),
        "website": ("Ready", "Package ready — upload next", "info"),
        "lulu": ("Needs Review", "Missing items — see Validate", "attention"),
    }
    records = full_records(**{key: {"status": status} for key, (status, _l, _i) in cases.items()})
    rows = marketplace_rows(book, records)
    for key, (_status, label, indicator) in cases.items():
        assert row(rows, key)["readiness_label"] == label
        assert row(rows, key)["indicator"] == indicator
    # Printer-template reminders are visible advisory notes, not missing book
    # data. The handoff folders can be prepared before the user has selected
    # that printer's exact production specification.
    assert row(rows, "bookvault")["readiness_label"] == "Can be prepared now"
    assert row(rows, "barnes_noble")["readiness_label"] == "Can be prepared now"
    empty_book = book_factory(with_files=False)
    empty_rows = marketplace_rows(empty_book, full_records())
    assert row(empty_rows, "amazon")["readiness_label"] == "Not started"
    assert row(empty_rows, "amazon")["indicator"] == ""


def test_printer_preparation_never_claims_final_upload_readiness(book_factory):
    rows = marketplace_rows(book_factory(), full_records(ingram={"status": "Prepared — Final Cover Needed"}))
    ingram = row(rows, "ingram")
    assert ingram["readiness_label"] == "Prepared — build final platform cover"
    assert ingram["indicator"] == "attention"
    assert "final IngramSpark cover" in " ".join(next_actions(rows))


def test_error_row_surfaces_persisted_message_and_local_folder(book_factory):
    book = book_factory()
    records = full_records(amazon={"status": "Error", "error_message": "the cover file could not be copied"})
    amazon = row(marketplace_rows(book, records), "amazon")
    assert amazon["error_message"] == "the cover file could not be copied"
    assert amazon["has_local_folder"] is False


def test_only_stored_published_state_counts_as_published(book_factory):
    book = book_factory()
    records = full_records(
        amazon={"status": "Published", "external_id": "B0LIVE", "url": "https://example.com/live"},
        etsy={"status": "Not Prepared", "url": "https://example.com/leftover"},
    )
    counts = whats_left(marketplace_rows(book, records))
    assert counts == {"total": 8, "published": 1, "uploaded": 0, "ready_to_upload": 0,
                      "ready_to_prepare": 7, "needs_attention": 0, "needs_items": 0,
                      "final_cover_needed": 0}
    rows = marketplace_rows(book, records)
    assert "Live" not in row(rows, "etsy")["readiness_label"]
    assert row(rows, "amazon")["external_id"] == "B0LIVE"


def test_uploaded_is_never_treated_as_published(book_factory):
    book = book_factory()
    records = full_records(amazon={"status": "Uploaded", "external_id": "B0X", "url": "https://example.com/x"})
    counts = whats_left(marketplace_rows(book, records))
    assert counts["published"] == 0 and counts["uploaded"] == 1
    assert "Live" not in row(marketplace_rows(book, records), "amazon")["readiness_label"]


def test_next_actions_put_errors_first(book_factory):
    book = book_factory()
    records = full_records(
        amazon={"status": "Error", "error_message": "disk full"},
        etsy={"status": "Ready"},
        website={"status": "Not Prepared"},
    )
    actions = next_actions(marketplace_rows(book, records))
    assert actions[0].startswith("Fix Amazon KDP first: disk full")
    rest = actions[1:]
    assert any("Etsy" in action for action in rest)
    assert any("Direct Website" in action for action in rest)


def test_needs_review_action_carries_validator_guidance(book_factory):
    book = book_factory()  # files complete, but no ISBN assigned
    records = full_records(
        ingram={"status": "Needs Review"},
        # Terminal states keep the other platforms from adding tasks.
        **{key: {"status": "Published"} for key in ("amazon", "etsy", "website", "barnes_noble")},
    )
    actions = next_actions(marketplace_rows(book, records))
    assert len(actions) == 1
    assert "ISBN" in actions[0]


def test_not_started_platforms_do_not_clutter_next_actions(book_factory):
    book = book_factory()
    records = full_records(
        lulu={"status": "Not Prepared"},  # template-cover note always applies
        **{key: {"status": "Published"} for key in ("amazon", "etsy", "website", "barnes_noble")},
    )
    rows = marketplace_rows(book, records)
    assert whats_left(rows)["ready_to_prepare"] == 4  # ingram + lulu + bookvault + Payhip stay Not Prepared
    assert next_actions(rows) == []


def test_whats_left_counts_a_mixed_catalog(book_factory):
    book = book_factory()
    records = full_records(
        amazon={"status": "Published"}, etsy={"status": "Published"},
        ingram={"status": "Error", "error_message": "x"}, barnes_noble={"status": "Needs Review"},
        website={"status": "Ready"}, lulu={"status": "Uploaded"}, bookvault={"status": "Not Prepared"},
    )
    counts = whats_left(marketplace_rows(book, records))
    assert counts == {"total": 8, "published": 2, "uploaded": 1, "ready_to_upload": 1,
                      "ready_to_prepare": 2, "needs_attention": 1, "needs_items": 1,
                      "final_cover_needed": 0}


def test_next_actions_are_capped_at_five(book_factory):
    book = book_factory()
    records = full_records(
        amazon={"status": "Error", "error_message": "a"}, etsy={"status": "Error", "error_message": "b"},
        ingram={"status": "Needs Review"}, barnes_noble={"status": "Needs Review"},
        website={"status": "Not Prepared"}, bookvault={"status": "Ready"},
    )
    actions = next_actions(marketplace_rows(book, records))
    assert len(actions) == 5
    assert all(action.startswith("Fix") for action in actions[:2])


def test_everything_published_leaves_no_remaining_actions(book_factory):
    book = book_factory()
    records = full_records(**{key: {"status": "Published"} for key in MARKETPLACES})
    rows = marketplace_rows(book, records)
    assert whats_left(rows)["published"] == 8
    assert next_actions(rows) == []


def test_classify_prepare_report_buckets_each_outcome():
    report = [
        ("b1", "amazon", "Ready"),
        ("b2", "etsy", "Already Uploaded"),
        ("b3", "ingram", "Already Published"),
        ("b4", "website", "Error: printer on fire"),
        ("b5", "lulu", "Needs Review"),
    ]
    buckets = classify_prepare_report(report)
    assert buckets["prepared"] == [("b1", "amazon")]
    assert buckets["already_confirmed"] == [("b2", "etsy", "Uploaded"), ("b3", "ingram", "Published")]
    assert buckets["errors"] == [("b4", "website", "printer on fire")]
    assert buckets["needs_review"] == [("b5", "lulu")]
    assert buckets["other"] == []


def test_classify_prepare_report_keeps_template_cover_work_visible():
    buckets = classify_prepare_report([("b1", "ingram", "Prepared — Final Cover Needed")])
    assert buckets["final_cover_needed"] == [("b1", "ingram")]


def test_classify_prepare_report_handles_all_ready_and_unknown_strings():
    ready = classify_prepare_report([("b1", key, "Ready") for key in MARKETPLACES])
    assert len(ready["prepared"]) == 8 and not any(ready[key] for key in ("needs_review", "already_confirmed", "errors"))
    odd = classify_prepare_report([("b1", "amazon", "Something Unexpected")])
    assert odd["other"] == [("b1", "amazon", "Something Unexpected")]


def test_format_history_orders_newest_first_with_plain_phrases():
    entries = [
        {"marketplace": "amazon", "old_status": "Uploaded", "new_status": "Published", "changed_at": "2026-08-25T10:00:00",
         "source": "manual", "external_id": "B0LIVE", "listing_url": "https://example.com/live", "error_message": ""},
        {"marketplace": "amazon", "old_status": "Ready", "new_status": "Uploaded", "changed_at": "2026-08-24T09:00:00",
         "source": "manual", "external_id": "B0X", "listing_url": "", "error_message": ""},
        {"marketplace": "amazon", "old_status": "Not Prepared", "new_status": "Ready", "changed_at": "2026-08-23T08:00:00",
         "source": "prepare", "external_id": "", "listing_url": "", "error_message": ""},
        {"marketplace": "amazon", "old_status": "Not Prepared", "new_status": "Ready", "changed_at": "2026-08-22T07:00:00",
         "source": "local_scan", "external_id": "", "listing_url": "", "error_message": ""},
        {"marketplace": "amazon", "old_status": "Not Prepared", "new_status": "Error", "changed_at": "2026-08-21T06:30:00",
         "source": "prepare", "external_id": "", "listing_url": "", "error_message": "cover missing"},
    ]
    text = format_history(entries)
    assert text.index("Aug 25, 2026") < text.index("Aug 24, 2026") < text.index("Aug 23, 2026")
    assert text.index("Aug 23, 2026") < text.index("Aug 22, 2026") < text.index("Aug 21, 2026")
    assert "Marked Published" in text and "Listing: https://example.com/live" in text
    assert "Recorded as Uploaded — ASIN: B0X" in text
    assert "Prepared the upload package" in text
    assert "Found the prepared folder on disk" in text
    assert "Preparation failed: cover missing" in text
    assert text.startswith("Aug 25, 2026")


def test_format_history_prefixes_labels_when_marketplaces_mix():
    entries = [
        {"marketplace": "etsy", "old_status": "Not Prepared", "new_status": "Ready", "changed_at": "2026-08-25T10:00:00",
         "source": "prepare", "external_id": "", "listing_url": "", "error_message": ""},
        {"marketplace": "amazon", "old_status": "Not Prepared", "new_status": "Ready", "changed_at": "2026-08-24T09:00:00",
         "source": "prepare", "external_id": "", "listing_url": "", "error_message": ""},
    ]
    text = format_history(entries)
    assert "Amazon KDP — Prepared the upload package" in text
    assert "Etsy — Prepared the upload package" in text


def test_format_history_empty_stream_is_friendly():
    assert format_history([]) == "No publishing history yet."


def test_portal_urls_are_official_https_addresses():
    expected = {
        "amazon": "https://kdp.amazon.com/en_US/bookshelf",
        "etsy": "https://www.etsy.com/shop-manager",
        "ingram": "https://www.ingramspark.com",
        "lulu": "https://www.lulu.com",
        "bookvault": "https://www.bookvault.app",
        "barnes_noble": "https://www.barnesandnoblepress.com",
        "website": "",
    }
    for key, url in expected.items():
        assert PUBLISHERS[key].portal_url == url
        if url:
            assert url.startswith("https://")


def test_portal_metadata_does_not_change_preparation_behavior(book_factory):
    book = book_factory()
    for publisher in PUBLISHERS.values():
        issues = publisher.validate(book)
        assert isinstance(issues, list)


def test_online_state_text_stays_truthful_about_automation_progress():
    assert online_state_text("") == ""
    assert "draft" in online_state_text("draft_created")
    assert "NOT published" in online_state_text("draft_created")
    assert "file" in online_state_text("files_uploaded").lower()
    assert "NOT published" in online_state_text("files_uploaded")
    complete = online_state_text("complete")
    assert "draft" in complete.lower() and "publish it in etsy shop manager" in complete.lower()
    unknown = online_state_text("mystery_state")
    assert "mystery state" in unknown.lower()  # underscores shown as spaces
    assert "published" not in unknown.lower()
    assert "history" in unknown.lower()
