from pathlib import Path

from publishing.content_capacity import blueprint, topic_capacity
from publishing.word_capacity_plan import build_plan, required_words


def test_topic_capacity_is_honest_about_cross_format_gaps(tmp_path):
    bank = tmp_path / "word_banks"; bank.mkdir()
    (bank / "Guided_Builder_Master_Word_Bank.json").write_text('{"topics":{"Space & Astronomy":["ORBIT"]}}', encoding="utf-8")
    (bank / "puzzle_content_library.json").write_text('{"packs":{"Space & Astronomy":{"cryptograms":[],"trivia":[]}}}', encoding="utf-8")
    space = next(row for row in topic_capacity(tmp_path) if row["topic"] == "Space & Astronomy")
    assert space["word_search_books"] == 0
    assert space["cryptogram_books"] == 0
    assert "Expand" in space["next_step"]


def test_blueprint_has_safe_automatic_production_defaults():
    plan = blueprint("Space & Astronomy", "Cryptogram")
    assert plan["puzzle_count"] == 60
    assert plan["interior_style"] == "Signature Collection"
    assert "amazon" in plan["launch_marketplaces"]


def test_word_search_portfolio_plan_reserves_two_standard_books_and_a_signature():
    words = [f"TOPIC TERM {number}" for number in range(required_words())]
    plan = build_plan("Example Topic", words)
    pools = plan["allocations"]
    assert plan["portfolio_ready"]
    assert len(pools["standard_book_1"]) == 48 * 12
    assert len(pools["standard_book_2"]) == 48 * 12
    assert len(pools["signature_edition"]) == 100 * 12
    assert not (set(pools["standard_book_1"]) & set(pools["standard_book_2"]))
    assert not (set(pools["standard_book_2"]) & set(pools["signature_edition"]))


def test_capacity_rows_expose_the_full_planned_portfolio_gap(tmp_path):
    bank = tmp_path / "word_banks"; bank.mkdir()
    words = [f"ORBIT {number}" for number in range(48 * 12)]
    (bank / "Guided_Builder_Master_Word_Bank.json").write_text(__import__("json").dumps({"topics": {"Space & Astronomy": words}}), encoding="utf-8")
    (bank / "puzzle_content_library.json").write_text('{"packs":{}}', encoding="utf-8")
    space = next(row for row in topic_capacity(tmp_path) if row["topic"] == "Space & Astronomy")
    assert not space["portfolio_ready"]
    assert space["portfolio_gap"] == required_words() - len(words)
