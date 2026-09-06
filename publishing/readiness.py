"""Readiness calculations for the Publishing Hub.

Pure presentation logic: no Tkinter, no database writes, no browser calls,
no file generation.  Everything here derives from stored status records plus
the marketplace validators' plain-English output, so the UI can stay truthful
without ever inventing publication state.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .database import MARKETPLACES
from .marketplaces import PUBLISHERS
from .package_layout import marketplace_handoff_folder

# Where prepare() places each platform's handoff inside a book package.
# Kept in step with publishing/manager.py and publishing/ui.py.
PREPARED_FOLDER_NAMES = {"amazon": "kdp", "barnes_noble": "barnes_noble", "payhip": "payhip"}
# Optional direct-sales channels stay visible in the readiness grid but do not
# crowd the immediate next-action list until the seller chooses to use them.
OPTIONAL_MARKETPLACES = {"payhip"}

# Buyer-facing noun for a confirmed marketplace identifier (ASIN on Amazon).
ID_NOUNS = {"amazon": "ASIN", "etsy": "Listing ID"}
DEFAULT_RECORD = {"status": "Not Prepared", "external_id": "", "url": "", "updated_at": "",
                  "error_message": "", "integration_state": "", "last_synced_at": ""}


def _readiness(status: str, issues: list[str]) -> tuple[str, str]:
    """Map stored state to a plain-English label and an indicator tag.

    Indicator tags ("ok", "attention", "info", "") are presentation hints;
    the wording itself never claims more than the record proves.
    """
    if status == "Published":
        return "Live — listing recorded", "ok"
    if status == "Uploaded":
        return "Uploaded — confirm when live", "ok"
    if status == "Error":
        return "Needs attention", "attention"
    if status == "Ready":
        return "Package ready — upload next", "info"
    if status == "Prepared — Final Cover Needed":
        return "Prepared — build final platform cover", "attention"
    if status == "Needs Review":
        return "Missing items — see Validate", "attention"
    if status == "Not Prepared":
        return ("Can be prepared now", "info") if not issues else ("Not started", "")
    return f"Status: {status}", ""


def marketplace_rows(book: dict, records: dict) -> list[dict]:
    """One truthful readiness row per marketplace, in canonical order."""
    package = str(book.get("package_path") or "")
    rows = []
    for key in MARKETPLACES:
        publisher = PUBLISHERS[key]
        record = dict(DEFAULT_RECORD)
        record.update(records.get(key) or {})
        try:
            issues = list(publisher.validate(book))
        except Exception as exc:  # a broken check must not crash the Hub
            issues = [f"Could not fully check {publisher.label} right now: {exc}"]
        # A platform-template reminder matters, but it is not missing book
        # information.  The user can prepare the handoff folder now and build
        # the final printer-specific cover after choosing that platform's
        # exact paper, binding and page count.
        blockers = publisher.blocking_issues(issues)
        folder = marketplace_handoff_folder(package, PREPARED_FOLDER_NAMES.get(key, key)) if package else None
        status = str(record.get("status") or "Not Prepared")
        label_text, indicator = _readiness(status, blockers)
        rows.append({
            "key": key,
            "label": publisher.label,
            "portal_url": getattr(publisher, "portal_url", ""),
            "status": status,
            "readiness_label": label_text,
            "indicator": indicator,
            "issues": issues,
            "has_local_folder": bool(folder and folder.is_dir()),
            "external_id": str(record.get("external_id") or ""),
            "url": str(record.get("url") or ""),
            "updated_at": str(record.get("updated_at") or ""),
            "error_message": str(record.get("error_message") or ""),
            "integration_state": str(record.get("integration_state") or ""),
            "last_synced_at": str(record.get("last_synced_at") or ""),
        })
    return rows


def online_state_text(integration_state: str) -> str:
    """Plain-English sentence for an automated integration state ('' = none).

    Every phrase is deliberately truthful: a draft on Etsy is NOT published,
    and the app never claims otherwise.
    """
    state = str(integration_state or "").strip()
    if not state:
        return ""
    if state == "draft_created":
        return ("Online status: a draft listing was created on Etsy — it is NOT published. "
                "Review and publish it yourself in Etsy Shop Manager.")
    if state == "files_uploaded":
        return ("Online status: the Etsy draft is complete with its digital file attached — still NOT published. "
                "Finish the details and publish it yourself in Etsy Shop Manager.")
    if state == "complete":
        return ("Online status: the Etsy draft was verified online with your file attached — waiting for you to review and publish. "
                "Nothing goes live until you publish it in Etsy Shop Manager.")
    return f"Online status: {state.replace('_', ' ')}. Open View history for details."


def whats_left(rows: list[dict]) -> dict:
    """Count each marketplace's state so the Hub can say '2 of 7 published'."""
    counts = {"total": len(rows), "published": 0, "uploaded": 0,
              "ready_to_upload": 0, "ready_to_prepare": 0, "final_cover_needed": 0,
              "needs_attention": 0, "needs_items": 0}
    for row in rows:
        counts[{
            "Published": "published",
            "Uploaded": "uploaded",
            "Ready": "ready_to_upload",
            "Prepared — Final Cover Needed": "final_cover_needed",
            "Error": "needs_attention",
            "Needs Review": "needs_items",
            "Not Prepared": "ready_to_prepare",
        }.get(row["status"], "ready_to_prepare")] += 1
    return counts


