"""Etsy read-only connection-check component.

This lower-level adapter does exactly one remote job: verify that stored Etsy
credentials work and report which user/shop they belong to.  Every remote call
is funnelled through :meth:`EtsyIntegration._guarded_get`, which only issues
HTTP GETs against the two whitelisted read-only endpoints below - there is no
code path in this module that can create, update, activate or delete anything
on Etsy. Draft creation and attachment uploads are intentionally implemented
by :mod:`integrations.etsy.draft_service`; listing activation remains manual.

Read-only endpoints used (official Etsy Open API v3):
- ``GET https://openapi.etsy.com/v3/application/users/me``
  (operation getMe: authenticated user id)
- ``GET https://openapi.etsy.com/v3/application/users/{user_id}/shops``
  (operation getShopByOwnerUserId: shop id/name for the user)

Credentials come from environment variables or an injected provider; nothing
is persisted by this module.  Required environment variables:

- ``KDP_ETSY_API_KEYSTRING``   app keystring from etsy.com/developers/your-apps
- ``KDP_ETSY_SHARED_SECRET``   app shared secret from the same page (optional;
                               sent as ``keystring:shared_secret`` when set)
- ``KDP_ETSY_ACCESS_TOKEN``    OAuth bearer token with the ``shops_r`` scope
- ``KDP_ETSY_REFRESH_TOKEN``   optional for now; refresh wiring is Phase B

Manual smoke check (opt-in, never run automatically):

    python -m integrations.etsy.connection

prints the ConnectionReport fields using whatever environment configuration
is present.  No secrets are printed.
"""

import os
from dataclasses import dataclass
from typing import Mapping, Optional, Protocol

from integrations.base import CapabilityFlags, ConnectionReport, PublishingIntegration
from integrations.errors import (
    AuthError,
    PermanentError,
    TransientError,
    redact_text,
)
from integrations.etsy.auth import build_x_api_key_header
from integrations.http import HttpClient, HttpRequest

ETSY_API_HOST = "https://openapi.etsy.com"

PATH_ME = "/v3/application/users/me"
PATH_USER_SHOPS = "/v3/application/users/{user_id}/shops"

# The complete set of remote paths this Phase A adapter may ever touch.
# _guarded_get refuses everything else, so future code edits cannot silently
# widen the attack surface without changing (and being caught by) tests.
ALLOWED_READ_PATHS = frozenset({PATH_ME, PATH_USER_SHOPS})

ENV_API_KEYSTRING = "KDP_ETSY_API_KEYSTRING"
ENV_SHARED_SECRET = "KDP_ETSY_SHARED_SECRET"
ENV_ACCESS_TOKEN = "KDP_ETSY_ACCESS_TOKEN"
ENV_REFRESH_TOKEN = "KDP_ETSY_REFRESH_TOKEN"


@dataclass(frozen=True)
class EtsyCredentials:
    api_keystring: str = ""
    shared_secret: str = ""
    access_token: str = ""
    refresh_token: str = ""

    def __repr__(self):
        return (
            f"<EtsyCredentials keystring={'set' if self.api_keystring else 'unset'} "
            f"shared_secret={'set' if self.shared_secret else 'unset'} "
            f"access_token={'set' if self.access_token else 'unset'} "
            f"refresh_token={'set' if self.refresh_token else 'unset'}>"
        )

    __str__ = __repr__


class CredentialProvider(Protocol):
    def load(self) -> EtsyCredentials: ...


class EnvCredentialProvider:
    """Reads Etsy credentials from process environment variables."""

    def load(self) -> EtsyCredentials:
        return EtsyCredentials(
            api_keystring=os.environ.get(ENV_API_KEYSTRING, "").strip(),
            shared_secret=os.environ.get(ENV_SHARED_SECRET, "").strip(),
            access_token=os.environ.get(ENV_ACCESS_TOKEN, "").strip(),
            refresh_token=os.environ.get(ENV_REFRESH_TOKEN, "").strip(),
        )


