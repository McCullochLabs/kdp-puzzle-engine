"""Universal Publishing Foundation tests: model, capabilities, results,
validation, registry discovery, publication view, export-only contract.

Everything runs offline; the only filesystem touched is pytest's tmp_path.
"""
from __future__ import annotations

import dataclasses
import inspect
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from integrations.base import (
    ConnectionReport,
    PublishingIntegration,
    CapabilityFlags,
)
from integrations.errors import IntegrationError, UnsupportedCapabilityError
from integrations.exporting import FolderExportIntegration
from integrations.foundation import UniversalPublishingIntegration
from integrations.product import (
    ArtifactPurpose,
    MasterProduct,
    ProductArtifact,
    validate_canonical,
)
from integrations.publication import PublicationRecord
from integrations.results import PublishResult
from integrations.validation import (
    ValidationIssue,
    ValidationResult,
    ValidationSeverity,
)
from integrations import registry


# ---------------------------------------------------------------------------
# MasterProduct
# ---------------------------------------------------------------------------


class TestMasterProduct:
    def test_minimal_incomplete_product_is_valid_to_construct(self):
        product = MasterProduct()
        assert product.internal_product_id == ""
        assert product.title == ""
        assert product.price is None
        assert product.artifacts == ()

    def test_full_creation_with_neutral_field_names(self):
        product = MasterProduct(
            internal_product_id="abc123", sku="BK-abc123", revision=2,
            title="Ocean Word Search", subtitle="60 puzzles", description="d",
            short_description="s", author="Jordan M. Slade", brand="Imprint",
            language="English", product_type="puzzle_book", target_audience="Adults",
            age_range="12+", categories=("Games",), keywords=("ocean puzzle",),
            tags=("ocean", "word search"), price=6.99, currency="USD",
            publication_date="2026-01-01", copyright_notice="© 2026 Jordan",
            isbn="9798...", page_count=72, trim_size="8.5x11", bleed_inches=0.125,
            source_reference="theme-key", generated_at="2026-08-23T00:00:00",
            ai_disclosure="reviewed by publisher",
        )
        assert product.revision == 2 and product.price == 6.99
        names = {f.name for f in dataclasses.fields(MasterProduct)}
        # Marketplace-neutral naming guarantee: no platform prefixes ever.
        for banned in ("etsy_tags", "kdp_keywords", "shopify_product_type"):
            assert banned not in names

    def test_model_never_carries_credential_like_fields(self):
        names = {f.name for f in dataclasses.fields(MasterProduct)}
        for banned in ("token", "secret", "credential", "password", "keystring", "api_key"):
            assert not any(banned in name for name in names), banned

    def test_digital_print_and_hybrid_shapes(self):
        digital = MasterProduct(internal_product_id="p1", artifacts=(
            ProductArtifact(path="x.pdf", purpose=ArtifactPurpose.DIGITAL_PDF),))
        assert digital.is_digital_ready
        printed = MasterProduct(internal_product_id="p2", artifacts=(
            ProductArtifact(path="i.pdf", purpose=ArtifactPurpose.PRINT_INTERIOR),))
        assert not printed.is_digital_ready
        hybrid = MasterProduct(internal_product_id="p3", artifacts=digital.artifacts + printed.artifacts)
        assert hybrid.is_digital_ready and hybrid.has_artifact(ArtifactPurpose.PRINT_INTERIOR)

    def test_artifact_helpers_order_by_position(self):
        product = MasterProduct(internal_product_id="p", artifacts=(
            ProductArtifact(path="b.png", purpose=ArtifactPurpose.PREVIEW, position=2),
            ProductArtifact(path="a.png", purpose=ArtifactPurpose.PREVIEW, position=1),
            ProductArtifact(path="c.pdf", purpose=ArtifactPurpose.DIGITAL_PDF),
        ))
        ordered = product.artifacts_for(ArtifactPurpose.PREVIEW)
        assert [item.path for item in ordered] == ["a.png", "b.png"]
        assert product.first_artifact(ArtifactPurpose.DIGITAL_PDF).path == "c.pdf"
        assert product.first_artifact(ArtifactPurpose.EPUB) is None


