"""Offline tests for the additional Publishing Hub channel handoffs."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from integrations.product import ArtifactPurpose, MasterProduct, ProductArtifact
from integrations.registry import get_export_integration, integration_metadata
from integrations.validation import ValidationSeverity


def product(tmp_path):
    interior = tmp_path / "interior.pdf"; interior.write_bytes(b"interior")
    cover = tmp_path / "cover.pdf"; cover.write_bytes(b"cover")
    image = tmp_path / "cover.png"; image.write_bytes(b"image")
    return MasterProduct(internal_product_id="garden-1", title="Garden Word Search",
        description="Garden puzzles.", price=9.99, artifacts=(
            ProductArtifact(str(interior), ArtifactPurpose.PRINT_INTERIOR),
            ProductArtifact(str(cover), ArtifactPurpose.PRINT_COVER),
            ProductArtifact(str(image), ArtifactPurpose.THUMBNAIL),
        ))


def test_all_new_channel_handoffs_are_registered_and_offline(tmp_path):
    item = product(tmp_path)
    for key in ("ingram", "lulu", "barnes_noble", "shopify", "woocommerce", "wix"):
        adapter = get_export_integration(key)
        assert adapter is not None
        assert adapter.capabilities.can_export_package
        assert not adapter.capabilities.has_any_write_capability
        result = adapter.export_package(item, tmp_path / "exports")
        assert result.success
        assert (tmp_path / "exports" / key / "garden-1" / "manifest.json").is_file()
        assert "nothing is sent" in adapter.test_connection().message.casefold()


def test_print_distributors_require_print_assets(tmp_path):
    item = MasterProduct(internal_product_id="x", title="T")
    for key in ("ingram", "lulu", "barnes_noble"):
        result = get_export_integration(key).validate_product(item)
        assert not result.valid
        assert any(issue.severity is ValidationSeverity.ERROR for issue in result.issues)


def test_registry_describes_actual_automation_level_not_fake_live_publish():
    rows = {row["key"]: row for row in integration_metadata()}
    for key in ("ingram", "lulu", "barnes_noble", "shopify", "woocommerce", "wix"):
        assert rows[key]["mode"] == "export_only"
        assert rows[key]["capabilities"]["can_export_package"]
        assert not rows[key]["capabilities"]["can_create_listing"]