class EtsyIntegration(PublishingIntegration):
    """Read-only connection verifier used by the wider Etsy service."""

    key = "etsy"
    label = "Etsy"
    capabilities = CapabilityFlags(can_test_connection=True)

    def __init__(self, credential_provider=None, http_client=None):
        self._provider = credential_provider if credential_provider is not None else EnvCredentialProvider()
        self._client_override = http_client

    # -- PublishingIntegration contract -----------------------------------

    def is_configured(self) -> bool:
        creds = self._provider.load()
        return bool(creds.api_keystring) and bool(creds.access_token)

    def test_connection(self) -> ConnectionReport:
        creds = self._provider.load()
        if not self.is_configured():
            missing = []
            if not creds.api_keystring:
                missing.append(ENV_API_KEYSTRING)
            if not creds.shared_secret:
                missing.append(ENV_SHARED_SECRET + " (optional)")
            if not creds.access_token:
                missing.append(ENV_ACCESS_TOKEN)
            return ConnectionReport(
                platform=self.key,
                ok=True,
                connected=False,
                message=(
                    "Not connected to Etsy. Set the environment variable(s): "
                    + ", ".join(missing)
                    + ", then run the connection check again."
                ),
            )
        client = self._client_override or HttpClient(
            sensitive_values=self._secret_values(creds)
        )
        headers = {
            "x-api-key": build_x_api_key_header(creds.api_keystring, creds.shared_secret),
            "Authorization": f"Bearer {creds.access_token}",
            "Accept": "application/json",
        }
        try:
            me = self._guarded_get(client, PATH_ME, {}, headers).json()
            user_id = _as_int(me.get("user_id"))
            shops_payload = {}
            if user_id is not None:
                shops_payload = (
                    self._guarded_get(
                        client, PATH_USER_SHOPS, {"user_id": user_id}, headers
                    ).json()
                    or {}
                )
        except AuthError as exc:
            return ConnectionReport(
                platform=self.key,
                ok=True,
                connected=False,
                message=(
                    "Etsy rejected the stored credentials "
                    f"({exc.message}). Generate a fresh access token and try again."
                ),
            )
        except TransientError as exc:
            return ConnectionReport(
                platform=self.key,
                ok=False,
                connected=False,
                message=f"Etsy could not be reached right now ({redact_text(exc.message)}).",
            )
        except PermanentError as exc:
            return ConnectionReport(
                platform=self.key,
                ok=False,
                connected=False,
                message=f"Etsy refused the connection check ({redact_text(exc.message)}).",
            )
        results = shops_payload.get("results") if isinstance(shops_payload, Mapping) else None
        shop = results[0] if results else None
        shop_id = _as_int((shop or {}).get("shop_id")) or _as_int(_safe_get(me, "shop_id"))
        shop_name = (shop or {}).get("shop_name") or ""
        if shop_name or shop_id:
            message = f"Etsy account connected successfully. Connected shop: {shop_name or shop_id}."
        elif user_id is not None:
            message = "Etsy account connected successfully (no shop found for this account)."
        else:
            message = "Etsy responded, but the account identity could not be read."
        return ConnectionReport(
            platform=self.key,
            ok=True,
            connected=user_id is not None,
            user_id=user_id,
            shop_id=shop_id,
            shop_name=shop_name or None,
            message=message,
        )

    # -- Internals ---------------------------------------------------------

    @staticmethod
    def _secret_values(creds):
        values = [creds.access_token, creds.refresh_token]
        if len(str(creds.api_keystring)) >= 4:
            values.append(creds.api_keystring)
        if creds.shared_secret:
            values.append(creds.shared_secret)
        return tuple(v for v in values if v)

    def _guarded_get(self, client, path_template, path_args, headers):
        """The ONLY remote-call gateway in this adapter: whitelisted GETs.

        The whitelist is checked against the request *template* before
        formatting, so parameterized endpoints are covered too.
        """
        if path_template not in ALLOWED_READ_PATHS:
            raise PermanentError(
                f"Blocked non read-only endpoint in Phase A adapter: {path_template}"
            )
        path = path_template.format(**path_args)
        if "{" in path:
            # Malformed arguments must never turn into an accidental URL.
            raise PermanentError(f"Malformed read-only request path: {path}")
        request = HttpRequest(method="GET", url=f"{ETSY_API_HOST}{path}", headers=dict(headers))
        return client.send(request)


def _safe_get(payload, name):
    try:
        return payload.get(name)
    except AttributeError:
        return None


def _as_int(value):
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def create_etsy_integration(**kwargs) -> EtsyIntegration:
    """Factory used by integrations.registry.get_integration("etsy")."""
    return EtsyIntegration(**kwargs)


def _run_manual_smoke():
    """Opt-in CLI verification; requires environment configuration."""
    integration = create_etsy_integration()
    report = integration.test_connection()
    print(f"platform     : {report.platform}")
    print(f"check ran    : {report.ok}")
    print(f"connected    : {report.connected}")
    print(f"user id      : {report.user_id}")
    print(f"shop id      : {report.shop_id}")
    print(f"shop name    : {report.shop_name}")
    print(f"message      : {report.message}")


if __name__ == "__main__":
    _run_manual_smoke()
