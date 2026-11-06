from dataclasses import FrozenInstanceError
import pytest
from reportlab.pdfbase import pdfmetrics
from publishing.cryptogram_typography import CryptogramTypography, resolve_typography


@pytest.mark.parametrize("values", [{"schema_version": True}, {"schema_version": 2}, {"puzzle_font_pt": 16}, {"puzzle_font_pt": 23}, {"puzzle_font_pt": True}, {"puzzle_font_pt": float("nan")}, {"solution_font_pt": float("inf")}, {"solution_font_pt": 10}, {"solution_font_pt": 15}, {"solution_font_pt": "12"}])
def test_invalid_values(values):
    with pytest.raises(ValueError): CryptogramTypography(**values)


def test_exact_versioned_roundtrip():
    config = CryptogramTypography(puzzle_font_pt=22, solution_font_pt=14)
    assert CryptogramTypography.from_dict(config.to_dict()) == config
    with pytest.raises(FrozenInstanceError): config.puzzle_font_pt = 20
    for raw in ({}, dict(config.to_dict(), approved=True)):
        with pytest.raises(ValueError): CryptogramTypography.from_dict(raw)
    with pytest.raises(ValueError): resolve_typography(config.to_dict())
    assert resolve_typography() == CryptogramTypography()


class CanvasSpy:
    def __init__(self): self.page = 3; self.sizes = []
    def getPageNumber(self): return self.page
    def showPage(self): self.page += 1
    def stringWidth(self, text, face, size): return pdfmetrics.stringWidth(text, face, size)
    def setFont(self, face, size): self.sizes.append((face, size))
    def __getattr__(self, name):
        if name.startswith("_"): raise AttributeError(name)
        return lambda *args, **kwargs: None


def test_seeded_renderer_preserves_records_and_pages(monkeypatch):
    import puzzle_book_studio as s
    for name in ("themed_running_header", "themed_solution_header", "footer", "title"):
        monkeypatch.setattr(s, name, lambda *args, **kwargs: None)
    old = CanvasSpy(); default = CanvasSpy(); larger = CanvasSpy()
    ends = [s.crypto_book(old, 10, 42), s.crypto_book(default, 10, 42, typography=CryptogramTypography()), s.crypto_book(larger, 10, 42, typography=CryptogramTypography(puzzle_font_pt=22, solution_font_pt=14))]
    assert ends[0] == ends[1] == ends[2]
    assert old._puzzle_records == default._puzzle_records == larger._puzzle_records
    assert old.sizes == default.sizes
    assert (s.font("BookMono"), 22) in larger.sizes
    assert (s.font("BookSans"), 14) in larger.sizes


def test_invalid_option_fails_before_content_selection(monkeypatch):
    import puzzle_book_studio as s
    monkeypatch.setattr(s, "themed_cryptograms", lambda *a: pytest.fail("Invalid option reached content"))
    with pytest.raises(ValueError): s.crypto_book(CanvasSpy(), 1, 42, theme="Space & Astronomy", typography={})