class TestProductArtifact:
    def test_purpose_enum_covers_documented_values(self):
        expected = {"print_interior", "print_cover", "digital_pdf", "epub", "thumbnail",
                    "listing_image", "preview", "source_archive", "metadata_export"}
        assert {item.value for item in ArtifactPurpose} == expected

    def test_optional_size_checksum_and_media_guess(self):
        bare = ProductArtifact(path="cover.png", purpose=ArtifactPurpose.THUMBNAIL)
        assert bare.file_size is None and bare.checksum == ""
        assert bare.media_type == "image/png"
        pdf = ProductArtifact(path="interior.PDF", purpose=ArtifactPurpose.PRINT_INTERIOR)
        assert pdf.media_type == "application/pdf"
        unknown = ProductArtifact(path="thing.xyz", purpose=ArtifactPurpose.SOURCE_ARCHIVE)
        assert unknown.media_type == ""

    def test_string_purpose_is_coerced_for_round_trips(self):
        artifact = ProductArtifact(path="a.pdf", purpose="digital_pdf")
        assert artifact.purpose is ArtifactPurpose.DIGITAL_PDF


# ---------------------------------------------------------------------------
# Capabilities: additive expansion + Phase A invariants preserved
# ---------------------------------------------------------------------------


class TestCapabilityFlags:
    def test_every_flag_defaults_false(self):
        flags = CapabilityFlags()
        for field in dataclasses.fields(CapabilityFlags):
            if field.name.startswith("can_") or field.name == "requires_public_file_urls":
                assert getattr(flags, field.name) is False, field.name

    def test_new_flags_advertise_without_touching_old_ones(self):
        exporter = CapabilityFlags(can_export_package=True)
        assert exporter.can_test_connection is False  # old fields untouched
        assert exporter.capability_dict["can_create_listing"] is False

    def test_has_any_write_capability_includes_new_remote_write_flags(self):
        assert CapabilityFlags().has_any_write_capability is False
        assert CapabilityFlags(can_create_draft=True).has_any_write_capability is True
        assert CapabilityFlags(can_update_listing=True).has_any_write_capability is True
        assert CapabilityFlags(can_delete_listing=True).has_any_write_capability is True
        # Local export is NOT a remote write.
        assert CapabilityFlags(can_export_package=True).has_any_write_capability is False

    def test_capability_dict_is_gui_friendly(self):
        payload = CapabilityFlags(can_test_connection=True, can_sync_orders=True).capability_dict
        assert payload["can_test_connection"] is True
        assert payload["can_sync_orders"] is True
        assert "_WRITE_FLAGS" not in payload


def _dummy_universal(**caps):
    class Dummy(UniversalPublishingIntegration):
        key = "dummy"
        label = "Dummy"
        capabilities = CapabilityFlags(**caps)

        def is_configured(self):
            return True

        def test_connection(self):
            return ConnectionReport(platform=self.key, ok=True, connected=False)
    return Dummy()


