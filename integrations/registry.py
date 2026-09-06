"""Lookup table connecting marketplace keys to adapter factories.

Kept deliberately tiny: future Hub code calls :func:`get_integration` without
special-casing Etsy.  Unknown keys return ``None`` (rather than raising) so
callers can degrade gracefully to the manual Level 1/2 workflows that already
work today.  Only platforms with real, reviewed adapters are registered.

Universal Publishing Foundation additions (backwards compatible):

- Registration is now an explicit dict (:data:`_FACTORIES`); adding a future
  integration means one entry here plus its own package - no dynamic module
  scanning, no magic imports.
- :func:`integration_metadata` / :func:`get_integration_info` expose static
  discovery metadata for a future GUI (key, display name, api vs export-only
  vs manual, active/planned).  This list intentionally covers channels that
  have NO adapter yet so the UI can show truthful "Export Only"/"Not
  Connected" rows; it is metadata only and never instantiates anything.
- :func:`available_keys` still reports ONLY keys with working adapters.
"""

from typing import Optional

from integrations.base import PublishingIntegration


# Explicit registry: registry key -> factory. No scanning, no magic imports.
# _FACTORIES holds API-style adapters only; export-only adapters live in
# _EXPORT_FACTORIES so Phase A invariants (available_keys() == ("etsy",),
# get_integration("amazon") is None) stay provable while export-only platforms
# remain first-class through get_export_integration().
_FACTORIES = {}
_EXPORT_FACTORIES = {}


def register_integration(key: str, factory):
    """Explicitly register an adapter factory under *key* (idempotent)."""
    normalized = _normalize(key)
    if not normalized:
        raise ValueError("An integration key is required.")
    _FACTORIES[normalized] = factory


def register_export_integration(key: str, factory):
    """Explicitly register an export-only adapter factory under *key*."""
    normalized = _normalize(key)
    if not normalized:
        raise ValueError("An integration key is required.")
    _EXPORT_FACTORIES[normalized] = factory


def unregister_integration(key: str) -> bool:
    """Remove a registration; mainly for tests."""
    removed_api = _FACTORIES.pop(_normalize(key), None) is not None
    removed_export = _EXPORT_FACTORIES.pop(_normalize(key), None) is not None
    return removed_api or removed_export


def _normalize(key) -> str:
    return (str(key or "")).strip().lower()


def get_integration(key, **kwargs) -> Optional[PublishingIntegration]:
    """Return the adapter for *key*, or None when no integration exists.

    Keyword arguments are forwarded to the adapter factory so callers (and
    tests) can inject credential providers and HTTP transports.
    """
    normalized = _normalize(key)
    factory = _FACTORIES.get(normalized)
    if factory is None:
        return None
    return factory(**kwargs)


def get_export_integration(key, **kwargs):
    """Return an export-only adapter for *key*, or None when unregistered."""
    normalized = _normalize(key)
    factory = _EXPORT_FACTORIES.get(normalized)
    if factory is None:
        return None
    return factory(**kwargs)


def available_keys():
    """Keys with a registered, working adapter, in stable order."""
    ordered = ("etsy",)
    extras = tuple(k for k in sorted(_FACTORIES) if k not in ordered)
    return ordered + extras


# ---------------------------------------------------------------------------
# Discovery metadata for a future GUI (static facts only; nothing instantiated)
# ---------------------------------------------------------------------------

_MODE_API = "api"
_MODE_EXPORT_ONLY = "export_only"
_MODE_MANUAL = "manual"

_STATUS_ACTIVE = "active"        # working adapter exists today
_STATUS_PLANNED = "planned"      # manual workflow only; adapter may come later


def _capabilities(**flags) -> dict:
    from integrations.base import CapabilityFlags

    return CapabilityFlags(**flags).capability_dict


def _etsy_capabilities() -> dict:
    from integrations.etsy.capabilities import ETSY_CAPABILITIES

    return ETSY_CAPABILITIES.capability_dict


