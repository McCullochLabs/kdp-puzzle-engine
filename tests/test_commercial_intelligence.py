from publishing.commercial_intelligence import (
    RULE_VERSION,
    commercial_assessment,
    render_commercial_report,
    write_commercial_report,
)


def _book():
    return {"book_id": "demo", "metadata": {
        "title": "Stargazer Sudoku",
        "subtitle": "100 symbol Sudoku puzzles for calm space lovers",
        "theme": "Space and Astronomy",
        "puzzle_type": "Sudoku",
        "puzzle_count": 100,
        "difficulty": "Mixed",
        "series": "Celestial Puzzles",
        "description": "A verified collection of astronomy-inspired symbol Sudoku challenges with complete solutions.",
        "files": {"print_interior": "interior.pdf", "print_cover": "cover.pdf", "printable_pdf": "download.pdf"},
        "price": {"amazon": 14.99},
    }}


def test_commercial_assessment_keeps_marketplace_rules_and_a_plus_separate():
    result = commercial_assessment(_book())
    assert result["rule_version"] == RULE_VERSION
    assert set(result["marketplaces"]) == {"amazon", "barnes_noble", "payhip", "lulu"}
    assert len(result["marketplaces"]["amazon"]["keywords"]) == 7
    assert result["marketplaces"]["amazon"]["a_plus_plan"]["eligible_after_publication"] is True
    assert result["marketplaces"]["barnes_noble"]["suggested_price"] >= 14.99
    assert "sales" in result["score_definition"].casefold()


def test_commercial_report_is_human_readable_and_writes_local_files(tmp_path):
    result = commercial_assessment(_book(), "payhip")
    text = render_commercial_report(result)
    assert "PAYHIP" in text
    assert "does not upload" in text
    path = write_commercial_report(_book(), tmp_path)
    assert path.is_file()
    assert (tmp_path / "MARKETPLACE_COMMERCIAL_INTELLIGENCE.json").is_file()


def test_commercial_engine_flags_generic_positioning_and_distribution_overlap():
    generic = _book()
    generic["metadata"].update({"title": "Word Search for Adults", "theme": "General"})
    result = commercial_assessment(generic)
    assert any("specific buyer topic" in note for note in result["improvements"])
    overlap = _book()
    overlap["metadata"]["distribution_plan"] = "KDP Expanded Distribution and Lulu Global Distribution"
    assert "overlap" in commercial_assessment(overlap)["marketplaces"]["lulu"]["overlap_warning"].casefold()