class TestUniversalContract:
    def test_phase_a_base_still_defines_no_write_methods(self):
        for name in ("create_draft", "publish", "update_listing", "delete_listing"):
            assert getattr(PublishingIntegration, name, None) is None

    def test_committed_etsy_adapter_gains_no_new_method_names(self):
        from integrations.etsy.connection import EtsyIntegration

        for name in ("create_draft", "publish", "update", "get_status",
                     "export_package", "validate_product"):
            assert getattr(EtsyIntegration, name, None) is None, name

    def test_universal_base_declares_the_operation_surface(self):
        for name in ("validate_product", "create_draft", "publish", "update",
                     "get_status", "export_package"):
            assert callable(getattr(UniversalPublishingIntegration, name, None))

    @pytest.mark.parametrize("operation,args", [
        ("validate_product", ("p",)), ("create_draft", ("p",)),
        ("publish", ("p",)), ("update", ("remote-1", "p")),
        ("get_status", ("remote-1",)), ("export_package", ("p", "dest")),
    ])
    def test_unsupported_operations_fail_loudly_not_silently(self, operation, args):
        adapter = _dummy_universal()
        with pytest.raises(UnsupportedCapabilityError) as excinfo:
            getattr(adapter, operation)(*args)
        assert "does not support" in str(excinfo.value)

    def test_supported_operations_work_when_overridden(self):
        class Validating(_dummy_universal(can_validate_products=True).__class__):
            def validate_product(self, product):
                return validate_canonical(product)

        product = MasterProduct(internal_product_id="x", title="T")
        assert Validating().validate_product(product).valid
        # The capability contract stays authoritative: without the override,
        # even a flagged adapter's default still refuses loudly.
        with pytest.raises(UnsupportedCapabilityError):
            _dummy_universal(can_validate_products=True).validate_product(product)

    def test_unsupported_error_is_an_integration_error(self):
        assert issubclass(UnsupportedCapabilityError, IntegrationError)


# ---------------------------------------------------------------------------
# Validation model
# ---------------------------------------------------------------------------


class TestValidationModel:
    def test_severities_and_issue_fields(self):
        issue = ValidationIssue(
            severity=ValidationSeverity.WARNING, code="no_isbn",
            message="No ISBN supplied.", field_ref="isbn",
            suggested_fix="Use KDP-assigned ISBN or assign one.",
        )
        assert issue.severity is ValidationSeverity.WARNING
        assert issue.artifact_ref == ""
        assert ValidationSeverity("error") is ValidationSeverity.ERROR

    def test_validity_requires_zero_errors_only(self):
        warn_only = ValidationResult(issues=(
            ValidationIssue(severity=ValidationSeverity.WARNING, code="w", message="w"),
            ValidationIssue(severity=ValidationSeverity.INFO, code="i", message="i"),
        ))
        assert warn_only.valid
        blocking = ValidationResult(issues=(
            ValidationIssue(severity=ValidationSeverity.ERROR, code="e", message="e"),
        ))
        assert not blocking.valid
        assert blocking.first_error_message() == "e"

    def test_aggregation_and_buckets(self):
        left = ValidationResult(issues=(
            ValidationIssue(severity=ValidationSeverity.ERROR, code="a", message="a"),
            ValidationIssue(severity=ValidationSeverity.INFO, code="b", message="b"),
        ))
        right = ValidationResult(issues=(
            ValidationIssue(severity=ValidationSeverity.WARNING, code="c", message="c"),
        ))
        merged = ValidationResult.aggregate(left, right, ValidationResult.ok())
        assert merged.valid is False
        assert len(merged.errors) == 1 and len(merged.warnings) == 1 and len(merged.infos) == 1

    def test_canonical_validation_belonging_next_to_the_model(self):
        empty = validate_canonical(MasterProduct())
        assert not empty.valid
        codes = {issue.code for issue in empty.errors}
        assert {"missing_product_id", "missing_title"} <= codes
        priced = validate_canonical(MasterProduct(
            internal_product_id="p", title="T", price=4.99))
        assert priced.valid and any(i.code == "no_artifacts" for i in priced.warnings)


# ---------------------------------------------------------------------------
# PublishResult
# ---------------------------------------------------------------------------


class TestPublishResult:
    def test_ok_and_failure_factories(self):
        good = PublishResult.ok(integration_key="etsy", status="draft_created",
                                remote_id="1234", message="done")
        assert good.success and good.remote_id == "1234"
        bad = PublishResult.failure(integration_key="etsy", message="nope",
                                    error_code="validation_failed")
        assert not bad.success and bad.status == "failed"
        assert isinstance(bad.created_at, str) and bad.created_at

    def test_repr_and_str_never_leak_recovery_or_tokens(self):
        token = "SUPERSECRETTOKEN99"
        result = PublishResult(
            success=False, integration_key="etsy",
            message=f"Etsy rejected access_token: {token}",
            recovery={"token": token, "export_path": "/tmp/x"},
        )
        text = repr(result) + str(result)
        assert token not in text
        assert "[REDACTED]" in text
        assert "export_path" not in text  # recovery excluded from debug output entirely

    def test_messages_are_redacted_on_construction(self):
        result = PublishResult(success=True, integration_key="x",
                               message="Bearer abcdefgh12345 ok")
        assert "abcdefgh12345" not in result.message