def next_actions(rows: list[dict]) -> list[str]:
    """Prioritized plain-English tasks; errors first, capped for readability."""
    actions: list[str] = []
    for row in rows:
        if row["status"] != "Error":
            continue
        detail = row["error_message"] or "try preparing it again"
        actions.append(f"Fix {row['label']} first: {detail}")
    for row in rows:
        if row["status"] != "Needs Review":
            continue
        actions.append(row["issues"][0] if row["issues"] else f"Check what {row['label']} still needs before preparing.")
    for row in rows:
        if row["status"] == "Not Prepared" and not row["issues"] and row["key"] not in OPTIONAL_MARKETPLACES:
            actions.append(f"Prepare the {row['label']} package")
    for row in rows:
        if row["status"] == "Ready":
            actions.append(f"Upload the prepared {row['label']} files, then record your listing details.")
        if row["status"] == "Prepared — Final Cover Needed":
            actions.append(f"Build the final {row['label']} cover from its current template, then upload the finished printer files.")
    for row in rows:
        if row["status"] == "Uploaded":
            actions.append(f"When {row['label']} shows live, mark it Published and save its listing link.")
    return actions[:5]


def classify_prepare_report(report: list[tuple[str, str, str]]) -> dict:
    """Bucket prepare_many() results so the GUI can report truthfully.

    The status strings come only from our own service code: "Ready",
    "Prepared — Final Cover Needed", "Needs Review", "Already {status}",
    and "Error: {message}".
    """
    buckets = {"prepared": [], "final_cover_needed": [], "needs_review": [],
               "already_confirmed": [], "errors": [], "other": []}
    for book_id, marketplace, result in report:
        if result == "Ready":
            buckets["prepared"].append((book_id, marketplace))
        elif result == "Prepared — Final Cover Needed":
            buckets["final_cover_needed"].append((book_id, marketplace))
        elif result == "Needs Review":
            buckets["needs_review"].append((book_id, marketplace))
        elif result.startswith("Already "):
            buckets["already_confirmed"].append((book_id, marketplace, result[len("Already "):]))
        elif result.startswith("Error: "):
            buckets["errors"].append((book_id, marketplace, result[len("Error: "):]))
        else:
            buckets["other"].append((book_id, marketplace, result))
    return buckets


def format_history(entries: list[dict]) -> str:
    """Render audit rows as a human story: day headers, newest first.

    Entries arrive newest-first from ``audit_history``.  When the stream
    mixes marketplaces, each event is prefixed with its platform label.
    """
    if not entries:
        return "No publishing history yet."
    multi = len({entry.get("marketplace") for entry in entries}) > 1
    days: dict[str, list[str]] = {}
    for entry in entries:
        marketplace = entry.get("marketplace", "")
        label = PUBLISHERS[marketplace].label if marketplace in PUBLISHERS else marketplace
        source, new_status = entry.get("source", ""), entry.get("new_status", "")
        external_id, listing_url = entry.get("external_id") or "", entry.get("listing_url") or ""
        id_noun = ID_NOUNS.get(marketplace, "ID")
        if source == "prepare" and new_status == "Ready":
            phrase = "Prepared the upload package"
        elif source == "prepare" and new_status == "Prepared — Final Cover Needed":
            phrase = "Prepared the starting files; a final platform cover is still needed"
        elif source == "prepare" and new_status == "Error":
            message = entry.get("error_message") or ""
            phrase = f"Preparation failed: {message}" if message else "Preparation failed"
        elif source == "prepare" and new_status == "Needs Review":
            phrase = "Checked before preparing; required items were missing"
        elif source == "local_scan":
            phrase = ("Found the prepared folder; a final platform cover is still needed"
                      if new_status == "Prepared — Final Cover Needed" else "Found the prepared folder on disk")
        elif new_status == "Uploaded":
            phrase = "Recorded as Uploaded" + (f" — {id_noun}: {external_id}" if external_id else "")
        elif new_status == "Published":
            phrase = "Marked Published" + (f" — {id_noun}: {external_id}" if external_id else "")
        elif old := entry.get("old_status"):
            phrase = f"Saved listing details ({old} → {new_status})" if old == new_status else f"Changed from {old} to {new_status}"
        else:
            phrase = f"Updated to {new_status}"
        prefix = f"{label} — " if multi else ""
        lines = [f"{prefix}{phrase}"]
        if listing_url:
            lines.append(f"  Listing: {listing_url}")
        changed_at = str(entry.get("changed_at") or "")
        try:
            day = datetime.fromisoformat(changed_at).strftime("%b %d, %Y")
        except ValueError:
            day = changed_at[:10] or "Unknown date"
        days.setdefault(day, []).extend(lines)
    out: list[str] = []
    for day, events in days.items():
        out.append(day)
        out.extend(f"  {line}" if not line.startswith("  ") else line for line in events)
    return "\n".join(out)
