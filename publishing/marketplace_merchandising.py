"""Safe local marketplace merchandising made from real product artifacts."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw, ImageFont
import pypdfium2 as pdfium

from .package_layout import package_file


def _font(size: int, bold: bool = False):
    try:
        return ImageFont.truetype("arialbd.ttf" if bold else "arial.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _render(pdf: pdfium.PdfDocument, index: int) -> Image.Image:
    return pdf[index].render(scale=1.5).to_pil().convert("RGB")


def _page_text(pdf: pdfium.PdfDocument, index: int) -> str:
    try:
        page = pdf[index]
        textpage = page.get_textpage()
        return textpage.get_text_range()
    except Exception:
        return ""


def _card(title: str, subtitle: str = "", image: Image.Image | None = None, badge: str = "") -> Image.Image:
    canvas = Image.new("RGB", (1800, 1800), "#f7f3ea")
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, 1800, 34), fill="#0f766e")
    draw.text((110, 90), title, fill="#17202a", font=_font(72, True))
    if subtitle:
        draw.multiline_text((112, 190), subtitle, fill="#3d4b57", font=_font(38), spacing=16)
    if image is not None:
        item = image.copy(); item.thumbnail((1320, 1180))
        canvas.paste(item, ((1800 - item.width) // 2, 420))
    if badge:
        box = (110, 1600, 1690, 1720); draw.rounded_rectangle(box, 28, fill="#17202a")
        bounds = draw.textbbox((0, 0), badge, font=_font(44, True))
        draw.text(((1800 - (bounds[2] - bounds[0])) // 2, 1628), badge, fill="white", font=_font(44, True))
    return canvas


def etsy_merchandising_plan(metadata: dict) -> dict:
    title = str(metadata.get("title") or "Puzzle Collection")
    count = int(metadata.get("puzzle_count") or 0)
    kind = str(metadata.get("puzzle_type") or "Puzzle Book")
    audience = str(metadata.get("audience") or "puzzle fans")
    return {
        "title": title,
        "digital_disclosure": "DIGITAL DOWNLOAD — NO PHYSICAL PRODUCT",
        "image_plan": [
            "Hero / thumbnail", "What You Get", "Interior Puzzle Preview", "Second Interior Preview",
            "Solution Preview", "Readability / Large Print Preview", "Puzzle / Page Count",
            "Print-at-Home / PDF Instructions", "Audience / Use Case", "Digital Download Disclosure",
        ],
        "verified_facts": {"puzzle_count": count, "puzzle_type": kind, "audience": audience},
        "notice": "All page graphics must come from the completed product. This plan does not imply physical delivery.",
    }


def build_etsy_merchandising_kit(
    package: Path,
    metadata: dict,
    *,
    approval_verifier: Callable[[Path], tuple] | None = None,
) -> Path:
    """Create ten listing images without modifying the production PDFs.

    Cover approval fails closed. Interior and solution previews are rendered
    from the package's real PDF; no sample puzzle is fabricated.
    """
    package = Path(package)
    cover = package_file(package, "front_cover.png")
    interior = package_file(package, "interior.pdf")
    if not cover.is_file() or not interior.is_file():
        raise FileNotFoundError("Etsy merchandising needs the completed front cover and interior PDF.")
    if approval_verifier is None:
        from background_generation.index import verify_rendered_cover_approval
        approval_verifier = verify_rendered_cover_approval
    approved, reason, proof = approval_verifier(cover)
    if not approved:
        raise ValueError("Etsy merchandising stopped because cover approval is missing or stale: " + str(reason))

    target = package / "05_MARKETPLACE_HANDOFFS" / "ETSY" / "LISTING_IMAGES"
    target.mkdir(parents=True, exist_ok=True)
    plan = etsy_merchandising_plan(metadata)
    title = plan["title"]; count = int(plan["verified_facts"]["puzzle_count"]); kind = str(plan["verified_facts"]["puzzle_type"])
    cover_image = Image.open(cover).convert("RGB")
    pdf = pdfium.PdfDocument(str(interior))
    texts = [_page_text(pdf, index).casefold() for index in range(len(pdf))]
    puzzle_indexes = [i for i, text in enumerate(texts) if "puzzle" in text and "solution" not in text and "answer" not in text]
    solution_indexes = [i for i, text in enumerate(texts) if "solution" in text or "answer key" in text]
    if not puzzle_indexes or not solution_indexes:
        pdf.close()
        raise ValueError("Etsy merchandising stopped because real puzzle and solution pages could not both be identified.")
    first = _render(pdf, puzzle_indexes[0]); second = _render(pdf, puzzle_indexes[min(1, len(puzzle_indexes) - 1)]); solution = _render(pdf, solution_indexes[0])
    pages = len(pdf); pdf.close()

    cards = [
        _card(title, "A printable puzzle collection", cover_image, "DIGITAL DOWNLOAD"),
        _card("What You Get", f"• Downloadable PDF\n• {count} {kind} challenges\n• Complete solutions", cover_image),
        _card("A Real Puzzle Page", "Previewed directly from the completed product", first),
        _card("More From Inside", "A second real page from the downloadable PDF", second),
        _card("Solutions Included", "A limited preview from the real answer section", solution),
        _card("Clear, Comfortable Pages", "See the actual typography and spacing before purchase", first),
        _card(f"{count} Puzzles", f"{pages} total PDF pages", cover_image),
        _card("Print-at-Home PDF", "Download after purchase. Print using your PDF viewer and printer settings.", first),
        _card("Made for Puzzle Time", f"A focused activity for {plan['verified_facts']['audience']}", cover_image),
        _card("Digital Download", "No physical product will be shipped.", cover_image, "DIGITAL DOWNLOAD — NO PHYSICAL PRODUCT"),
    ]
    names = []
    for number, (label, image) in enumerate(zip(plan["image_plan"], cards), 1):
        name = f"{number:02d}_{label.lower().replace(' / ', '_').replace(' ', '_').replace('-', '_')}.png"
        image.save(target / name, quality=95); names.append(name)
    manifest = {
        "generated_at": datetime.now().isoformat(timespec="seconds"), "source_cover": str(cover),
        "source_cover_sha256": _sha(cover), "source_interior": str(interior), "source_interior_sha256": _sha(interior),
        "cover_approval": proof, "assets": names, **plan,
    }
    (target / "ETSY_MERCHANDISING_MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return target
