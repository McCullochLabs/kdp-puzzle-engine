from PIL import Image, ImageDraw

import cover


def test_scramble_cover_uses_supplied_question_instead_of_space_placeholder(monkeypatch):
    seen = []
    original = cover._centered_stroked

    def capture(draw, text, font, y, fill, stroke, width):
        seen.append(text)
        return original(draw, text, font, y, fill, stroke, width)

    monkeypatch.setattr(cover, "_centered_stroked", capture)
    monkeypatch.setattr(cover, "COVER_PUZZLE_TYPE", "Word Scramble + Trivia")
    monkeypatch.setattr(cover, "COVER_SAMPLE_WORD", "TARSAEER")
    monkeypatch.setattr(cover, "COVER_SAMPLE_QUESTION", "What highway stop offers travelers a place to pause and use facilities?")
    draw = ImageDraw.Draw(Image.new("RGBA", (1300, 900)))
    cover.puzzle_type_hero(draw, 650, 450, 120, "#ffce77", "#17212c", "#fff4db")
    assert any("highway stop" in text for text in seen)
    assert not any("Red Planet" in text for text in seen)
