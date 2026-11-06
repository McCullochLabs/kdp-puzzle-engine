from pypdf import PdfReader

import pytest

from puzzle_book_studio import (
    make_interior, name_ideas_for, scramble_answer_parts, scramble_clue_share,
    validate_scramble_promise,
)
from publishing.metadata_service import marketplace_content


def test_scramble_answer_parts_avoids_duplicate_answer():
    assert scramble_answer_parts("CAMERA", "Camera") == ("CAMERA", None)
    assert scramble_answer_parts("CHECKIN", "Check-in") == ("CHECKIN", None)
    assert scramble_answer_parts("RAINBOW", "Seven") == ("RAINBOW", "Seven")


def test_clue_led_source_cannot_promise_an_independent_trivia_quiz():
    assert scramble_clue_share("General Knowledge & Curiosity") > 0.9
    with pytest.raises(ValueError, match="fact clues"):
        validate_scramble_promise(
            "Word Scramble + Trivia", "General Knowledge & Curiosity",
            "The Curiosity Cabinet", "60 Trivia Challenges and Word Scrambles",
        )
    validate_scramble_promise(
        "Word Scramble + Trivia", "General Knowledge & Curiosity",
        "The Curiosity Cabinet", "60 Word Scrambles with Fact Clues and Answers",
    )


def test_generated_scramble_names_and_marketplace_copy_describe_clues():
    for title, subtitle in name_ideas_for("Word Scramble + Trivia", "General Knowledge & Curiosity", 60):
        validate_scramble_promise("Word Scramble + Trivia", "General Knowledge & Curiosity", title, subtitle)
    copy = marketplace_content({
        "title": "The Curiosity Cabinet", "subtitle": "60 Word Scrambles with Fact Clues and Answers",
        "puzzle_type": "Word Scramble + Trivia", "detected_topic": "General Knowledge & Curiosity",
        "puzzle_count": 60,
    })
    assert "fact clues" in copy["description"].lower()
    assert "paired with trivia" not in copy["description"].lower()
    assert "trivia question book" not in copy["amazon_keywords"]


def test_scramble_answer_key_is_compact_and_complete(tmp_path):
    interior = tmp_path / "scramble.pdf"
    make_interior(
        "Word Scramble + Trivia", "The Curiosity Cabinet",
        "60 Word Scrambles with Fact Clues and Answers", "Jordan M. Slade",
        60, "Standard", 91001, interior, "General Knowledge & Curiosity",
    )
    reader = PdfReader(str(interior))
    pages = [page.extract_text() or "" for page in reader.pages]
    answer_pages = [page for page in pages if "ANSWER KEY" in page]
    assert len(reader.pages) == 36
    assert len(answer_pages) == 3
    assert "1." in answer_pages[0]
    assert "60." in answer_pages[-1]
    all_answers = "\n".join(answer_pages)
    assert "Fact answer: Seven" in all_answers
    assert "Fact answer: Mars" in all_answers
    assert "Fact answer: Camera" not in all_answers
    assert "WORD SCRAMBLES + FACT CLUES" in pages[0]
    assert "WORD SCRAMBLE + TRIVIA" not in pages[0]
