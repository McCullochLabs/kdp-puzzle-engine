from __future__ import annotations

from pathlib import Path

import pytest

from background_generation.index import CoverAssetApprovalError
from publishing.production_orchestrator import ProductionJobIndex, ProductionOrchestrator, plan_review_summary


def _context(book_id="book-1", puzzle_type="word_search", **changes):
    value = {
        "book_id": book_id, "book_plan_id": f"plan-{book_id}", "source_revision": "source-a",
        "capacity_proof": "capacity-a", "puzzle_type": puzzle_type, "puzzle_count": 48,
        "items_per_puzzle": 12, "difficulty": "standard", "seed": 17,
        "title": f"{puzzle_type} Test Book", "subtitle": "A safe test",
        "author": "Jordan M. Slade", "topic": "Gardening", "audience": "adults",
        "series": "", "large_print": True, "signature_edition": False,
        "no_repeat_words": True, "page_count": 112, "trim_size": "8.5x11",
        "cover_art_id": "approved-art", "cover_art_sha256": "art-a",
        "cover_style": "photo", "palette": "nature", "priority": "normal",
    }
    value.update(changes)
    return value


def _approve_plan(job):
    job.complete("idea"); job.complete("feasibility")
    job.approve_human_stage("content_plan", source="saved_book_plan_review", evidence_id="review-plan-1")


def _through_package(job, root: Path):
    root.mkdir(parents=True, exist_ok=True)
    _approve_plan(job)
    interior = root / "interior.pdf"; interior.write_bytes(b"pdf")
    cover = root / "front_cover.png"; cover.write_bytes(b"png")
    qa = root / "PRODUCT_QA.json"; qa.write_text("{}", encoding="utf-8")
    listing = root / "KDP_LISTING_KIT.txt"; listing.write_text("listing", encoding="utf-8")
    package = root / "package"; package.mkdir(exist_ok=True)
    job.complete("generation", artifact=str(interior))
    job.complete("cover", artifact=str(cover))
    job.complete("product_qa", artifact=str(qa))
    job.complete("listing", artifact=str(listing))
    job.complete("package", artifact=str(package))
    return interior, cover, package


def test_full_happy_path_stops_at_real_human_gates(tmp_path):
    job = ProductionOrchestrator(tmp_path, "book-1"); job.start(_context())
    _through_package(job, tmp_path)
    assert job.state().current_stage == "final_review"
    job.approve_human_stage("final_review", source="publishing_database.final_local_reviews", evidence_id="proof-1:review-1")
    assert job.state().current_stage == "platform_preview"
    job.complete("platform_preview", detail="Local platform preview opened and checked.")
    assert job.state().current_stage == "marketplace_handoff"
    job.approve_human_stage("marketplace_handoff", source="operator_handoff", evidence_id="handoff-1")
    assert job.state().status == "complete"


def test_resume_after_real_interior_artifact_starts_at_cover(tmp_path):
    job = ProductionOrchestrator(tmp_path, "book-1"); job.start(_context()); _approve_plan(job)
    interior = tmp_path / "interior.pdf"; interior.write_bytes(b"pdf")
    job.complete("generation", artifact=str(interior))
    reloaded = ProductionOrchestrator(tmp_path, "book-1"); reloaded.start(_context())
    assert reloaded.state().current_stage == "cover"


def test_resume_after_real_cover_starts_at_product_qa(tmp_path):
    job = ProductionOrchestrator(tmp_path, "book-1"); job.start(_context()); _approve_plan(job)
    interior = tmp_path / "interior.pdf"; interior.write_bytes(b"pdf")
    cover = tmp_path / "cover.png"; cover.write_bytes(b"png")
    job.complete("generation", artifact=str(interior)); job.complete("cover", artifact=str(cover))
    reloaded = ProductionOrchestrator(tmp_path, "book-1"); reloaded.start(_context())
    assert reloaded.state().current_stage == "product_qa"


def test_missing_artifact_resumes_exact_stage_without_rebuilding_upstream(tmp_path):
    job = ProductionOrchestrator(tmp_path, "book-1"); job.start(_context()); _approve_plan(job)
    missing = tmp_path / "missing-interior.pdf"
    job.complete("generation", artifact=str(missing))
    job.start(_context())
    assert job.state().current_stage == "generation"
    assert job.load()["steps"]["content_plan"]["status"] == "approved"


def test_content_plan_change_stales_interior_but_cover_only_change_does_not(tmp_path):
    job = ProductionOrchestrator(tmp_path, "book-1"); job.start(_context()); _through_package(job, tmp_path)
    job.start(_context(source_revision="source-b"))
    assert job.load()["steps"]["generation"]["status"] == "stale"

    other = ProductionOrchestrator(tmp_path, "book-2"); other.start(_context("book-2")); _through_package(other, tmp_path / "other")
    other.start(_context("book-2", cover_art_sha256="art-b"))
    assert other.load()["steps"]["generation"]["status"] == "complete"
    assert other.load()["steps"]["cover"]["status"] == "stale"


