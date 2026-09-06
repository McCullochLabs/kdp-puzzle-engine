from publishing.production_orchestrator import ProductionOrchestrator


PUZZLE_TYPES = ("word_search", "sudoku", "cryptogram", "scramble_trivia", "mixed")


def facts(book_id, puzzle_type, revision="source-a"):
    return {
        "book_id": book_id, "book_plan_id": f"plan-{book_id}", "source_revision": revision,
        "capacity_proof": f"capacity-{book_id}", "puzzle_type": puzzle_type,
        "puzzle_count": 48, "items_per_puzzle": 12, "difficulty": "standard", "seed": 17,
        "title": f"Test {puzzle_type} {book_id}", "subtitle": "Local stress fixture",
        "author": "Jordan M. Slade", "topic": "General Interest", "audience": "adults",
        "series": "", "large_print": True, "signature_edition": False,
        "no_repeat_words": True, "page_count": 112, "trim_size": "8.5x11",
        "cover_art_id": "fixture-art", "cover_art_sha256": "art-a",
        "cover_style": "illustrated", "palette": "studio",
    }


def test_thirty_jobs_resume_and_stale_only_the_correct_dependencies(tmp_path):
    for index in range(30):
        puzzle_type = PUZZLE_TYPES[index % len(PUZZLE_TYPES)]
        book_id = f"stress-{index:02d}"
        job = ProductionOrchestrator(tmp_path, book_id)
        job.start(facts(book_id, puzzle_type))
        for stage in ("idea", "feasibility"):
            job.complete(stage)
        job.approve_human_stage("content_plan", source="test_plan_review", evidence_id=f"plan-{index}")
        job.complete("generation", artifact="interior.pdf")
        job.complete("cover", artifact="front_cover.png")
        assert ProductionOrchestrator(tmp_path, book_id).state().current_stage == "product_qa"
        job.complete("product_qa")
        job.complete("listing")
        job.complete("package")
        job.approve_human_stage("final_review", source="test_final_review", evidence_id=f"review-{index}")
        job.complete("platform_preview")
        assert job.state().current_stage == "marketplace_handoff"

        job.start(facts(book_id, puzzle_type, revision="source-b"))
        assert job.load()["steps"]["generation"]["status"] == "stale"


def test_failure_and_retry_do_not_cross_a_human_gate(tmp_path):
    job = ProductionOrchestrator(tmp_path, "retry-book")
    job.start(facts("retry-book", "word_search"))
    job.complete("idea")
    job.fail("feasibility", "Reviewed content is incomplete.")
    assert job.state().status == "blocked"
    job.complete("feasibility")
    calls = []
    result = job.continue_production({"content_plan": lambda: calls.append("unsafe")})
    assert result["status"] == "human_review_required"
    assert calls == []
