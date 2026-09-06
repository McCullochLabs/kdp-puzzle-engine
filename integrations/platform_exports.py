"""Truthful local handoff adapters for channels without a configured API.

These adapters deliberately create *only* reusable local packages.  They do
not contain HTTP, browser, credential, or publishing code.  A future official
API connector can replace an individual adapter without changing the master
product model or the Publishing Hub.
"""
from __future__ import annotations

from dataclasses import dataclass

from integrations.exporting import FolderExportIntegration
from integrations.product import ArtifactPurpose, MasterProduct, validate_canonical
from integrations.validation import ValidationIssue, ValidationResult, ValidationSeverity


@dataclass(frozen=True)
class PlatformExportRule:
    key: str
    label: str
    automation_level: int
    note: str
    needs_print_files: bool = False
    needs_digital_file: bool = False


RULES = {
    "ingram": PlatformExportRule("ingram", "IngramSpark upload package", 3,
        "Upload manually in IngramSpark. Build the final cover from its current template.", True),
    "barnes_noble": PlatformExportRule("barnes_noble", "Barnes & Noble Press upload package", 3,
        "Upload manually in B&N Press. Build the final cover from its current template.", True),
    "lulu": PlatformExportRule("lulu", "Lulu print handoff", 2,
        "This creates a Lulu-ready handoff only. Connect official Lulu credentials before any print-job action.", True),
    "shopify": PlatformExportRule("shopify", "Shopify product handoff", 2,
        "This creates a product handoff only. Connect a Shopify custom app before creating drafts through Shopify.", False),
    "woocommerce": PlatformExportRule("woocommerce", "WooCommerce product handoff", 2,
        "This creates a product handoff only. Connect a WooCommerce REST API key before creating drafts.", False),
    "wix": PlatformExportRule("wix", "Wix product handoff", 3,
        "This creates a product handoff only. Configure the selected Wix integration before publishing.", False),
}


class PlatformExportIntegration(FolderExportIntegration):
    """Channel-aware, offline package export that never makes a remote call."""

    def __init__(self, rule: PlatformExportRule) -> None:
        self.rule = rule
        self.key = rule.key
        self.label = rule.label

    def test_connection(self):
        report = super().test_connection()
        return report.__class__(platform=self.key, ok=True, connected=False,
            message=f"{self.rule.note} Nothing is sent or published by this export.")

    def validate_product(self, product: MasterProduct) -> ValidationResult:
        issues = list(validate_canonical(product).issues)
        if self.rule.needs_print_files:
            for purpose, label in ((ArtifactPurpose.PRINT_INTERIOR, "finished interior PDF"),
                                   (ArtifactPurpose.PRINT_COVER, "platform-specific cover PDF")):
                if not product.has_artifact(purpose):
                    issues.append(ValidationIssue(ValidationSeverity.ERROR,
                        f"{self.key}_{purpose.value}_required",
                        f"{self.label} needs a {label} before this package can be prepared.",
                        artifact_ref=purpose.value))
            # KDP covers are intentionally supplied only as a reference to
            # non-KDP printers, so no false promise of a reusable final cover.
            if product.has_artifact(ArtifactPurpose.PRINT_COVER):
                issues.append(ValidationIssue(ValidationSeverity.WARNING,
                    f"{self.key}_cover_template_review", "Confirm the printer's current template and rebuild the final cover there before upload."))
        if self.rule.needs_digital_file and not product.has_artifact(ArtifactPurpose.DIGITAL_PDF):
            issues.append(ValidationIssue(ValidationSeverity.ERROR,
                f"{self.key}_digital_file_required", "A buyer-ready digital download is needed for this product variant.",
                artifact_ref=ArtifactPurpose.DIGITAL_PDF.value))
        return ValidationResult(issues=tuple(issues))


def create_platform_export(key: str):
    rule = RULES[str(key).strip().lower()]
    return lambda **_kwargs: PlatformExportIntegration(rule)
