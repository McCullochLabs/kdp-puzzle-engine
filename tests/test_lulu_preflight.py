from pathlib import Path
import sys

from reportlab.pdfgen import canvas

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from publishing.lulu import LuluPrintConfiguration, preflight


def pdf(path, width, height, pages=1):
    c = canvas.Canvas(str(path), pagesize=(width * 72, height * 72))
    for _ in range(pages): c.showPage()
    c.save()


def config():
    # Observed real Lulu configuration: 8.5 x 11, 138 pages, 0.371-inch spine.
    return LuluPrintConfiguration(8.5, 11, 138, spine_width=.371)


def test_observed_lulu_geometry_is_independent_from_kdp(tmp_path):
    assert config().cover_size() == (17.621, 11.25)
    pdf(tmp_path / "interior.pdf", 8.5, 11, 138)
    pdf(tmp_path / "lulu_full_wrap.pdf", 17.556, 11.25)  # observed KDP wrap
    ok, notes = preflight(tmp_path, config())
    assert not ok and any("17.556" in note and "17.621" in note for note in notes)


def test_correct_lulu_cover_passes_without_using_kdp_dimensions(tmp_path):
    pdf(tmp_path / "interior.pdf", 8.5, 11, 138)
    pdf(tmp_path / "lulu_full_wrap.pdf", 17.621, 11.25)
    ok, notes = preflight(tmp_path, config())
    assert ok and any(note.startswith("PASS - Lulu cover") for note in notes)


def test_missing_spine_configuration_blocks_claim_of_readiness(tmp_path):
    pdf(tmp_path / "interior.pdf", 8.5, 11, 138)
    pdf(tmp_path / "lulu_full_wrap.pdf", 17.621, 11.25)
    ok, notes = preflight(tmp_path, LuluPrintConfiguration(8.5, 11, 138))
    assert not ok and any("spine width" in note for note in notes)
