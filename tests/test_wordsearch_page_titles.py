from word_intelligence.page_titles import puzzle_page_title


def test_legacy_section_cannot_make_an_unproven_page_claim():
    data = {"detected_topic": "Bible and Faith"}
    puzzle = {"name": "Faith and Encouragement 1", "section": "Faith and Encouragement", "words": ["SHESHAI", "FOREST"]}
    assert puzzle_page_title(data, puzzle, 1) == "BIBLE & FAITH WORDS 01"


def test_reviewed_mini_theme_is_preserved():
    data = {"detected_topic": "Nature & Outdoors"}
    puzzle = {"name": "Woodland Wildlife", "mini_theme": "Woodland Wildlife", "page_title_basis": "reviewed_mini_theme"}
    assert puzzle_page_title(data, puzzle, 7) == "Woodland Wildlife"


def test_vocabulary_pages_receive_truthful_grade_label():
    data = {"detected_topic": "Grade 5 Vocabulary"}
    assert puzzle_page_title(data, {"name": "Words for Feelings"}, 3) == "GRADE 5 VOCABULARY 03"
