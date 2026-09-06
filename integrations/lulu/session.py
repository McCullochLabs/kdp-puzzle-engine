"""Secure, local configuration for a future Lulu Print API connection.

Lulu credentials are deliberately kept out of project files, generated book
folders, logs, and the catalog database.  On Windows, the small encrypted
record is stored in Windows Credential Manager under ``KDPuzzleEngine/Lulu``.
This module only manages that record; it does not make a network request or
place an order.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional, Protocol

from integrations import wincred
from integrations.errors import PermanentError

CREDENTIAL_PLATFORM = "Lulu"
ENV_CLIENT_KEY = "LULU_CLIENT_KEY"
ENV_CLIENT_SECRET = "LULU_CLIENT_SECRET"
ENV_ENVIRONMENT = "LULU_ENVIRONMENT"
SANDBOX = "Sandbox"
PRODUCTION = "Production"
_ENVIRONMENTS = {SANDBOX, PRODUCTION}


@dataclass(frozen=True, repr=False)
class LuluCredentials:
    """Lulu application credentials, intentionally redacted in repr output."""

    client_key: str = ""
    client_secret: str = ""
    environment: str = SANDBOX

    def is_complete(self) -> bool:
        return bool(self.client_key and self.client_secret)

    def __repr__(self) -> str:
        return (
            "LuluCredentials(client_key=<stored>" if self.client_key else "LuluCredentials(client_key=<missing>"
        ) + (
            ", client_secret=<stored>" if self.client_secret else ", client_secret=<missing>"
        ) + f", environment={self.environment!r})"


class CredentialStore(Protocol):
    def load(self) -> Optional[LuluCredentials]: ...
    def save(self, credentials: LuluCredentials) -> None: ...
    def forget(self) -> bool: ...


class WinCredCredentialStore:
    """Windows Credential Manager backed credential store; never writes a file."""

    def load(self) -> Optional[LuluCredentials]:
        payload = wincred.load_secret(CREDENTIAL_PLATFORM)
        return deserialize_credentials(payload) if payload else None

    def save(self, credentials: LuluCredentials) -> None:
        wincred.store_secret(CREDENTIAL_PLATFORM, serialize_credentials(credentials))

    def forget(self) -> bool:
        return wincred.delete_secret(CREDENTIAL_PLATFORM)


def normalize_environment(value: object) -> str:
    text = str(value or "").strip().lower()
    if text in {"production", "prod"}:
        return PRODUCTION
    return SANDBOX


def serialize_credentials(credentials: LuluCredentials) -> dict:
    """Return the minimal encrypted payload; secret values never enter logs."""
    return {
        "client_key": credentials.client_key,
        "client_secret": credentials.client_secret,
        "environment": normalize_environment(credentials.environment),
    }


def deserialize_credentials(payload: object) -> LuluCredentials:
    if not isinstance(payload, dict):
        raise PermanentError("Stored Lulu credentials have an unexpected shape")
    return LuluCredentials(
        client_key=str(payload.get("client_key") or "").strip(),
        client_secret=str(payload.get("client_secret") or "").strip(),
        environment=normalize_environment(payload.get("environment")),
    )


def load_credentials(store: Optional[CredentialStore] = None) -> LuluCredentials:
    """Environment variables override the local encrypted record for automation."""
    env = LuluCredentials(
        client_key=os.environ.get(ENV_CLIENT_KEY, "").strip(),
        client_secret=os.environ.get(ENV_CLIENT_SECRET, "").strip(),
        environment=normalize_environment(os.environ.get(ENV_ENVIRONMENT)),
    )
    stored = (store or WinCredCredentialStore()).load()
    if stored is None:
        return env
    return LuluCredentials(
        client_key=env.client_key or stored.client_key,
        client_secret=env.client_secret or stored.client_secret,
        environment=env.environment if os.environ.get(ENV_ENVIRONMENT) else stored.environment,
    )


def save_credentials(credentials: LuluCredentials, store: Optional[CredentialStore] = None) -> None:
    if not credentials.is_complete():
        raise PermanentError("Enter both the Lulu client key and client secret before saving.")
    (store or WinCredCredentialStore()).save(
        LuluCredentials(
            client_key=credentials.client_key.strip(),
            client_secret=credentials.client_secret.strip(),
            environment=normalize_environment(credentials.environment),
        )
    )


def forget_credentials(store: Optional[CredentialStore] = None) -> bool:
    return (store or WinCredCredentialStore()).forget()


def setup_report(credentials: Optional[LuluCredentials] = None) -> str:
    """Plain-English local setup check; deliberately makes no API request."""
    current = credentials or load_credentials()
    if not current.is_complete():
        return "Lulu is not set up yet. Add both your client key and client secret."
    return (
        f"Lulu {current.environment} credentials are stored securely on this computer. "
        "The app has not contacted Lulu or created an order."
    )
