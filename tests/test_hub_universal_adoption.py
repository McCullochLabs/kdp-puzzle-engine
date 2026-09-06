"""Universal Publishing ADOPTION tests (Phase A of batch 3).

Proves the Publishing Hub now reads through the canonical MasterProduct /
PublicationRecord models, that marketplace discovery is capability-driven,
that a REAL export-only Amazon KDP adapter exists and writes local handoff
folders only, and that the Etsy draft automation builds its payload through
the shared mapper with byte parity to build_draft_fields.

All tests are headless: they exercise pure helpers, the database, and file
output. No Tk windows are created.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from integrations.factory import MasterProductFactory
from integrations.product import ArtifactPurpose, ProductArtifact, MasterProduct
from integrations.publication import PublicationRecord
from integrations.registry import get_export_integration, integration_metadata
from integrations.validation import ValidationSeverity
from publishing.database import PublishingDatabase
from publishing.ui import (
    _format_bytes,
    apply_export_outcome,
    artifact_summary_lines,
    export_action_enabled,
    integration_info_for,
    marketplace_row_values,
    render_master_product_text,
    selected_book_overview,
)

ROOT = Path(__file__).resolve().parents[1]
BOOK_ID = "b1a2c3d4e5f6"


def make_product(**overrides) -> MasterProduct:
    fields = dict(
        internal_product_id=BOOK_ID,
        title="Garden Word Search",
        subtitle="60 relaxing puzzles",
        series="Calm Collections",
        author="Jordan M. Slade",
        description="Relaxing garden puzzles.",
        page_count=64,
        trim_size="8.5x11",
        isbn="9798123456780",
        price=6.99,
        keywords=["garden word search"],
        tags=["garden", "word search"],
    )
    fields.update(overrides)
    return MasterProduct(**fields)


def make_book(tmp_path, **meta_overrides) -> dict:
    """A realistic catalog record with real print files on disk."""
    package = tmp_path / "package"
    package.mkdir(parents=True, exist_ok=True)
    files = {
        "print_interior": package / "interior.pdf",
        "print_cover": package / "kdp_full_wrap.pdf",
        "front_cover": package / "front_cover.png",
    }
    for name, path in files.items():
        path.write_bytes(b"content-" + name.encode())
    metadata = {
        "title": "Garden Word Search", "subtitle": "60 relaxing puzzles",
        "series": "Calm Collections", "theme": "Garden",
        "author": "Jordan M. Slade", "isbn": "", "page_count": 64,
        "trim_size": "8.5x11", "price": {"etsy": 6.99},
        "files": {key: str(path) for key, path in files.items()},
    }
    metadata.update(meta_overrides)
    return {"book_id": BOOK_ID, "source_key": r"C:\themes\garden.json",
            "metadata": metadata, "package_path": str(package),
            "created_at": "2026-08-01T00:00:00", "updated_at": "2026-08-22T00:00:00"}


# ---------------------------------------------------------------------------
# Series flows through the canonical model
# ---------------------------------------------------------------------------


class TestSeriesField:
    def test_series_default_empty(self):
        assert MasterProduct().series == ""

    def test_factory_maps_series(self, tmp_path):
        product = MasterProductFactory.from_book_record(make_book(tmp_path))
        assert product.series == "Calm Collections"

    def test_factory_survives_missing_series(self, tmp_path):
        book = make_book(tmp_path)
        del book["metadata"]["series"]
        assert MasterProductFactory.from_book_record(book).series == ""


# ---------------------------------------------------------------------------
# Hub read-model helpers
# ---------------------------------------------------------------------------


class TestSelectedBookOverview:
    def test_overview_flows_through_master_product(self, tmp_path):
        text = selected_book_overview(MasterProductFactory.from_book_record(make_book(tmp_path)),
                                      make_book(tmp_path))
        assert "60 relaxing puzzles" in text
        assert "Series: Calm Collections" in text
        assert "Theme: Garden" in text
        assert "64 pages" in text
        assert "ISBN: not assigned" in text

    def test_overview_shows_isbn_when_present(self):
        text = selected_book_overview(make_product(), {"metadata": {}})
        assert "ISBN: 9798123456780" in text

    def test_overview_singular_page(self):
        product = make_product(page_count=1)
        assert "1 page" in selected_book_overview(product, {"metadata": {}})


class TestArtifactSummary:
    def test_lines_include_position_size_checksum_and_path(self, tmp_path):
        target = tmp_path / "interior.pdf"
        target.write_bytes(b"x" * 2048)
        product = make_product(artifacts=(ProductArtifact(
            purpose=ArtifactPurpose.PRINT_INTERIOR, path=str(target), file_size=2048),))
        lines = artifact_summary_lines(product)
        joined = "\n".join(lines)
        assert "print_interior: interior.pdf" in joined
        assert "[application/pdf, 2.0 KB, checksum: Not calculated]" in joined
        assert lines[1] == f"    {target}"

    def test_position_prefix_when_set(self, tmp_path):
        target = tmp_path / "thumbnail.jpg"
        target.write_bytes(b"img")
        product = make_product(artifacts=(ProductArtifact(
            purpose=ArtifactPurpose.LISTING_IMAGE, path=str(target), position=1),))
        assert artifact_summary_lines(product)[0].startswith("#1 listing_image:")

    def test_no_artifacts_no_lines(self):
        assert artifact_summary_lines(make_product()) == []


class TestFormatBytes:
    @pytest.mark.parametrize("raw,expected", [
        (512, "512 B"), (2048, "2.0 KB"), (3 * 1024 * 1024, "3.0 MB"),
        ("garbage", ""), (None, ""),
    ])
    def test_formatting(self, raw, expected):
        assert _format_bytes(raw) == expected


class TestRenderMasterProductText:
    def test_all_sections_and_values(self):
        text = render_master_product_text(make_product())
        for header in ("IDENTITY", "METADATA", "COMMERCIAL", "PRINT", "ARTIFACTS", "SOURCE / REVISION"):
            assert header in text
        assert "Garden Word Search" in text
        assert "Series: Calm Collections" in text
        assert "6.99 USD" in text
        assert "9798123456780" in text
        assert '8.5x11' in text

    def test_never_carries_credential_words(self):
        text = render_master_product_text(make_product()).casefold()
        for word in ("api_key", "apikey", "secret", "password", "token", "cookie"):
            assert word not in text


class TestMarketplaceRowValues:
    ROW_LABEL = DISPLAY = "Etsy"  # noqa: N815 - display label only

    def test_not_prepared_row_matches_previous_rendering(self):
        record = PublicationRecord.from_marketplace_record(
            BOOK_ID, "etsy", {"status": "", "integration_state": ""})
        values = marketplace_row_values(record, "Etsy", "Ready when prepared")
        assert values == ("Etsy", "Not Prepared", "Ready when prepared", "—", "—", "—")

    def test_uploaded_row_preserves_id_and_date(self):
        record = PublicationRecord.from_marketplace_record(
            BOOK_ID, "etsy", {"status": "Uploaded", "external_id": "12345",
                              "url": "https://etsy.test/12345",
                              "updated_at": "2026-08-22T10:30:00"})
        values = marketplace_row_values(record, "Etsy", "Confirm it is live")
        assert values == ("Etsy", "Uploaded", "Confirm it is live", "12345",
                          "Saved link", "2026-08-22 10:30")

    def test_published_row(self):
        record = PublicationRecord.from_marketplace_record(
            BOOK_ID, "amazon", {"status": "Published"})
        values = marketplace_row_values(record, "Amazon KDP", "Live")
        assert values[1] == "Published"


# ---------------------------------------------------------------------------
# Capability-driven discovery + export gating
# ---------------------------------------------------------------------------


class TestIntegrationDiscovery:
    def test_etsy_advertises_api_capabilities(self):
        info = integration_info_for("etsy")
        assert info["mode"] == "api" and info["status"] == "active"
        assert info["requires_connection"] is True
        caps = info["capabilities"]
        assert caps["can_create_draft"] and caps["can_test_connection"]
        assert not caps["can_export_package"]

    def test_amazon_advertises_active_export_only(self):
        info = integration_info_for("amazon")
        assert info["display_name"] == "Amazon KDP"
        assert info["mode"] == "export_only" and info["status"] == "active"
        assert info["capabilities"]["can_export_package"] is True
        # No API adapter exists - only the export builder.
        assert info.get("export_key") == "amazon_kdp"

    def test_unimplemented_channel_stays_planned(self):
        for key in ("bookvault",):
            info = integration_info_for(key)
            assert info["status"] == "planned"
            assert not any(info["capabilities"].values())

    def test_new_channels_advertise_safe_export_only_support(self):
        for key in ("ingram", "lulu", "barnes_noble", "shopify", "woocommerce", "wix"):
            info = integration_info_for(key)
            assert info["mode"] == "export_only" and info["status"] == "active"
            assert info["capabilities"]["can_export_package"]
            assert not info["capabilities"]["can_create_listing"]

    def test_unknown_key_returns_none(self):
        assert integration_info_for("mars") is None
        assert integration_info_for("") is None

    def test_metadata_rows_are_copies(self):
        rows = integration_metadata()
        rows[0]["capabilities"]["can_create_draft"] = False
        assert integration_info_for("etsy")["capabilities"]["can_create_draft"] is True


class TestExportGating:
    def _row(self, key="amazon", folder=True, status="Prepared"):
        return {"key": key, "has_local_folder": folder, "status": status}

    def test_enabled_for_active_export_channel(self):
        assert export_action_enabled(self._row(), integration_info_for("amazon")) is True

    def test_disabled_without_folder(self):
        assert export_action_enabled(self._row(folder=False), integration_info_for("amazon")) is False

    def test_disabled_once_human_confirmed_upload(self):
        assert export_action_enabled(self._row(status="Uploaded"), integration_info_for("amazon")) is False
        assert export_action_enabled(self._row(status="Published"), integration_info_for("amazon")) is False

    def test_disabled_for_api_channels(self):
        assert export_action_enabled(self._row(key="etsy"), integration_info_for("etsy")) is False

    def test_enabled_for_new_active_export_channels(self):
        assert export_action_enabled(self._row(key="ingram"), integration_info_for("ingram")) is True

    def test_disabled_without_row_or_info(self):
        assert export_action_enabled(None, integration_info_for("amazon")) is False
        assert export_action_enabled(self._row(), None) is False


# ---------------------------------------------------------------------------
# apply_export_outcome: automation-owned state only
# ---------------------------------------------------------------------------


class FakeResult:
    def __init__(self, success, message="done"):
        self.success = success
        self.message = message


class TestApplyExportOutcome:
    @pytest.fixture()
    def db(self, tmp_path):
        database = PublishingDatabase(tmp_path / "catalog.db")
        database.upsert_book(BOOK_ID, "theme:garden", {"title": "Garden Word Search"})
        database.set_status(BOOK_ID, "amazon", "Prepared")
        database.set_integration_state(BOOK_ID, "amazon", "prepared")
        return database

    def test_success_sets_integration_state_only(self, db):
        before = db.marketplace_records(BOOK_ID)["amazon"]
        apply_export_outcome(db, BOOK_ID, "amazon", FakeResult(True, "Export ready"))
        after = db.marketplace_records(BOOK_ID)["amazon"]
        assert after["integration_state"] == "exported"
        assert after["status"] == before["status"] == "Prepared"
        assert after["external_id"] == before["external_id"]
        assert after["url"] == before["url"]
        assert after["updated_at"] == before["updated_at"]

    def test_failure_records_event_only(self, db):
        apply_export_outcome(db, BOOK_ID, "amazon", FakeResult(False, "Interior PDF missing"))
        record = db.marketplace_records(BOOK_ID)["amazon"]
        assert record["status"] == "Prepared"
        assert record["integration_state"] == "prepared"
        events = db.integration_history(BOOK_ID, "amazon")
        assert any(e["event"] == "export_failed" and "Interior PDF missing" in e["detail"]
                   for e in events)


# ---------------------------------------------------------------------------
# Real KDP export-only adapter
# ---------------------------------------------------------------------------


class TestKDPPackageExportIntegration:
    @pytest.fixture()
    def adapter(self):
        return get_export_integration("amazon_kdp")

    def test_registry_roundtrip_and_shape(self, adapter):
        from integrations.exporting import FolderExportIntegration

        assert adapter is not None
        assert adapter.key == "amazon_kdp"
        assert isinstance(adapter, FolderExportIntegration)
        assert adapter.capabilities.can_export_package is True
        assert adapter.capabilities.has_any_write_capability is False

    def test_no_write_methods_on_adapter(self, adapter):
        """The adapter (and its export base) must not DEFINE write methods.

        Inherited loud-unsupported stubs from the universal contract are fine
        (they raise UnsupportedCapabilityError); definitions are not.
        """
        forbidden = {"create_draft", "publish", "update_listing", "delete_listing",
                     "upload_listing_file", "upload_listing_image"}
        own_names = {name for klass in type(adapter).__mro__
                     if klass.__name__ in ("KDPPackageExportIntegration", "FolderExportIntegration")
                     for name in vars(klass)}
        assert not forbidden & own_names

    def test_connection_reports_local_only(self, adapter):
        report = adapter.test_connection()
        assert report.connected is False and report.ok is True
        assert "kdp.amazon.com" in report.message
        assert "never" in report.message.casefold() or "nothing" in report.message.casefold()

    def test_validation_requires_interior_and_cover(self, tmp_path):
        product = MasterProductFactory.from_book_record(make_book(tmp_path))
        result = get_export_integration("amazon_kdp").validate_product(product)
        errors = [i for i in result.issues if i.severity is ValidationSeverity.ERROR]
        assert result.valid
        assert not errors  # both print files exist in this fixture

    def test_validation_flags_missing_print_files(self):
        result = get_export_integration("amazon_kdp").validate_product(make_product())
        codes = {issue.code for issue in result.issues}
        assert {"kdp_interior_required", "kdp_cover_required"} <= codes
        assert not result.valid

    def test_validation_warns_about_missing_isbn(self):
        product = make_product(isbn="", artifacts=(
            ProductArtifact(purpose=ArtifactPurpose.PRINT_INTERIOR, path="p.pdf"),
            ProductArtifact(purpose=ArtifactPurpose.PRINT_COVER, path="c.pdf")))
        issues = get_export_integration("amazon_kdp").validate_product(product).issues
        warnings = [i for i in issues if i.severity is ValidationSeverity.WARNING]
        assert any(i.code == "kdp_isbn_missing" for i in warnings)

    def test_export_writes_kdp_handoff_layout(self, tmp_path):
        book = make_book(tmp_path)
        product = MasterProductFactory.from_book_record(book)
        destination = tmp_path / "exports"
        result = get_export_integration("amazon_kdp").export_package(product, destination)
        assert result.success
        root = destination / "amazon_kdp" / BOOK_ID
        assert (root / "LISTING_KIT.txt").is_file()
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["title"] == "Garden Word Search"
        assert manifest["page_count"] == 64
        assert manifest["isbn"] == "" and manifest["trim_size"] == "8.5x11"
        copied = sorted(p.name for p in (root / "files").iterdir())
        assert any(name.endswith("interior.pdf") for name in copied)
        assert any(name.endswith("kdp_full_wrap.pdf") for name in copied)

    def test_export_refuses_invalid_product_without_writing(self, tmp_path):
        destination = tmp_path / "exports"
        result = get_export_integration("amazon_kdp").export_package(
            make_product(), destination)  # no print artifacts -> invalid
        assert not result.success
        assert result.error_code == "validation_failed"
        assert not destination.exists()

    def test_adapter_source_has_no_network_or_process_calls(self):
        source = (ROOT / "integrations" / "amazon" / "kdp_export.py").read_text(encoding="utf-8")
        for marker in ("urllib", "requests.", "subprocess", "webbrowser", "selenium", "socket"):
            assert marker not in source, f"kdp_export.py must stay offline ({marker})"


# ---------------------------------------------------------------------------
# Etsy draft automation adoption
# ---------------------------------------------------------------------------


class TestDraftServiceAdoption:
    def test_run_remote_builds_payload_through_mapper(self):
        source = (ROOT / "integrations" / "etsy" / "draft_service.py").read_text(encoding="utf-8")
        assert "EtsyListingMapper" in source
        assert "MasterProductFactory.from_book_record(book)" in source

    def test_build_draft_fields_still_public_api(self):
        from integrations.etsy.draft_service import build_draft_fields

        fields = build_draft_fields({"title": "T", "description": "D"}, 161, 6.99)
        assert fields["taxonomy_id"] == "161"

    def test_mapper_payload_matches_legacy_for_realistic_book(self, tmp_path):
        from integrations.etsy.draft_service import build_draft_fields
        from integrations.etsy.mapper import EtsyListingMapper

        book = make_book(tmp_path)
        meta = book["metadata"]
        product = MasterProductFactory.from_book_record(book)
        legacy = build_draft_fields(meta, 161, float(meta["price"]["etsy"]))
        adopted = EtsyListingMapper().to_listing_data(
            product, taxonomy_id=161, price_override=float(meta["price"]["etsy"])).to_form_fields()
        assert adopted == legacy

    def test_import_cycle_is_avoided(self):
        """mapper imports draft_service; draft_service must import lazily."""
        ds_source = (ROOT / "integrations" / "etsy" / "draft_service.py").read_text(encoding="utf-8")
        top = "\n".join(line for line in ds_source.splitlines()[:40])
        assert "integrations.etsy.mapper" not in top


# ---------------------------------------------------------------------------
# Hub wiring (static checks keep these tests headless)
# ---------------------------------------------------------------------------


class TestHubWiring:
    @staticmethod
    def _ui_source() -> str:
        return (ROOT / "publishing" / "ui.py").read_text(encoding="utf-8")

    def test_view_master_product_button_and_dialog_exist(self):
        source = self._ui_source()
        assert '"View Master Product"' in source
        assert "class MasterProductDialog" in source
        assert "_open_master_product" in source

    def test_generate_export_package_action_wired(self):
        source = self._ui_source()
        assert '"Generate Export Package"' in source
        assert "_generate_export_package" in source
        assert "apply_export_outcome(self.service.db" in source

    def test_tree_values_come_from_publication_records(self):
        source = self._ui_source()
        assert 'self.publication_records.get(row["key"])' in source
        assert "PublicationRecord.from_marketplace_record(" in source

    def test_selection_resets_domain_views(self):
        source = self._ui_source()
        assert "self.master_product = None" in source
        assert "self.publication_records = {}" in source

    def test_handler_uses_threading_like_draft_flow(self):
        source = self._ui_source()
        start = source.index("def _generate_export_package")
        body = source[start:source.index("def refresh(", start)]
        assert "threading.Thread(target=runner, daemon=True)" in body
        # The export handler persists automation state only; human-owned
        # status columns are never written from this path.
        assert ".set_status(" not in body.replace("self.status.set", "")
