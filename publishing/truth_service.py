"""Read-only answers that compose the existing publishing sources of truth.

This module deliberately owns no state.  It exists so UI screens can ask one
place for the current answer without reimplementing readiness rules.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from .error_feed import related_creator_errors
from .package_layout import package_file, release_contract
from .production_gate import book_gate
from .readiness import marketplace_rows, next_actions


class PublishingTruthService:
    """Compose catalog, package, cover, and marketplace facts without writes."""

    def __init__(self, publishing_service) -> None:
        self.service = publishing_service

    def for_book(self, book_id: str) -> dict:
        book = self.service.db.get_book(book_id)
        if not book:
            raise ValueError("Book was not found in the Publishing Center.")
        package_text = str(book.get("package_path") or "").strip()
        package = Path(package_text) if package_text else Path("__no_catalog_package__")
        package_exists = bool(package_text) and package.is_dir()
        gate = book_gate(book)
        records = self.service.db.marketplace_records(book_id)
        marketplace = marketplace_rows(book, records)
        contract = release_contract(package) if package_exists else {
            "ready": False, "required": (), "missing": ("complete package",),
        }
        cover = self._cover_truth(book, package)
        creator_errors = related_creator_errors(
            self.service.project, str((book.get("metadata") or {}).get("title") or "")
        )
        attention = list(gate.get("blockers") or [])
        if package_exists and not contract["ready"]:
            attention.append("Package contract is incomplete: " + ", ".join(contract["missing"]))
        attention.extend(row["error_message"] for row in marketplace if row.get("error_message"))
        attention.extend(
            "Creator error: {0}{1}".format(
                item["what_happened"],
                f" Suggested fix: {item['suggestion']}" if item.get("suggestion") else "",
            )
            for item in creator_errors if item.get("what_happened")
        )
        attention = list(dict.fromkeys(item for item in attention if item))
        return {
            "book": book,
            "content_and_source": gate,
            "package_contract": contract,
            "cover": cover,
            "creator_errors": creator_errors,
            "marketplaces": marketplace,
            "attention": attention,
            "next_actions": next_actions(marketplace),
            "catalog_authoritative": True,
        }

    def upload_files(self, book_id: str, marketplace: str) -> dict:
        """Return the exact current local handoff state without preparing it."""
        snapshot = self.for_book(book_id)
        row = next((item for item in snapshot["marketplaces"] if item["key"] == marketplace), None)
        if not row:
            raise ValueError("Unknown marketplace.")
        return {
            "marketplace": marketplace,
            "status": row["status"],
            "prepared_folder": row.get("folder", ""),
            "has_local_folder": bool(row.get("has_local_folder")),
            "issues": list(row.get("issues") or []),
            "message": row["readiness_label"],
        }

    def _cover_truth(self, book: dict, package: Path) -> dict:
        concepts = self.service.db.cover_concepts(book["book_id"])
        selected = next((item for item in concepts if item.get("selected")), None)
        front = package_file(package, "front_cover.png") if package.is_dir() else Path(
            str(((book.get("metadata") or {}).get("files") or {}).get("front_cover") or "")
        )
        render_sha256 = hashlib.sha256(front.read_bytes()).hexdigest() if front.is_file() else ""
        release_lock = self.service.db.latest_release_lock_snapshot(book["book_id"])
        locked_cover = None
        if release_lock and render_sha256:
            locked_cover = next(
                (item for item in (release_lock["snapshot"].get("file_checksums") or {}).values()
                 if isinstance(item, dict) and str(item.get("sha256") or "") == render_sha256),
                None,
            )
        current_proof = ((release_lock or {}).get("snapshot") or {}).get("phase4_production_proof") or {}
        proof_id = str(current_proof.get("proof_id") or "")
        final_review = (
            self.service.db.final_local_review(book["book_id"], proof_id=proof_id, package_path=str(package))
            if package.is_dir() and proof_id else None
        )
        if selected and front.is_file():
            state = "selected_direction_with_render"
            message = "A selected cover direction and final front-cover render are recorded."
        elif front.is_file():
            state = "render_needs_direction_review"
            message = "A front-cover render exists, but no selected cover direction is recorded."
        else:
            state = "cover_missing"
            message = "No final front-cover render is recorded."
        return {
            "state": state,
            "message": message,
            "selected_concept": selected or {},
            "front_cover": str(front) if front.is_file() else "",
            "render_sha256": render_sha256,
            "release_lock": {
                "revision": release_lock.get("revision"),
                "locked_at": release_lock.get("locked_at"),
                "matches_final_render": bool(locked_cover),
                "recorded_path": str(locked_cover.get("path") or "") if locked_cover else "",
            } if release_lock else {},
            "final_local_review": final_review or {},
            "review_note": (
                "The selected direction is bound to the latest locked cover file."
                if locked_cover else
                "This cover is not yet bound to a release lock; lock the release only after final review."
            ),
        }