# Truthful system-wide capability advertisement per channel.  Etsy reflects
# the committed connection + draft-automation surface (never activation);
# amazon_kdp reflects the local export builder.  Planned channels advertise
# nothing yet.
_INTEGRATION_INFO = (
    {"key": "etsy", "display_name": "Etsy", "mode": _MODE_API,
     "requires_connection": True, "status": _STATUS_ACTIVE,
     "capabilities": _etsy_capabilities()},
    {"key": "amazon", "display_name": "Amazon KDP", "mode": _MODE_EXPORT_ONLY,
     "requires_connection": False, "status": _STATUS_ACTIVE,
     "export_key": "amazon_kdp",
     "capabilities": _capabilities(can_export_package=True, can_validate_products=True)},
    {"key": "ingram", "display_name": "IngramSpark", "mode": _MODE_EXPORT_ONLY,
     "requires_connection": False, "status": _STATUS_ACTIVE, "export_key": "ingram",
     "capabilities": _capabilities(can_export_package=True, can_validate_products=True)},
    {"key": "lulu", "display_name": "Lulu Direct", "mode": _MODE_EXPORT_ONLY,
     "requires_connection": False, "status": _STATUS_ACTIVE, "export_key": "lulu",
     "capabilities": _capabilities(can_export_package=True, can_validate_products=True)},
    {"key": "bookvault", "display_name": "BookVault", "mode": _MODE_EXPORT_ONLY,
     "requires_connection": False, "status": _STATUS_PLANNED,
     "capabilities": _capabilities()},
    {"key": "barnes_noble", "display_name": "Barnes & Noble Press", "mode": _MODE_EXPORT_ONLY,
     "requires_connection": False, "status": _STATUS_ACTIVE, "export_key": "barnes_noble",
     "capabilities": _capabilities(can_export_package=True, can_validate_products=True)},
    {"key": "payhip", "display_name": "Payhip", "mode": _MODE_MANUAL,
     "requires_connection": False, "status": _STATUS_ACTIVE,
     "capabilities": _capabilities(can_export_package=True, can_validate_products=True)},
    {"key": "shopify", "display_name": "Shopify", "mode": _MODE_EXPORT_ONLY,
     "requires_connection": False, "status": _STATUS_ACTIVE, "export_key": "shopify",
     "capabilities": _capabilities(can_export_package=True, can_validate_products=True)},
    {"key": "woocommerce", "display_name": "WooCommerce", "mode": _MODE_EXPORT_ONLY,
     "requires_connection": False, "status": _STATUS_ACTIVE, "export_key": "woocommerce",
     "capabilities": _capabilities(can_export_package=True, can_validate_products=True)},
    {"key": "wix", "display_name": "Wix", "mode": _MODE_EXPORT_ONLY,
     "requires_connection": False, "status": _STATUS_ACTIVE, "export_key": "wix",
     "capabilities": _capabilities(can_export_package=True, can_validate_products=True)},
)


def integration_metadata() -> list[dict]:
    """Fresh copies of the discovery rows, in canonical marketplace order."""
    return [get_integration_info(entry["key"]) for entry in _INTEGRATION_INFO]


def get_integration_info(key) -> Optional[dict]:
    """Discovery metadata for one key (fresh deep-enough copy each call)."""
    normalized = _normalize(key)
    for row in _INTEGRATION_INFO:
        if row["key"] == normalized:
            # Copy nested dicts too so callers can never mutate global state.
            info = dict(row)
            info["capabilities"] = dict(row.get("capabilities") or {})
            return info
    return None


def _register_builtin_integrations():
    """Wire the built-in adapters. Kept in one place for review clarity."""
    from integrations.etsy.connection import create_etsy_integration
    from integrations.amazon.kdp_export import create_kdp_export_integration
    from integrations.platform_exports import create_platform_export

    register_integration("etsy", create_etsy_integration)
    register_export_integration("amazon_kdp", create_kdp_export_integration)
    for key in ("ingram", "lulu", "barnes_noble", "shopify", "woocommerce", "wix"):
        register_export_integration(key, create_platform_export(key))


_register_builtin_integrations()
