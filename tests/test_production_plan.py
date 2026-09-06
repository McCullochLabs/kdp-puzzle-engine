from publishing.production_plan import content_capacity, production_plan_summary


def test_content_capacity_reports_two_book_readiness():
    result = content_capacity(1152, 48, 12)
    assert result["full_books"] == 2
    assert result["target_ready"] is True
    assert "2 complete" in str(result["message"])


def test_content_capacity_reports_exact_gap_for_second_book():
    result = content_capacity(600, 48, 12)
    assert result["one_book_ready"] is True
    assert result["target_ready"] is False
    assert result["missing_for_target"] == 552


def test_plan_summary_contains_approval_details():
    text = production_plan_summary(title="Sky", subtitle="Calm puzzles", difficulty="Standard",
                                   puzzle_count=48, words_per_puzzle=12, pages=98, price=8.99,
                                   palette="starlight-indigo", layout="photo", folder="out/Sky",
                                   capacity=content_capacity(1152, 48, 12))
    assert "CONTENT GUARANTEE" in text
    assert "Amazon KDP" in text
