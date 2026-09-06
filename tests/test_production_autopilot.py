from publishing.production_autopilot import ProductionAutopilot, canonical_facts, quality_score


def _book(package=""):
    return {"book_id": "book-1", "source_key": "", "package_path": package, "metadata": {"title": "Space Puzzles", "subtitle": "", "author": "Jordan M. Slade", "theme": "Space", "puzzle_count": 48, "page_count": 100, "trim_size": "8.5x11", "production_status": "Passed", "files": {}}, "statuses": {}}


def test_canonical_facts_prefers_catalog_and_flags_conflict():
    facts = canonical_facts(_book(), {"title": "Other title", "author": "Jordan M. Slade", "puzzle_count": 48})
    assert facts["title"] == "Space Puzzles"
    assert any("title" in item.casefold() for item in facts["conflicts"])


def test_canonical_facts_include_the_generation_seed_for_safe_resume():
    first = canonical_facts(_book(), {"puzzle_seed": 101})
    second = canonical_facts(_book(), {"puzzle_seed": 202})
    assert first["puzzle_seed"] == 101
    assert first["fingerprint"] != second["fingerprint"]


def test_checkpoint_skips_unchanged_completed_stage(tmp_path):
    facts = canonical_facts(_book())
    autopilot = ProductionAutopilot(tmp_path, "book-1")
    calls = []
    stages = {"validate": lambda: calls.append("validate") or "validated", "plan": lambda: calls.append("plan") or "planned"}
    first = autopilot.run(facts, stages)
    second = autopilot.run(facts, stages)
    assert first["status"] == "complete"
    assert second["skipped"] == ["validate", "plan"]
    assert calls == ["validate", "plan"]


def test_human_stop_is_recorded_without_retry(tmp_path):
    facts = canonical_facts(_book())
    result = ProductionAutopilot(tmp_path, "book-1").run(facts, {"validate": lambda: (_ for _ in ()).throw(RuntimeError("author identity conflict"))})
    assert result["status"] == "needs_human_review"


def test_completed_package_checkpoint_keeps_its_reusable_artifact_path(tmp_path):
    facts = canonical_facts(_book())
    folder = tmp_path / "completed"; folder.mkdir()
    autopilot = ProductionAutopilot(tmp_path, "book-1"); autopilot.begin(facts)
    fingerprint = autopilot.stage_fingerprint(facts, "package")
    autopilot.complete("package", fingerprint, "final inspection passed", artifact=str(folder))
    stage = autopilot.record()["stages"]["package"]
    assert autopilot.stage_is_current("package", fingerprint)
    assert stage["artifact"] == str(folder)


def test_current_artifact_requires_an_unchanged_existing_file(tmp_path):
    facts = canonical_facts(_book())
    artifact = tmp_path / "interior.pdf"; artifact.write_bytes(b"pdf")
    autopilot = ProductionAutopilot(tmp_path, "book-1"); autopilot.begin(facts)
    fingerprint = autopilot.stage_fingerprint(facts, "generate")
    autopilot.complete("generate", fingerprint, artifact=str(artifact))
    assert autopilot.current_artifact("generate", fingerprint) == artifact
    artifact.unlink()
    assert autopilot.current_artifact("generate", fingerprint) is None


def test_quality_score_is_local_not_marketplace_approval():
    result = quality_score(_book())
    assert result["label"] in {"Needs Work", "Good Candidate", "Ready for Final Local Review", "Ready for Platform Preview"}
    assert "Amazon" not in result["label"]