# ---------------------------------------------------------------------------
# Registry: explicit registration + discovery metadata
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_etsy_lookup_case_insensitive(self):
        for key in ("etsy", "Etsy", " ETSY "):
            integration = registry.get_integration(key)
            assert type(integration).__name__ == "EtsyIntegration"

    def test_unknown_keys_return_none(self):
        for key in ("amazon", "gumroad", "", None):
            assert registry.get_integration(key) is None

    def test_available_keys_reports_working_adapters_only(self):
        assert registry.available_keys() == ("etsy",)

    def test_discovery_metadata_covers_all_channels(self):
        rows = registry.integration_metadata()
        keys = [row["key"] for row in rows]
        assert keys[0] == "etsy"
        assert len(rows) >= 7
        etsy = registry.get_integration_info("etsy")
        assert etsy["mode"] == "api" and etsy["requires_connection"] is True
        assert etsy["status"] == "active"
        kdp = registry.get_integration_info("amazon")
        assert kdp["display_name"] == "Amazon KDP"
        assert kdp["mode"] == "export_only"
        # A real local export adapter exists since the adoption batch.
        assert kdp["status"] == "active"
        assert kdp["capabilities"]["can_export_package"] is True
        assert registry.get_export_integration("amazon_kdp") is not None

    def test_get_integration_info_unknown_is_none(self):
        assert registry.get_integration_info("not_a_channel") is None
        assert registry.get_integration_info(None) is None

    def test_explicit_registration_no_dynamic_scanning(self):
        calls = []

        def factory(**kwargs):
            calls.append(kwargs)
            return _dummy_universal()

        try:
            registry.register_integration("test_channel", factory)
            assert registry.get_integration("Test_Channel ") is not None
            assert registry.available_keys() == ("etsy", "test_channel")
        finally:
            registry.unregister_integration("test_channel")
        assert registry.get_integration("test_channel") is None
        assert registry.available_keys() == ("etsy",)

    def test_registry_module_uses_no_dynamic_import_tools(self):
        source = inspect.getsource(registry)
        for banned in ("importlib", "__import__", "pkgutil", "walk_packages"):
            assert banned not in source, banned


# ---------------------------------------------------------------------------
# PublicationRecord: a VIEW over existing marketplace_status rows
# ---------------------------------------------------------------------------


class TestPublicationRecord:
    def _row(self, **overrides):
        row = {"marketplace": "etsy", "status": "Ready", "external_id": "",
               "url": "", "updated_at": "2026-08-20T10:00:00", "error_message": "",
               "integration_state": "", "last_synced_at": ""}
        row.update(overrides)
        return row

    def test_maps_existing_record_fields(self):
        record = PublicationRecord.from_marketplace_record(
            "book1", "etsy", self._row(status="Published", external_id="555",
                                       url="https://www.etsy.com/listing/555"),
            {"integration_state": "complete", "idempotency_key": "k1",
             "external_sku": "printable.pdf", "last_synced_at": "2026-08-21T09:00:00"})
        assert record.listing_status == "Published"
        assert record.remote_id == "555"
        assert record.published_at == "2026-08-20T10:00:00"
        assert record.is_published
        assert record.idempotency_key == "k1"

    def test_uploaded_must_not_become_published(self):
        record = PublicationRecord.from_marketplace_record(
            "book1", "amazon", self._row(marketplace="amazon", status="Uploaded"))
        assert record.listing_status == "Uploaded"
        assert record.published_at == ""      # never inferred
        assert record.uploaded_at == "2026-08-20T10:00:00"
        assert not record.is_published

    def test_export_only_channel_representation(self):
        record = PublicationRecord.from_marketplace_record(
            "book1", "amazon", self._row(marketplace="amazon", status="Ready"))
        assert record.listing_status == "Ready"
        assert record.remote_id == "" and record.remote_url == ""
        assert record.published_at == ""
        assert record.integration_state == ""

    def test_missing_rows_map_to_empty_truthfully(self):
        record = PublicationRecord.from_marketplace_record("book1", "lulu", None)
        assert record.listing_status == "" and record.published_at == ""


