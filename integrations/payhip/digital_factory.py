"""Build a customer-safe, manual Payhip listing package without remote writes."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from publishing.payhip_communications import store_setup_sheet
from publishing.payhip_product import advanced_options, collection_for, description_for, marketplace_category_for, price_for, render_publishing_sheet, tags_for, visibility_for

MAX_FILE_BYTES = 5 * 1024 * 1024 * 1024


def _pdf_renderer() -> str:
    """Find Poppler without requiring the operator to edit Windows PATH."""
    configured = str(os.environ.get("SLADE_PDFTOPPM_PATH") or "").strip()
    candidates = [
        Path(configured) if configured else None,
        Path(shutil.which("pdftoppm") or "") if shutil.which("pdftoppm") else None,
        Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies" / "native" / "poppler" / "Library" / "bin" / "pdftoppm.exe",
    ]
    for candidate in candidates:
        if candidate and candidate.is_file():
            return str(candidate)
    raise ValueError(
        "The local PDF renderer is unavailable, so Payhip sample images could not be made. "
        "Install Poppler or set SLADE_PDFTOPPM_PATH to pdftoppm.exe, then prepare Payhip again."
    )


def _copy(source: Path, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target); return target


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_source(files: dict) -> Path:
    source = Path(str(files.get("printable_pdf") or files.get("print_interior") or ""))
    if not source.is_file(): raise ValueError("Create the complete package first so Payhip has a customer digital-download PDF.")
    if source.stat().st_size > MAX_FILE_BYTES: raise ValueError("The customer PDF exceeds Payhip's current 5 GB per-file limit; split it before preparing.")
    reader = PdfReader(str(source))
    if reader.is_encrypted or not reader.pages: raise ValueError("The customer PDF must be a readable, non-encrypted PDF with at least one page.")
    return source


def preview_source_pages(source: Path, puzzle_type: str = "") -> list[int]:
    """Choose actual, representative puzzle pages deterministically; never answers."""
    reader = PdfReader(str(source)); chosen: list[int] = []
    kind = puzzle_type.casefold()
    patterns = ("SUDOKU", "CRYPTOGRAM", "UNSCRAMBLE") if "mixed" in kind else ("SUDOKU",) if "sudoku" in kind else ("CRYPTOGRAM",) if "cryptogram" in kind else ("UNSCRAMBLE", "WORD SEARCH")
    def safe_content(text: str) -> bool:
        return bool(text.strip()) and not any(marker in text for marker in (
            "SOLUTION", "ANSWER KEY", "HOW TO PLAY", "FRESH PUZZLE BREAK",
            "MY PUZZLE NOTES", "PUZZLES I LOVED", "PUZZLE PASSPORT",
            "COLLECTION GUIDE", "WELCOME TO THE COLLECTION",
        ))
    def numbered_puzzle(text: str) -> bool:
        return bool(
            re.search(r"\b(?:PUZZLE|CRYPTOGRAM)\s+\d+\b", text)
            or re.search(r"\b\d+\.\s+UNSCRAMBLE:", text)
        )
    def playable(text: str) -> bool:
        return safe_content(text) and numbered_puzzle(text)
    for pattern in patterns:
        for index, page in enumerate(reader.pages):
            text = (page.extract_text() or "").upper()
            # Cryptogram and scramble pages use activity-specific labels;
            # require those labels to describe playable content, not the book
            # title or a section divider.
            activity_page = ((pattern == "CRYPTOGRAM" and numbered_puzzle(text))
                             or (pattern == "UNSCRAMBLE" and "UNSCRAMBLE:" in text and numbered_puzzle(text))
                             or (pattern == "WORD SEARCH" and numbered_puzzle(text)))
            if pattern in text and safe_content(text) and activity_page and index not in chosen:
                chosen.append(index); break
    for index, page in enumerate(reader.pages):
        if len(chosen) >= 4: break
        text = (page.extract_text() or "").upper()
        if index >= 2 and playable(text) and index not in chosen: chosen.append(index)
    return chosen[:4]


def _cover_page(cover: Path, target: Path) -> None:
    c = canvas.Canvas(str(target), pagesize=letter); width, height = letter; image_w, image_h = 2550, 3300
    scale = min((width - 72) / image_w, (height - 72) / image_h); draw_w, draw_h = image_w * scale, image_h * scale
    c.drawImage(str(cover), (width - draw_w) / 2, (height - draw_h) / 2, draw_w, draw_h, preserveAspectRatio=True, mask="auto"); c.showPage(); c.save()


def build_preview_pdf(source: Path, cover: Path, target: Path, puzzle_type: str = "") -> dict:
    """Build a compact cover-plus-real-pages teaser without answers/records."""
    reader = PdfReader(str(source)); selected = preview_source_pages(source, puzzle_type)
    if not selected: raise ValueError("The product does not have enough readable puzzle pages for a safe Payhip preview.")
    writer = PdfWriter()
    with tempfile.TemporaryDirectory(prefix="payhip_preview_") as temp:
        cover_pdf = Path(temp) / "cover.pdf"; _cover_page(cover, cover_pdf); writer.add_page(PdfReader(str(cover_pdf)).pages[0])
        for index in selected: writer.add_page(reader.pages[index])
        with target.open("wb") as stream: writer.write(stream)
    return {"source_pages": [index + 1 for index in selected], "page_count": len(writer.pages)}


def _render_page_image(source: Path, page_index: int, target: Path) -> None:
    """Render one actual PDF page with local Poppler at a readable 150 DPI."""
    with tempfile.TemporaryDirectory(prefix="payhip_image_") as temp:
        single = Path(temp) / "sample.pdf"; writer = PdfWriter(); writer.add_page(PdfReader(str(source)).pages[page_index])
        with single.open("wb") as stream: writer.write(stream)
        base = Path(temp) / "rendered"
        subprocess.run([_pdf_renderer(), "-png", "-r", "150", "-singlefile", str(single), str(base)], check=True, capture_output=True)
        _copy(base.with_suffix(".png"), target)


def build_payhip_digital_handoff(book: dict, target: Path) -> list[Path]:
    """Create only Payhip-used files plus its one product publishing sheet."""
    meta = book.get("metadata") or {}; files = meta.get("files") if isinstance(meta.get("files"), dict) else {}
    source = _safe_source(files); cover = Path(str(files.get("front_cover") or ""))
    if not cover.is_file(): raise ValueError("Create the complete package first so Payhip has a main product cover image.")
    target.mkdir(parents=True, exist_ok=True)
    # Clean only obsolete Payhip fragments from a prior package format.
    for name in ("customer_puzzle_book.pdf", "customer_download.zip", "customer_preview.pdf", "listing_cover.png", "payhip_product_manifest.json", "READY_TO_COPY_LISTING.txt", "UPLOAD_NOTES.txt", "README_FOR_CUSTOMERS.txt"):
        (target / name).unlink(missing_ok=True)
    customer = _copy(source, target / "customer_product.pdf")
    preview = target / "preview.pdf"; preview_info = build_preview_pdf(source, cover, preview, str(meta.get("puzzle_type") or ""))
    hero = _copy(cover, target / "product_cover.png")
    samples: list[Path] = []
    for number, source_page in enumerate(preview_info["source_pages"][:2], 2):
        image = target / f"product_image_{number:02d}.png"; _render_page_image(source, source_page - 1, image); samples.append(image)
    image_names = [hero.name, *[image.name for image in samples]]
    sheet = target / "PAYHIP_PUBLISHING_SHEET.txt"; sheet.write_text(render_publishing_sheet(meta, {"customer_pdf": customer.name, "preview": preview.name, "images": image_names}), encoding="utf-8")
    setup = target / "PAYHIP_STORE_SETUP_SHEET.txt"; setup.write_text(store_setup_sheet(str(meta.get("brand") or "SladePuzzleCo")), encoding="utf-8")
    artifacts = [customer, preview, hero, *samples, sheet, setup]
    manifest = target / "payhip_manifest.json"
    manifest.write_text(json.dumps({"platform": "payhip", "manual_only": True, "generated_at": datetime.now().isoformat(timespec="seconds"), "product_title": str(meta.get("title") or ""), "source_master_product": book.get("book_id", ""), "source_revision": meta.get("revision", ""), "customer_pdf_reuses_verified_interior": True, "customer_pdf": customer.name, "preview": {"file": preview.name, **preview_info}, "images": image_names, "collection": collection_for(meta), "marketplace_category": marketplace_category_for(meta), "tags": tags_for(meta), "visibility": visibility_for(meta), "price": price_for(meta), "advanced_options": advanced_options(meta), "description": description_for(meta), "artifacts": [{"name": item.name, "sha256": _sha256(item), "bytes": item.stat().st_size} for item in artifacts]}, indent=2) + "\n", encoding="utf-8")
    artifacts.append(manifest)
    return artifacts
