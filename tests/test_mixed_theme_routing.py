from puzzle_book_studio import mixed_section_themes


def test_mixed_word_sections_keep_the_selected_theme():
    assert mixed_section_themes("Space & Astronomy") == ("Space & Astronomy", "Space & Astronomy")
    assert mixed_section_themes("School & Vocabulary") == ("School & Vocabulary", "School & Vocabulary")


def test_mixed_word_sections_use_safe_general_default():
    assert mixed_section_themes("") == ("General Starter", "General Starter")
