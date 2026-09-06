"""Single source of truth for the verified Etsy feature surface."""
from integrations.base import CapabilityFlags

# Connection checking lives in connection.py. Draft creation and attachment
# uploads live in draft_service.py/drafts.py. Human activation remains required.
ETSY_CAPABILITIES = CapabilityFlags(
    can_test_connection=True,
    can_create_draft=True,
    can_upload_files=True,
    can_upload_images=True,
)
