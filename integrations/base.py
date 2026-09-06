"""Shared integration contract for marketplace adapters.

The base adapter deliberately defines only configuration and connection
verification. Approved write workflows (such as Etsy draft creation and
attachment uploads) live in separate, explicit services and advertise their
individual capabilities through :class:`CapabilityFlags`.

Not defining write methods here is a safety feature: an adapter cannot grow a
write path by accident - it would have to extend this contract first, which
shows up in code review and in the Phase A security tests.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, fields
from typing import ClassVar, Optional


@dataclass(frozen=True)
class CapabilityFlags:
    """Truthful advertisement of what an adapter can do *right now*.

    Adapters must only set flags for capabilities that are actually
    implemented and safe to invoke; future capability may be discussed in the
    adapter's docstring instead of being pre-advertised here.

    Universal Publishing Foundation note: the flags below were extended
    ADDITIVELY.  The original Phase A fields, their order and their
    False defaults are unchanged, so every existing adapter and test keeps
    behaving identically.  New fields describe the operations defined by the
    opt-in universal contract in :mod:`integrations.foundation`.
    """

    can_test_connection: bool = False
    can_create_draft: bool = False
    can_upload_files: bool = False
    can_upload_images: bool = False
    can_activate: bool = False
    can_pull_status: bool = False
    can_pull_sales: bool = False
    requires_public_file_urls: bool = False
    # -- Universal Publishing Foundation additions (all default False) -----
    can_validate_products: bool = False
    can_create_listing: bool = False
    can_update_listing: bool = False
    can_delete_listing: bool = False
    can_sync_status: bool = False
    can_sync_orders: bool = False
    can_fulfill_physical: bool = False
    can_calculate_print_cost: bool = False
    can_export_package: bool = False

    _WRITE_FLAGS = (
        "can_create_draft",
        "can_upload_files",
        "can_upload_images",
        "can_activate",
        "can_create_listing",
        "can_update_listing",
        "can_delete_listing",
        "can_fulfill_physical",
    )

    @property
    def has_any_write_capability(self):
        return any(getattr(self, name) for name in self._WRITE_FLAGS)

    @property
    def capability_dict(self):
        """Plain dict view used by GUI discovery metadata (no Tk imports)."""
        return {
            field.name: getattr(self, field.name)
            for field in fields(self)
            if field.name != "_WRITE_FLAGS"
        }


@dataclass(frozen=True)
class ConnectionReport:
    """Result of a read-only connectivity verification.

    ``ok`` means the check itself ran to a conclusion (no unexpected crash);
    ``connected`` means remote credentials were actually verified.  All fields
    are non-secret and safe to display in the Publishing Hub.
    """

    platform: str
    ok: bool
    connected: bool
    user_id: Optional[int] = None
    shop_id: Optional[int] = None
    shop_name: Optional[str] = None
    message: str = ""


class PublishingIntegration(ABC):
    """Base contract every marketplace adapter implements.

    Class attributes:
        key: short registry key, e.g. "etsy".
        label: human-readable platform name for UI display.
        capabilities: CapabilityFlags describing implemented features only.
    """

    key: ClassVar[str] = ""
    label: ClassVar[str] = ""
    capabilities: ClassVar[CapabilityFlags] = CapabilityFlags()

    @abstractmethod
    def is_configured(self) -> bool:
        """True when enough credentials are present to attempt a connection."""

    @abstractmethod
    def test_connection(self) -> ConnectionReport:
        """Perform read-only verification against the remote platform.

        Implementations must never raise for ordinary failure modes; they
        return a ConnectionReport with a plain-English message instead.
        """
