import pytest
from dataclasses import asdict
from publishing.studio_assistant import AssistantIntent, guide_request, parse_proposal

@pytest.mark.parametrize("text,topic",[
    ("Create a 100-page wildlife word search book for adults.","wildlife"),
    ("Create a birdwatching word search book","Birdwatching"),
    ("Create a chess word search book","chess"),
    ("Create a word search book about coastal birds for adults","coastal birds"),
])
def test_offline_book_topic_is_preserved(text,topic):
    intent=guide_request(text)
    assert intent.action=="create_book" and intent.topic.casefold()==topic.casefold()


def test_word_scramble_request_uses_scramble_engine():
    assert guide_request("Make a road trip word scramble book").kind=="Word Scramble + Trivia"

@pytest.mark.parametrize("family",["crossword","word ladder","logic grid","fill-in","maze"])
def test_unimplemented_puzzles_are_not_silently_word_searches(family):
    text=f"Create a {family} book"
    assert guide_request(text).action=="clarify"
    assert parse_proposal(asdict(AssistantIntent(action="create_book",topic="Space")),text).action=="clarify"

@pytest.mark.parametrize("text",["Create a space Sudoku book with mixed difficulties","Create a Sudoku book with mixed easy and medium puzzles"])
def test_mixed_difficulty_is_not_mixed_puzzle_family(text):
    assert guide_request(text).kind=="Sudoku"

@pytest.mark.parametrize("text",["Create a word search book about crossword terminology","Create a mixed brain games book without crosswords"])
def test_topic_words_and_excluded_formats_do_not_become_requested_families(text):
    assert guide_request(text).action=="create_book"
