"""Commercial capacity must not count dictionary-substitution sentences."""
from __future__ import annotations

import puzzle_book_studio as studio


def test_templated_cryptograms_do_not_count_as_finished_puzzles(monkeypatch):
    monkeypatch.setattr(studio, "content_packs", lambda: {
        "Space & Astronomy": {"cryptograms": [
            "MARS IS OFTEN CALLED THE RED PLANET",
            "CURIOSITY MAKES BOREAS MORE INTERESTING TO EXPLORE",
            "A CAREFUL LOOK AT CALLIOPE CAN REVEAL SOMETHING NEW",
        ]}
    })
    prompts = studio.themed_cryptograms("Space & Astronomy")
    assert prompts == ["MARS IS OFTEN CALLED THE RED PLANET"]
    checked, detail, capacity = studio.content_check("Cryptogram", "Space & Astronomy")
    assert checked
    assert capacity == 1


def test_unwritten_theme_has_no_cryptogram_capacity(monkeypatch):
    monkeypatch.setattr(studio, "content_packs", lambda: {})
    assert studio.themed_cryptograms("History & Heritage") == []
    assert studio.content_check("Cryptogram", "History & Heritage")[2] == 0


def test_mixed_capacity_uses_the_selected_theme_not_general_library(monkeypatch):
    monkeypatch.setattr(studio, "content_packs", lambda: {
        "Space & Astronomy": {
            "cryptograms": ["MARS IS OFTEN CALLED THE RED PLANET"],
            "trivia": [["MARS", "Which planet is called the Red Planet?", "Mars"]],
        }
    })
    assert studio.pack_capacity("Mixed Brain Games", "Space & Astronomy") == 1
    assert studio.pack_capacity("Cryptogram", "Space & Astronomy") == 1
    assert studio.pack_capacity("Word Scramble + Trivia", "Space & Astronomy") == studio.content_check("Word Scramble + Trivia", "Space & Astronomy")[2]


def test_content_packs_merges_only_approved_editorial_library(tmp_path, monkeypatch):
    base = tmp_path / "base.json"
    supplement = tmp_path / "supplement.json"
    base.write_text('{"packs":{"Existing":{"cryptograms":["AN EXISTING APPROVED MESSAGE"]}}}', encoding="utf-8")
    supplement.write_text('{"status":"REVIEW_REQUIRED","packs":{"History & Heritage":{"cryptograms":["A CANDIDATE MUST NOT LEAK INTO PRODUCTION"]}}}', encoding="utf-8")
    monkeypatch.setattr(studio, "CONTENT_LIBRARY", base)
    monkeypatch.setattr(studio, "EDITORIAL_CONTENT_LIBRARY", supplement)
    assert "History & Heritage" not in studio.content_packs()

    supplement.write_text('{"status":"APPROVED_FOR_LOCAL_PRODUCTION","packs":{"History & Heritage":{"cryptograms":["A REVIEWED MESSAGE CAN ENTER THE PRODUCTION LIBRARY"]}}}', encoding="utf-8")
    packs = studio.content_packs()
    assert packs["Existing"]["cryptograms"] == ["AN EXISTING APPROVED MESSAGE"]
    assert packs["History & Heritage"]["cryptograms"] == ["A REVIEWED MESSAGE CAN ENTER THE PRODUCTION LIBRARY"]


def test_reviewed_editorial_packs_have_sixty_clean_messages_each():
    for topic in ("History & Heritage", "Bible & Faith", "Nature & Outdoors", "School & Vocabulary"):
        prompts = studio.themed_cryptograms(topic)
        assert len(prompts) == 60
        assert len(prompts) == len(set(prompts))
        assert all(6 <= len(prompt.split()) <= 16 for prompt in prompts)
        assert all(len(prompt) <= 100 for prompt in prompts)


def test_capacity_matches_renderer_supported_sentence_punctuation(monkeypatch):
    monkeypatch.setattr(studio, "content_packs", lambda: {
        "History & Heritage": {"cryptograms": [
            "CANALS, BRIDGES, AND RAILWAYS CONNECTED GROWING COMMUNITIES.",
            "WHAT STORIES CAN A TOWN'S OLD MAPS REVEAL?",
        ]}
    })
    checked, _detail, capacity = studio.content_check("Cryptogram", "History & Heritage")
    assert checked and capacity == 2


def test_capacity_still_rejects_unsupported_cryptogram_symbols(monkeypatch):
    monkeypatch.setattr(studio, "content_packs", lambda: {
        "History & Heritage": {"cryptograms": ["A REVIEWED MESSAGE CANNOT CONTAIN A SLASH / SYMBOL."]}
    })
    checked, _detail, capacity = studio.content_check("Cryptogram", "History & Heritage")
    assert not checked and capacity == 0
