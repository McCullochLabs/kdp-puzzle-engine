"""Phase 4 proof tests use temporary packages only; no catalog files are changed."""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

from PIL import Image
from reportlab.pdfgen import canvas

from publishing.database import PublishingDatabase
from background_generation.index import BackgroundAssetIndex, file_sha256, write_cover_approval_proof
from publishing.production_proof import (
    artifact_manifest, book_plan_hash, build_production_proof, proof_is_current, write_proof_report,
)
from word_intelligence.book_planning import BookPlanner, PlanRequest
from word_intelligence.capacity import ContentCapacityEngine
from word_intelligence.content_contracts import ContentRecord, FormatRules, Provenance, QualityStatus, TopicReference, deterministic_content_id, normalized_value
from word_intelligence.content_registry import ContentRegistry
from word_intelligence.taxonomy import TopicTaxonomy
import pytest


@pytest.fixture(autouse=True)
def isolated_cover_registry(tmp_path, monkeypatch):
    monkeypatch.setenv("SLADE_COVER_ASSET_REGISTRY", str(tmp_path / "cover_registry.json"))


def _record(word: str) -> ContentRecord:
    return ContentRecord(
        id=deterministic_content_id("word", word, source_id="fixture:" + word), type="word", display=word,
        normalized=normalized_value(word), topics=(TopicReference("gardening", "primary", 100, "approved"),),
        format_rules=FormatRules(), quality=QualityStatus("approved", "verified", False, False),
        provenance=Provenance("curated", "fixture:" + word),
    )


def _planner():
    taxonomy = TopicTaxonomy.from_master_bank({"topics": {"Gardening": ["TROWEL"]}})
    registry = ContentRegistry()
    for number in range(12):
        word = "TERM" + chr(65 + number)
        registry.add(_record(word))
    engine = ContentCapacityEngine(".", taxonomy, registry, cache_state={"state": "fresh"})
    engine.source_revision = "fixture-revision"; engine.reservation_evidence = []
    return BookPlanner(engine), taxonomy.resolve("Gardening")


def _pdf(path: Path) -> None:
    page = canvas.Canvas(str(path)); page.drawString(72, 720, "Phase 4 fixture"); page.showPage(); page.save()


def _package(tmp_path: Path) -> Path:
    root = tmp_path / "package"
    for folder in ("01_PRINT_UPLOADS", "02_LISTING_INFORMATION", "03_PREVIEWS", "04_REVIEW_AND_RECORDS"):
        (root / folder).mkdir(parents=True, exist_ok=True)
    _pdf(root / "01_PRINT_UPLOADS" / "interior.pdf")
    _pdf(root / "01_PRINT_UPLOADS" / "kdp_full_wrap.pdf")
    Image.new("RGB", (2550, 3300), "#2d475a").save(root / "03_PREVIEWS" / "front_cover.png")
    art = tmp_path / "approved_art.png"; Image.new("RGB", (900, 900), "#285a73").save(art)
    row = {"asset_id": "approved-fixture", "path": str(art), "topics": ["gardening"],
           "classification": "APPROVED_PROJECT_GENERATED", "approval_state": "approved",
           "production_approved": True, "project_generated": True, "sha256": file_sha256(art),
           "provenance": {"provider": "SladePuzzleCo project generation"}}
    BackgroundAssetIndex().save({"assets": [row]})
    write_cover_approval_proof(root / "03_PREVIEWS" / "front_cover.png", row)
    (root / "02_LISTING_INFORMATION" / "KDP_LISTING_KIT.txt").write_text("Listing", encoding="utf-8")
    (root / "04_REVIEW_AND_RECORDS" / "PUBLISHER_PREFLIGHT.txt").write_text("Pass", encoding="utf-8")
    (root / "04_REVIEW_AND_RECORDS" / "PACKAGE_SOURCE_RECORD.json").write_text(json.dumps({"cover_art": str(art)}), encoding="utf-8")
    (root / "04_REVIEW_AND_RECORDS" / "PRODUCTION_PROOF_GATE.txt").write_text("Prior fixture proof", encoding="utf-8")
    return root


def _plan():
    planner, topic = _planner()
    result = planner.create(PlanRequest(topic, "word_search", 1, 12, seed=51))
    assert result.plan
    return planner, result.plan


def test_book_plan_hash_is_canonical_and_ignores_creation_timestamp():
    _planner, plan = _plan()
    changed_time = replace(plan, created_at="2099-01-01T00:00:00+00:00")
    changed_seed = replace(plan, seed=52)
    assert book_plan_hash(plan) == book_plan_hash(changed_time)
    assert book_plan_hash(plan) != book_plan_hash(changed_seed)


