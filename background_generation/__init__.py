"""Approved, project-generated cover-background services.

This package deliberately has no import-time network calls.  It provides a
small, testable boundary between cover selection and an optional image
generation provider.
"""

from .index import (BackgroundAssetIndex, CoverAssetApprovalError, approved_background_choices,
                    require_production_approved_cover_asset, verify_rendered_cover_approval)
from .service import BackgroundGenerationService

__all__ = ["BackgroundAssetIndex", "BackgroundGenerationService", "CoverAssetApprovalError",
           "approved_background_choices", "require_production_approved_cover_asset",
           "verify_rendered_cover_approval"]
