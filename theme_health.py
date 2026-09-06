"""Shared, revision-aware production readiness records for saved theme files.

The interface, package creator, and Publishing Manager must agree on whether a
specific *version* of a theme has passed its checks.  This tiny module keeps
that evidence outside the theme JSON, so it never changes a user word bank.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path


# Bump this when the shared production gate becomes stricter. A green result
# from an older rule set must never keep a theme marked publish-ready.
CURRENT_GATE_VERSION = 2


def _fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(cache_path: Path) -> dict:
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save(cache_path: Path, payload: dict) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = cache_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(cache_path)


def read_theme_health(cache_path: Path, theme_path: Path) -> dict | None:
    """Return a result only when it belongs to the current file contents."""
    try:
        record = _load(cache_path).get(str(theme_path.resolve()))
        if (not isinstance(record, dict) or
                record.get("fingerprint") != _fingerprint(theme_path) or
                record.get("gate_version") != CURRENT_GATE_VERSION):
            return None
        return record
    except OSError:
        return None


def record_theme_health(cache_path: Path, theme_path: Path, errors: list[str], warnings: list[str]) -> dict:
    """Save the result of the exact production gate that was just run."""
    payload = _load(cache_path)
    record = {
        "fingerprint": _fingerprint(theme_path),
        "status": ("Passed" if not errors and not warnings
                   else "Passed with notes" if not errors else "Blocked"),
        "errors": list(errors),
        "warnings": list(warnings),
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "gate_version": CURRENT_GATE_VERSION,
    }
    payload[str(theme_path.resolve())] = record
    _save(cache_path, payload)
    return record