def test_valid_proof_hashes_artifacts_and_is_current(tmp_path):
    planner, plan = _plan(); package = _package(tmp_path)
    proof = build_production_proof(tmp_path, plan, package, planner=planner,
                                   generation_evidence={"selected_content_ids": plan.selected_content_ids})
    assert proof.status == "needs_review", proof.blocking_reasons
    assert proof.artifacts["interior"]["sha256"] and proof.artifacts["wrap"]["sha256"]
    assert proof.artifacts["cover_approval"]["asset_id"] == "approved-fixture"
    assert proof_is_current(proof, plan, package) == (True, [])
    report = write_proof_report(package / "04_REVIEW_AND_RECORDS" / "PHASE4_PROOF.txt", proof)
    assert report.is_file()


def test_missing_required_artifact_hard_blocks(tmp_path):
    planner, plan = _plan(); package = _package(tmp_path)
    (package / "01_PRINT_UPLOADS" / "interior.pdf").unlink()
    proof = build_production_proof(tmp_path, plan, package, planner=planner,
                                   generation_evidence={"selected_content_ids": plan.selected_content_ids})
    assert proof.status == "blocked" and any("interior" in item.casefold() for item in proof.blocking_reasons)


def test_artifact_or_plan_change_makes_a_proof_stale(tmp_path):
    planner, plan = _plan(); package = _package(tmp_path)
    proof = build_production_proof(tmp_path, plan, package, planner=planner,
                                   generation_evidence={"selected_content_ids": plan.selected_content_ids})
    (package / "03_PREVIEWS" / "front_cover.png").write_bytes(b"changed")
    current, reasons = proof_is_current(proof, plan, package)
    assert not current and any("Cover" in item for item in reasons)
    assert not proof_is_current(proof, replace(plan, seed=99), package)[0]
    _pdf(package / "01_PRINT_UPLOADS" / "interior.pdf")
    current, reasons = proof_is_current(proof, plan, package)
    assert not current and any("Wrap must be revalidated" in item for item in reasons)


def test_content_evidence_mismatch_and_human_listing_conflict_block(tmp_path):
    planner, plan = _plan(); package = _package(tmp_path)
    book = {"book_id": "fixture-book", "metadata": {"title": "Garden Plan", "puzzle_count": 1,
            "page_count": 1, "description": "Enjoy 100 puzzles in large print.",
            "human_edited_listing_fields": ["description"], "files": {}}}
    proof = build_production_proof(tmp_path, plan, package, planner=planner, book=book,
                                   generation_evidence={"selected_content_ids": list(reversed(plan.selected_content_ids))})
    assert proof.status == "blocked"
    assert any("Generated content evidence" in item for item in proof.blocking_reasons)
    assert any("Listing conflicts" in item for item in proof.blocking_reasons)


def test_legacy_compatible_proof_requires_human_acknowledgement(tmp_path):
    planner, topic = _planner(); package = _package(tmp_path)
    compatibility = planner.create(PlanRequest(topic, "word_search", 1, 12, seed=51, review_policy="legacy_compatible")).plan
    assert compatibility
    pending = build_production_proof(tmp_path, compatibility, package, planner=planner,
                                     generation_evidence={"selected_content_ids": compatibility.selected_content_ids})
    acknowledged = build_production_proof(tmp_path, compatibility, package, planner=planner,
                                          generation_evidence={"selected_content_ids": compatibility.selected_content_ids}, human_acknowledged=True)
    assert pending.status == "needs_review" and acknowledged.status == "needs_review"


def test_database_lock_keeps_marketplace_history_and_revisions(tmp_path):
    planner, plan = _plan(); package = _package(tmp_path)
    proof = build_production_proof(tmp_path, plan, package, planner=planner,
                                   generation_evidence={"selected_content_ids": plan.selected_content_ids})
    db = PublishingDatabase(tmp_path / "books.db")
    db.upsert_book("fixture", "fixture-source", {"title": "Garden Plan"}, str(package))
    db.transition_status("fixture", "amazon", "Published", external_id="ASIN", source="manual")
    first = db.lock_production_proof("fixture", replace(proof, status="ready_for_platform_preview").to_dict())
    changed = replace(proof, proof_id="changed-proof", status="ready_for_platform_preview")
    second = db.lock_production_proof("fixture", changed.to_dict())
    assert first["revision"] == 1 and second["revision"] == 2
    assert db.marketplace_records("fixture")["amazon"]["status"] == "Published"


def test_manifest_is_machine_readable_and_reports_missing_files(tmp_path):
    package = _package(tmp_path)
    manifest = artifact_manifest(package)
    assert manifest["cover"]["exists"]
    (package / "01_PRINT_UPLOADS" / "kdp_full_wrap.pdf").unlink()
    assert not artifact_manifest(package)["wrap"]["exists"]