def test_unapproved_cover_failure_is_recorded_and_never_bypassed(tmp_path):
    job = ProductionOrchestrator(tmp_path, "book-1"); job.start(_context()); _approve_plan(job)
    interior = tmp_path / "interior.pdf"; interior.write_bytes(b"pdf")
    job.complete("generation", artifact=str(interior))
    result = job.continue_production({"cover": lambda: (_ for _ in ()).throw(CoverAssetApprovalError("COVER ART REQUIRED"))})
    step = job.load()["steps"]["cover"]
    assert result["status"] == "blocked"
    assert step["error_type"] == "CoverAssetApprovalError"
    assert "product_qa" in step["affected_stages"]


def test_generator_failure_retry_does_not_corrupt_approved_plan(tmp_path):
    job = ProductionOrchestrator(tmp_path, "book-1"); job.start(_context()); _approve_plan(job)
    failed = job.continue_production({"generation": lambda: (_ for _ in ()).throw(RuntimeError("generator stopped"))})
    assert failed["status"] == "blocked"
    interior = tmp_path / "interior.pdf"; interior.write_bytes(b"pdf")
    retried = job.retry("generation", lambda: {"artifact": str(interior), "detail": "recreated deterministically"})
    assert retried["status"] == "complete"
    assert job.load()["steps"]["content_plan"]["status"] == "approved"


def test_package_retry_does_not_regenerate_interior_or_cover(tmp_path):
    job = ProductionOrchestrator(tmp_path, "book-1"); job.start(_context()); _through_package(job, tmp_path)
    job.fail("package", "manifest missing", error_type="MissingArtifact")
    before = {name: dict(job.load()["steps"][name]) for name in ("generation", "cover")}
    package = tmp_path / "repaired-package"; package.mkdir()
    assert job.retry("package", lambda: {"artifact": str(package), "detail": "manifest rebuilt"})["status"] == "complete"
    after = job.load()["steps"]
    assert after["generation"] == before["generation"]
    assert after["cover"] == before["cover"]


def test_local_listing_fallback_completes_without_external_call(tmp_path):
    job = ProductionOrchestrator(tmp_path, "book-1"); job.start(_context()); _approve_plan(job)
    interior = tmp_path / "interior.pdf"; interior.write_bytes(b"pdf")
    cover = tmp_path / "cover.png"; cover.write_bytes(b"png")
    qa = tmp_path / "qa.json"; qa.write_text("{}", encoding="utf-8")
    job.complete("generation", artifact=str(interior)); job.complete("cover", artifact=str(cover)); job.complete("product_qa", artifact=str(qa))
    result = job.continue_production({"listing": lambda: {"detail": "Gemini unavailable; validated local listing used"}})
    assert result["status"] == "complete"
    assert "local listing" in job.load()["steps"]["listing"]["detail"]


def test_human_gate_cannot_be_fabricated(tmp_path):
    job = ProductionOrchestrator(tmp_path, "book-1"); job.start(_context()); job.complete("idea"); job.complete("feasibility")
    with pytest.raises(ValueError, match="cannot be completed automatically"):
        job.complete("content_plan")
    with pytest.raises(ValueError, match="persisted human-review evidence"):
        job.complete("content_plan", approved=True)


def test_plan_review_summary_shows_all_operator_decision_facts():
    summary = plan_review_summary(_context(signature_edition=True))
    for expected in ("Title:", "Topic: Gardening", "Puzzle type: Word Search", "Puzzles: 48",
                     "Words/items per puzzle: 12", "Difficulty: Standard", "Edition: Signature Edition"):
        assert expected in summary


def test_stop_preserves_completed_work_and_continue_resumes(tmp_path):
    job = ProductionOrchestrator(tmp_path, "book-1"); job.start(_context()); _approve_plan(job)
    job.stop(detail="Operator paused the test.")
    assert job.state().status == "stopped"
    interior = tmp_path / "interior.pdf"; interior.write_bytes(b"pdf")
    result = job.continue_production({"generation": lambda: {"artifact": str(interior)}})
    assert result["status"] == "complete"
    assert job.load()["steps"]["content_plan"]["status"] == "approved"


def test_job_index_filters_persisted_jobs_without_output_scan(tmp_path):
    high = ProductionOrchestrator(tmp_path, "high"); high.start(_context("high", "sudoku", priority="high")); high.complete("idea")
    normal = ProductionOrchestrator(tmp_path, "normal"); normal.start(_context("normal", priority="normal")); normal.complete("idea")
    rows = ProductionJobIndex(tmp_path).rows(puzzle_type="sudoku", priority="high")
    assert [row["book_id"] for row in rows] == ["high"]


@pytest.mark.parametrize("puzzle_type,count", [
    ("word_search", 10), ("sudoku", 5), ("cryptogram", 5),
    ("scramble_trivia", 5), ("mixed", 5),
])
def test_cross_format_stress_jobs_are_resumable_and_make_no_external_calls(tmp_path, puzzle_type, count):
    for number in range(count):
        book_id = f"{puzzle_type}-{number}"
        job = ProductionOrchestrator(tmp_path, book_id); job.start(_context(book_id, puzzle_type))
        _approve_plan(job)
        interior = tmp_path / f"{book_id}.pdf"; interior.write_bytes(b"pdf")
        job.complete("generation", artifact=str(interior))
        if number % 3 == 0:
            job.stop(); assert job.state().status == "stopped"; job.start(_context(book_id, puzzle_type))
        assert job.state().current_stage == "cover"
