from puzzle_book_studio import (
    buffered_capacity_needed,
    content_check,
    themed_trivia,
)


def test_travel_trivia_supports_a_buffered_sixty_puzzle_book():
    checked, _, capacity = content_check("Word Scramble + Trivia", "Travel & Adventure")
    assert checked
    assert capacity >= buffered_capacity_needed(60)
    assert capacity == len(themed_trivia("Travel & Adventure"))


def test_travel_trivia_entries_have_matching_answers():
    for word, question, answer in themed_trivia("Travel & Adventure"):
        assert word.isalpha()
        assert word == "".join(character for character in answer.upper() if character.isalpha())
        assert question.endswith("?")


def test_road_trip_route_has_sixty_specific_reviewed_clues():
    prompts = themed_trivia("Road Trips & Highways")
    words = {word for word, _question, _answer in prompts}
    assert len(prompts) >= 60
    assert not words.intersection({"PASSPORT", "AIRPORT", "AIRLINE", "CRUISE", "CUSTOMS", "VISA", "LAYOVER"})
    assert {"HIGHWAY", "ROADMAP", "GASSTATION", "MILEMARKER", "SCENICOVERLOOK"}.issubset(words)
