"""Unit tests for the Publishing Hub selected-book presentation helpers.

These cover the pure logic added to publishing/ui.py so the GUI behavior
(status lines, issue triage, dialog compatibility) stays truthful without
spinning up Tkinter windows.
"""
import inspect

from publishing.database import MARKETPLACES
from publishing.ui import (
    DISPLAY_GRID,
    EtsyConnectDialog,
    MarketplaceConnectionsDialog,
    UploadStatusDialog,
    draft_action_enabled,
    publishing_counts_line,
    split_issues,
    whats_left_text,
)
from publishing.production_orchestrator import ProductionJobIndex


def test_grid_labels_cover_every_marketplace_in_canonical_order():
    assert tuple(DISPLAY_GRID[key] for key in MARKETPLACES) == (
        "Amazon KDP", "Etsy", "IngramSpark", "Website / Direct",
        "Lulu", "BookVault", "Barnes & Noble Press", "Payhip digital downloads",
    )


def test_split_issues_keeps_advisory_template_notes_out_of_blockers():
    issues = [
        "Assign your own ISBN before preparing IngramSpark distribution.",
        "Build the final cover on the current IngramSpark template; a KDP wrap is reference-only because spine dimensions can differ.",
    ]
    blockers, advisories = split_issues(issues)
    assert blockers == [issues[0]]
    assert advisories == [issues[1]]


def test_publishing_counts_line_leads_with_published_and_omits_zero_buckets():
    rows = [{"status": status} for status in
            ("Published", "Uploaded", "Ready", "Not Prepared", "Not Prepared", "Not Prepared", "Not Prepared")]
    line = publishing_counts_line(rows)
    assert line.startswith("1 of 7 published")
    assert "1 uploaded" in line and "1 ready to upload" in line
    assert "need items" not in line and "need attention" not in line


def _grid_row(status: str, **extra) -> dict:
    """Minimal row matching marketplace_rows() output for pure-logic tests."""
    base = {"key": "amazon", "label": "Amazon KDP", "portal_url": "", "status": status,
            "readiness_label": "", "indicator": "", "issues": [], "has_local_folder": False,
            "external_id": "", "url": "", "updated_at": "", "error_message": ""}
    base.update(extra)
    return base


def test_whats_left_text_reports_errors_first_and_caps_next_steps():
    rows = [_grid_row("Error", error_message="disk full"),
            *[_grid_row("Not Prepared") for _ in range(6)]]
    text = whats_left_text(rows)
    assert "0 of 7 marketplaces published" in text
    assert text.index("Fix") < text.index("Prepare the")
    bullets = [line for line in text.splitlines() if line.startswith("• ")]
    assert 1 <= len(bullets) <= 5


def test_whats_left_never_claims_uploaded_is_published():
    rows = [_grid_row("Uploaded") for _ in range(7)]
    text = whats_left_text(rows)
    assert "0 of 7 marketplaces published" in text
    assert "7 uploaded" in text


def test_upload_status_dialog_initial_marketplace_is_optional_and_backwards_compatible():
    parameters = inspect.signature(UploadStatusDialog.__init__).parameters
    assert list(parameters)[2:5] == ["service", "book", "on_saved"]
    assert parameters["initial_marketplace"].default == ""


def test_draft_action_enabled_is_etsy_only_and_never_for_confirmed_rows():
    assert draft_action_enabled({"key": "etsy", "has_local_folder": True, "status": "Ready"})
    assert draft_action_enabled({"key": "etsy", "has_local_folder": True, "status": "Not Prepared"})
    # Wrong marketplace rows never offer it, even when otherwise identical.
    assert not draft_action_enabled({"key": "amazon", "has_local_folder": True, "status": "Ready"})
    # No prepared folder on disk -> nothing to attach.
    assert not draft_action_enabled({"key": "etsy", "has_local_folder": False, "status": "Ready"})
    # Human already confirmed an upload or a live listing: hands off.
    assert not draft_action_enabled({"key": "etsy", "has_local_folder": True, "status": "Uploaded"})
    assert not draft_action_enabled({"key": "etsy", "has_local_folder": True, "status": "Published"})
    assert not draft_action_enabled(None)


def test_market_connection_dialogs_keep_lightweight_construction_contracts():
    connect = inspect.signature(EtsyConnectDialog.__init__).parameters
    connections = inspect.signature(MarketplaceConnectionsDialog.__init__).parameters
    assert list(connections) == ["self", "parent"]
    assert list(connect) == ["self", "parent", "on_done"]
    assert connect["on_done"].default is None


def test_publishing_center_exposes_the_canonical_production_queue():
    source = inspect.getsource(__import__("publishing.ui", fromlist=["PublishingManagerDialog"]).PublishingManagerDialog)
    assert "Production queue" in source
    assert "ProductionJobIndex" in source
    assert "refresh_production_queue" in source
