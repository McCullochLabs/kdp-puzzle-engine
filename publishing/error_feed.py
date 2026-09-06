"""Read the legacy creator error log without creating a second error store."""
from __future__ import annotations

import json
from pathlib import Path


def related_creator_errors(project: Path, title: str) -> list[dict]:
    """Return only plain-English legacy errors that name this book exactly.

    The root error log remains the source and stays managed by the creator.
    This adapter merely makes applicable entries visible with publishing facts.
    """
    path = Path(project) / "error_log.json"
    try:
        entries = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return []
    wanted = str(title or "").strip().casefold()
    if not wanted or not isinstance(entries, list):
        return []
    result = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("book") or "").strip().casefold() != wanted:
            continue
        result.append({
            "time": str(entry.get("time") or ""),
            "action": str(entry.get("action") or ""),
            "what_happened": str(entry.get("what_happened") or ""),
            "suggestion": str(entry.get("suggestion") or ""),
        })
    return result
