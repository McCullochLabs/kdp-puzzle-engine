from word_search_creator import recommend_theme_from_words, recommended_builder_count, resolve_topic_pack_choice


def test_plain_english_space_topic_resolves_to_existing_pack():
    choices={"Science — Space, Planets and Astronomy":"Space, Planets and Astronomy","Education — School Vocabulary":"School Vocabulary"}
    assert resolve_topic_pack_choice("Space & Astronomy",choices)=="Science — Space, Planets and Astronomy"


def test_unrelated_topic_does_not_silently_load_wrong_pack():
    choices={"Science — Space and Astronomy":"Space and Astronomy"}
    assert resolve_topic_pack_choice("Cocktail Nightlife",choices)==""


def test_explicit_space_topic_cannot_be_relabelled_as_national_parks():
    result = recommend_theme_from_words([{"words": ["FOREST", "ORBIT", "GALAXY"]}], "Space & Astronomy")
    assert result["topic"] == "Space and Astronomy"
    assert result["palette"] == "midnight-gold"


def test_standard_wizard_keeps_48_puzzles_even_when_more_content_exists():
    assert recommended_builder_count(109, 48) == 48
    assert recommended_builder_count(109, 100) == 100
