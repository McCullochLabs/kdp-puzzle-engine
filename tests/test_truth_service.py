from __future__ import annotations

from pathlib import Path

from publishing.database import PublishingDatabase
from publishing.truth_service import PublishingTruthService
from background_generation.index import BackgroundAssetIndex, file_sha256, write_cover_approval_proof


class _Service:
    def __init__(self, root: Path) -> None:
        self.project = root
        self.db = PublishingDatabase(root / "books.db")


def _book(root: Path, monkeypatch) -> tuple[_Service, str, Path]:
    monkeypatch.setenv("SLADE_COVER_ASSET_REGISTRY", str(root / "cover_registry.json"))
    service = _Service(root)
    package = root / "package"
    for folder in ("01_PRINT_UPLOADS", "02_LISTING_INFORMATION", "03_PREVIEWS", "04_REVIEW_AND_RECORDS"):
        (package / folder).mkdir(parents=True, exist_ok=True)
    for name in ("interior.pdf", "kdp_full_wrap.pdf"):
        (package / "01_PRINT_UPLOADS" / name).write_bytes(b"pdf")
    front = package / "03_PREVIEWS" / "front_cover.png"
    from PIL import Image
    Image.new("RGB", (2550, 3300), "#365f58").save(front)
    art = root / "approved_art.png"; Image.new("RGB", (900, 900), "#527b64").save(art)
    row = {"asset_id":"approved-fixture", "path":str(art), "topics":["gardening"], "approval_state":"approved", "production_approved":True, "project_generated":True, "classification":"APPROVED_PROJECT_GENERATED", "sha256":file_sha256(art), "provenance":{"provider":"SladePuzzleCo project generation"}}
    BackgroundAssetIndex().save({"assets":[row]}); write_cover_approval_proof(front, row)
    (package / "02_LISTING_INFORMATION" / "KDP_LISTING_KIT.txt").write_text("listing", encoding="utf-8")
    (package / "04_REVIEW_AND_RECORDS" / "PUBLISHER_PREFLIGHT.txt").write_text("pass", encoding="utf-8")
    (package / "04_REVIEW_AND_RECORDS" / "PACKAGE_SOURCE_RECORD.json").write_text("{}", encoding="utf-8")
    (package / "04_REVIEW_AND_RECORDS" / "PRODUCTION_PROOF_GATE.txt").write_text("proof", encoding="utf-8")
    source = root / "source.json"
    source.write_text('{"title":"Garden Search","author":"Jordan M. Slade","puzzles":[{"words":["TROWEL"]}]}', encoding="utf-8")
    service.db.upsert_book("book", str(source), {"title": "Garden Search", "author": "Jordan M. Slade", "files": {"front_cover": str(package / "03_PREVIEWS" / "front_cover.png")}, "production_status": "Complete package"}, str(package))
    return service, "book", package


def test_truth_service_composes_existing_book_facts_without_writing(tmp_path, monkeypatch):
    service, book_id, package = _book(tmp_path, monkeypatch)
    service.db.save_cover_concept(book_id, "Garden", {"palette": "nature"}, selected=True)

    snapshot = PublishingTruthService(service).for_book(book_id)

    assert snapshot["catalog_authoritative"] is True
    assert snapshot["package_contract"]["ready"] is True
    assert snapshot["cover"]["state"] == "selected_direction_with_render"
    assert snapshot["content_and_source"]["stage"] == "Needs attention"
    assert snapshot["content_and_source"]["blockers"]
    assert Path(snapshot["cover"]["front_cover"]) == package / "03_PREVIEWS" / "front_cover.png"
    assert snapshot["cover"]["render_sha256"]
    assert snapshot["cover"]["release_lock"] == {}


def test_truth_service_reports_exact_marketplace_handoff_state(tmp_path, monkeypatch):
    service, book_id, _package = _book(tmp_path, monkeypatch)

    handoff = PublishingTruthService(service).upload_files(book_id, "amazon")

    assert handoff["marketplace"] == "amazon"
    assert handoff["status"] == "Not Prepared"
    assert handoff["has_local_folder"] is False


def test_truth_service_binds_selected_cover_to_existing_release_lock(tmp_path, monkeypatch):
    service, book_id, package = _book(tmp_path, monkeypatch)
    service.db.save_cover_concept(book_id, "Garden", {"palette": "nature"}, selected=True)
    service.db.lock_release(book_id)

    cover = PublishingTruthService(service).for_book(book_id)["cover"]

    assert cover["release_lock"]["revision"] == 1
    assert cover["release_lock"]["matches_final_render"] is True
    assert cover["release_lock"]["recorded_path"] == str(package / "03_PREVIEWS" / "front_cover.png")


def test_truth_service_surfaces_related_legacy_creator_error_without_copying_it(tmp_path, monkeypatch):
    service, book_id, _package = _book(tmp_path, monkeypatch)
    (tmp_path / "error_log.json").write_text(
        '[{"book":"Garden Search","what_happened":"Cover export stopped","suggestion":"Choose a cover image."},'
        '{"book":"Other Book","what_happened":"Ignore me","suggestion":""}]', encoding="utf-8"
    )

    snapshot = PublishingTruthService(service).for_book(book_id)

    assert len(snapshot["creator_errors"]) == 1
    assert "Cover export stopped" in snapshot["attention"][-1]