# ---------------------------------------------------------------------------
# Export-only contract (fake/test integration, no network anywhere)
# ---------------------------------------------------------------------------


class TestExportOnlyContract:
    def test_reference_adapter_is_api_free_by_design(self):
        adapter = FolderExportIntegration()
        assert adapter.mode == "export_only"
        assert adapter.is_configured() is True          # no credentials involved
        assert adapter.capabilities.can_export_package is True
        report = adapter.test_connection()
        assert isinstance(report, ConnectionReport)
        assert report.connected is False and "export-only" in report.message.lower()

    def test_export_creates_structured_package(self, tmp_path):
        interior = tmp_path / "interior.pdf"; interior.write_bytes(b"%PDF-interior")
        thumb = tmp_path / "thumbnail.jpg"; thumb.write_bytes(b"\xff\xd8-thumb")
        product = MasterProduct(
            internal_product_id="prod.1", title="Garden Word Search",
            author="Jordan M. Slade", language="English", price=6.99,
            tags=("garden", "word search"), page_count=64, trim_size="8.5x11",
            generated_at="2026-08-23T00:00:00",
            artifacts=(
                ProductArtifact(path=str(interior), purpose=ArtifactPurpose.DIGITAL_PDF),
                ProductArtifact(path=str(thumb), purpose=ArtifactPurpose.LISTING_IMAGE, position=1),
            ),
        )
        destination = tmp_path / "exports"
        result = FolderExportIntegration().export_package(product, destination)
        assert result.success and result.status == "exported"
        root = destination / "folder_export" / "prod.1"
        assert (root / "LISTING_KIT.txt").is_file()
        assert (root / "manifest.json").is_file()
        files = sorted(p.name for p in (root / "files").iterdir())
        assert len(files) == 2
        kit = (root / "LISTING_KIT.txt").read_text(encoding="utf-8")
        assert "Garden Word Search" in kit and "garden" in kit
        manifest = (root / "manifest.json").read_text(encoding="utf-8")
        assert '"internal_product_id": "prod.1"' in manifest
        assert result.recovery["export_path"].endswith(str(Path("folder_export") / "prod.1"))

    def test_export_refuses_invalid_products_before_writing(self, tmp_path):
        product = MasterProduct()  # no id/title -> canonical errors
        result = FolderExportIntegration().export_package(product, tmp_path)
        assert not result.success
        assert result.error_code == "validation_failed"
        assert not (tmp_path / "folder_export").exists()

    def test_export_only_adapter_never_supports_publishing(self, tmp_path):
        adapter = FolderExportIntegration()
        with pytest.raises(UnsupportedCapabilityError):
            adapter.publish(MasterProduct(internal_product_id="p", title="T"))
        with pytest.raises(UnsupportedCapabilityError):
            adapter.create_draft(MasterProduct(internal_product_id="p", title="T"))


# ---------------------------------------------------------------------------
# Security checks across the new surface
# ---------------------------------------------------------------------------


class TestFoundationSecurity:
    def test_no_credentials_on_domain_objects(self):
        for model in (MasterProduct, ProductArtifact, PublicationRecord, PublishResult):
            names = {f.name for f in dataclasses.fields(model)}
            for banned in ("token", "secret", "password", "credential", "api_key"):
                assert not any(banned in name for name in names), (model.__name__, banned)

    def test_redaction_still_reachable_through_results(self):
        result = PublishResult(success=True, integration_key="x",
                               message="shared_secret: 9876543210abcdef leaked?")
        assert "9876543210abcdef" not in result.message
