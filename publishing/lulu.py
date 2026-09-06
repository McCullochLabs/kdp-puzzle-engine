"""Offline Lulu geometry and preflight support.

Lulu cover geometry is deliberately explicit per print configuration.  A KDP
cover is never resized or accepted as a Lulu cover merely because it is close.
The exact spine comes from Lulu's template/API configuration, not a guessed
universal paper formula.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from pypdf import PdfReader

PT = 72.0
TOLERANCE_IN = 0.01


@dataclass(frozen=True)
class LuluPrintConfiguration:
    trim_width: float
    trim_height: float
    page_count: int
    interior_color: str = "Standard Black & White"
    paper_type: str = ""
    binding_type: str = "Paperback Perfect Bound"
    cover_finish: str = "Matte"
    bleed: float = 0.125
    spine_width: float | None = None
    isbn_status: str = "NOT_REQUIRED"
    product_id: str = ""

    def cover_size(self) -> tuple[float, float] | None:
        if self.spine_width is None or self.spine_width <= 0:
            return None
        return (2 * self.trim_width + self.spine_width + 2 * self.bleed,
                self.trim_height + 2 * self.bleed)

    def manifest(self) -> dict:
        data = asdict(self); data["expected_cover_size"] = self.cover_size()
        return data


def page_size_inches(pdf: Path) -> tuple[float, float]:
    reader = PdfReader(str(pdf))
    if len(reader.pages) != 1:
        raise ValueError("A Lulu cover must be a single integrated PDF page.")
    box = reader.pages[0].mediabox
    return float(box.width) / PT, float(box.height) / PT


def preflight(folder: Path, config: LuluPrintConfiguration) -> tuple[bool, list[str]]:
    """Run local Lulu checks. API/account readiness is intentionally separate."""
    folder = Path(folder); notes: list[str] = []
    interior = folder / "interior.pdf"; cover = folder / "lulu_full_wrap.pdf"
    if not interior.is_file(): notes.append("FAIL - Missing interior.pdf.")
    else:
        try:
            reader = PdfReader(str(interior)); pages = len(reader.pages)
            if pages != config.page_count:
                notes.append(f"FAIL - Interior has {pages} pages; Lulu configuration expects {config.page_count}.")
            else: notes.append(f"PASS - Interior page count matches ({pages}).")
            box = reader.pages[0].mediabox; width, height = float(box.width)/PT, float(box.height)/PT
            if abs(width-config.trim_width) <= TOLERANCE_IN and abs(height-config.trim_height) <= TOLERANCE_IN:
                notes.append(f"PASS - Interior trim matches {config.trim_width:g} x {config.trim_height:g} inches.")
            else: notes.append(f"FAIL - Interior trim is {width:.3f} x {height:.3f}; expected {config.trim_width:g} x {config.trim_height:g}.")
            if reader.is_encrypted: notes.append("FAIL - Interior PDF is encrypted; remove PDF security.")
        except Exception as exc: notes.append(f"FAIL - Could not read interior PDF ({exc}).")
    expected = config.cover_size()
    if expected is None:
        notes.append("FAIL - Lulu spine width is not configured from a Lulu template or official configuration response.")
    if not cover.is_file(): notes.append("FAIL - Missing lulu_full_wrap.pdf. A KDP wrap cannot substitute for it.")
    else:
        try:
            actual = page_size_inches(cover)
            if expected and abs(actual[0]-expected[0]) <= TOLERANCE_IN and abs(actual[1]-expected[1]) <= TOLERANCE_IN:
                notes.append(f"PASS - Lulu cover is {actual[0]:.3f} x {actual[1]:.3f} inches and matches configuration.")
            elif expected:
                notes.append(f"FAIL - Lulu cover is {actual[0]:.3f} x {actual[1]:.3f}; expected {expected[0]:.3f} x {expected[1]:.3f}.")
            reader = PdfReader(str(cover))
            if reader.is_encrypted: notes.append("FAIL - Lulu cover PDF is encrypted; remove PDF security.")
        except Exception as exc: notes.append(f"FAIL - Could not read Lulu cover PDF ({exc}).")
    notes.append(f"INFO - ISBN status: {config.isbn_status}. No ISBN is fabricated or copied from KDP.")
    notes.append("INFO - Lulu API: not configured. Local file readiness does not mean published.")
    return not any(note.startswith("FAIL") for note in notes), notes


def report_text(folder: Path, config: LuluPrintConfiguration, title: str = "") -> str:
    ok, notes = preflight(folder, config); expected = config.cover_size()
    state = "FILES READY" if ok else "NEEDS ATTENTION"
    header = f"LULU PREFLIGHT — {state}"
    lines = [header, "=" * len(header), f"Book: {title or Path(folder).name}",
             f"Trim: {config.trim_width:g} x {config.trim_height:g}", f"Pages: {config.page_count}",
             f"Spine: {config.spine_width:.3f} in" if config.spine_width else "Spine: not configured",
             f"Required cover: {expected[0]:.3f} x {expected[1]:.3f}" if expected else "Required cover: unavailable", ""]
    return "\n".join(lines + notes) + "\n"
