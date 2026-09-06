"""Print-package checks shared by every Word Search Creator production route.

This is a local readiness check, not a substitute for KDP's current Previewer.
It prefers the Book Studio's ``kdp_full_wrap.pdf`` and also supports the
older standalone factory's ``wrap.pdf`` so that route stays safe to use.
"""
from __future__ import annotations

import sys
from pathlib import Path

from pypdf import PdfReader
from publishing.package_layout import package_file

TRIM_W, TRIM_H = 8.5, 11.0
BLEED = 0.125
SPINE_FACTOR = 0.002252
PT = 72.0
TOL_PT = 4.0
MIN_PAGES = 24
MAX_BLACK_WHITE_PAGES = 590  # 8.5 x 11 black ink on white paper


def _page_size(reader: PdfReader) -> tuple[float, float]:
    box = reader.pages[0].mediabox
    return float(box.width), float(box.height)


def preflight(book_dir: str | Path) -> tuple[bool, list[str]]:
    """Check the actual files made by this app and return plain-English lines."""
    folder = Path(book_dir)
    interior = package_file(folder, "interior.pdf")
    wrap = package_file(folder, "kdp_full_wrap.pdf")
    if not wrap.is_file():
        wrap = folder / "wrap.pdf"
    results: list[str] = []
    if not interior.is_file():
        return False, ["FAIL - Missing interior.pdf."]
    if not wrap.is_file():
        return False, ["FAIL - Missing kdp_full_wrap.pdf (or legacy wrap.pdf)."]
    try:
        interior_reader = PdfReader(str(interior)); wrap_reader = PdfReader(str(wrap))
    except Exception as exc:
        return False, [f"FAIL - Could not open a PDF: {exc}"]
    pages = len(interior_reader.pages)
    if pages < MIN_PAGES:
        results.append(f"FAIL - Interior has {pages} pages; KDP paperbacks need at least {MIN_PAGES}.")
    elif pages > MAX_BLACK_WHITE_PAGES:
        results.append(f"WARN - Interior has {pages} pages, above the known 8.5 x 11 black-and-white limit of {MAX_BLACK_WHITE_PAGES}; confirm the ink and paper options in KDP.")
    else:
        results.append(f"PASS - Interior has {pages} page(s), within the expected 8.5 x 11 black-and-white range.")
    if pages % 2:
        results.append("WARN - Interior has an odd page count. KDP may round this up; rebuild the package so the final cover-spine calculation is based on the exact count.")
    else:
        results.append("PASS - Interior page count is even, so the generated wrap uses the same physical-sheet count.")
    iw, ih = _page_size(interior_reader)
    if abs(iw - TRIM_W * PT) <= TOL_PT and abs(ih - TRIM_H * PT) <= TOL_PT:
        results.append("PASS - Interior trim is 8.5 x 11 inches.")
    else:
        results.append(f"FAIL - Interior trim is {iw/PT:.3f} x {ih/PT:.3f} inches; expected 8.5 x 11.")
    ww, wh = _page_size(wrap_reader)
    expected_w = (TRIM_W * 2 + pages * SPINE_FACTOR + BLEED * 2) * PT
    expected_h = (TRIM_H + BLEED * 2) * PT
    if abs(ww - expected_w) <= TOL_PT and abs(wh - expected_h) <= TOL_PT:
        results.append(f"PASS - Full-wrap size matches the {pages}-page interior.")
    else:
        results.append(f"FAIL - Full-wrap size is {ww/PT:.3f} x {wh/PT:.3f} inches; expected {expected_w/PT:.3f} x {expected_h/PT:.3f}.")
    if pages <= 79:
        results.append("PASS - Thin-book spine rule: this wrap should have no spine text.")
    else:
        results.append("PASS - KDP permits spine text above 79 pages; still confirm its placement in KDP Print Previewer.")
    author = str((interior_reader.metadata.author if interior_reader.metadata else "") or "").strip()
    results.append("PASS - Interior author metadata is present." if author else "WARN - Interior author metadata is empty; confirm the author/pen name before upload.")
    ok = not any(line.startswith("FAIL") for line in results)
    return ok, results


def report_text(book_dir: str | Path) -> str:
    ok, results = preflight(book_dir)
    heading = "PUBLISHER PREFLIGHT - PASSED" if ok else "PUBLISHER PREFLIGHT - NEEDS ATTENTION"
    return heading + "\n" + "=" * len(heading) + "\n\n" + "\n".join(results) + "\n\nAlways run the current KDP Print Previewer before uploading.\n"


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python preflight.py <finished-book-folder>")
        return 2
    print(report_text(sys.argv[1]))
    return 0 if preflight(sys.argv[1])[0] else 1


if __name__ == "__main__":
    raise SystemExit(main())
