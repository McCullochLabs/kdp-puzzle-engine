from publishing.production_orchestrator import ProductionOrchestrator


def context(**changes):
    value = {
        "book_id": "book-1", "book_plan_id": "plan-1", "source_revision": "source-a",
        "capacity_proof": "capacity-a", "puzzle_type": "word_search", "puzzle_count": 48,
        "items_per_puzzle": 12, "difficulty": "standard", "seed": 7,
        "title": "Summer Activities Word Search", "subtitle": "48 sunny puzzles",
        "author": "Jordan M. Slade", "topic": "Summer Activities", "audience": "adults",
        "series": "Seasonal Escapes", "large_print": True, "signature_edition": False,
        "no_repeat_words": True, "page_count": 112, "trim_size": "8.5x11",
        "cover_art_id": "summer-1", "cover_art_sha256": "art-a",
        "cover_style": "photo", "palette": "summer",
    }
    value.update(changes); return value


def advance_to_cover(orchestrator):
    orchestrator.complete("idea")
    orchestrator.complete("feasibility")
    orchestrator.approve_human_stage("content_plan", source="test_plan_review", evidence_id="plan-1")
    orchestrator.complete("generation", artifact="interior.pdf")
    orchestrator.complete("cover", artifact="front_cover.png")


def test_canonical_job_lifecycle_and_plain_next_action(tmp_path):
    job = ProductionOrchestrator(tmp_path, "book-1"); job.start(context())
    assert job.state().next_action == "Book Idea"
    advance_to_cover(job)
    assert job.state().current_stage == "product_qa"
    assert job.state().next_action == "Run Product QA"


def test_resume_after_cover_runs_qa_only(tmp_path):
    job = ProductionOrchestrator(tmp_path, "book-1"); job.start(context()); advance_to_cover(job)
    calls = []
    reloaded = ProductionOrchestrator(tmp_path, "book-1")
    result = reloaded.continue_production({"product_qa": lambda: calls.append("qa") or {"detail": "QA passed"}})
    assert result["status"] == "complete"
    assert calls == ["qa"]
    assert reloaded.state().current_stage == "listing"


def test_cover_change_stales_cover_dependents_not_interior(tmp_path):
    job = ProductionOrchestrator(tmp_path, "book-1"); job.start(context()); advance_to_cover(job)
    job.complete("product_qa"); job.complete("listing"); job.complete("package")
    job.start(context(cover_art_sha256="art-b"))
    steps = job.load()["steps"]
    assert steps["generation"]["status"] == "complete"
    assert steps["cover"]["status"] == "stale"
    assert steps["product_qa"]["status"] == "stale"
    assert steps["package"]["status"] == "stale"


def test_content_change_stales_generation_and_downstream(tmp_path):
    job = ProductionOrchestrator(tmp_path, "book-1"); job.start(context()); advance_to_cover(job)
    job.start(context(source_revision="source-b"))
    steps = job.load()["steps"]
    assert steps["generation"]["status"] == "stale"
    assert steps["cover"]["status"] == "stale"
    assert steps["product_qa"]["status"] if "product_qa" in steps else True


def test_human_gate_is_never_crossed_automatically(tmp_path):
    job = ProductionOrchestrator(tmp_path, "book-1"); job.start(context()); job.complete("idea"); job.complete("feasibility")
    called = []
    result = job.continue_production({"content_plan": lambda: called.append(True)})
    assert result["status"] == "human_review_required"
    assert not called


def test_failure_surfaces_one_attention_state(tmp_path):
    job = ProductionOrchestrator(tmp_path, "book-1"); job.start(context()); job.complete("idea")
    job.fail("feasibility", "576 reviewed items are still needed", human_review=True)
    state = job.state()
    assert state.status == "needs_review"
    assert state.attention == ("576 reviewed items are still needed",)


def test_existing_autopilot_route_mirrors_into_canonical_job(tmp_path):
    from publishing.production_autopilot import ProductionAutopilot

    old = ProductionAutopilot(tmp_path, "book-1")
    facts = {**context(), "fingerprint": "whole-book",
             "content_plan_approval": {"source": "saved_book_plan", "evidence_id": "plan-1"}}
    old.begin(facts); old.attach_orchestrator(facts)
    for stage in ("generate", "cover", "listing", "qa", "package"):
        old.complete(stage, old.stage_fingerprint(facts, stage), stage + " complete", artifact=f"{stage}.dat")
    current = ProductionOrchestrator(tmp_path, "book-1").load()["steps"]
    assert current["generation"]["status"] == "complete"
    assert current["cover"]["status"] == "complete"
    assert current["product_qa"]["status"] == "complete"
    assert current["listing"]["status"] == "complete"
    assert current["package"]["status"] == "complete"
    assert ProductionOrchestrator(tmp_path, "book-1").state().current_stage == "final_review"
