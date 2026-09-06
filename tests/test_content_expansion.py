import json

from publishing.content_expansion import expansion_plan, save_research_brief


def test_expansion_plan_reports_exact_gap_and_saves_a_review_brief(tmp_path):
    bank = {"topics": {"Space & Astronomy": [f"term {index}" for index in range(50)]}, "topic_packs": {"Planets & Solar System": ["Space & Astronomy"]}}
    (tmp_path / "word_banks").mkdir()
    (tmp_path / "word_banks" / "Guided_Builder_Master_Word_Bank.json").write_text(json.dumps(bank), encoding="utf-8")
    (tmp_path / "word_banks" / "puzzle_content_library.json").write_text(json.dumps({"packs": {}}), encoding="utf-8")
    plan = expansion_plan(tmp_path, "Space & Astronomy")
    assert plan["missing_words"] > 0
    target = save_research_brief(tmp_path, "Space & Astronomy")
    assert target.is_file()
    assert json.loads(target.read_text(encoding="utf-8"))["topic"] == "Space & Astronomy"
