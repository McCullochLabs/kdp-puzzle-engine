"""Buyer-ready Etsy bundle assembly from finished, verified book packages."""
from __future__ import annotations

import re
import zipfile
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw

from font_utils import image_font_candidates, load_image_font


ETSY_FILE_LIMIT = 5
ETSY_PER_FILE_LIMIT = 20 * 1024 * 1024
ETSY_STORE_NAME = "SladePuzzleCo"


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")[:72] or "etsy_bundle"


def eligible_book_error(book: dict) -> str | None:
    files = book.get("metadata", {}).get("files", {})
    interior = Path(str(files.get("printable_pdf") or files.get("print_interior") or ""))
    if not interior.is_file():
        return "The completed customer-download PDF is missing. Create or sync the full package first."
    if interior.stat().st_size > ETSY_PER_FILE_LIMIT:
        return "Its customer PDF is over Etsy's 20 MB per-file limit and must be reduced before bundling."
    return None


def _bundle_cover(books: list[dict], target: Path, title: str) -> None:
    canvas = Image.new("RGB", (2000, 2000), "#142b35")
    draw = ImageDraw.Draw(canvas)
    title_font = load_image_font(image_font_candidates("sans-bold"), 88)
    body_font = load_image_font(image_font_candidates("sans"), 40)
    draw.text((100, 90), title.upper(), fill="#ffffff", font=title_font)
    draw.text((105, 210), f"{len(books)} instant-download puzzle books", fill="#a9ead7", font=body_font)
    slots = [(110, 340), (1040, 340), (110, 1130), (1040, 1130)]
    for index, book in enumerate(books[:4]):
        files = book["metadata"].get("files", {}); cover = Path(str(files.get("front_cover") or ""))
        x, y = slots[index]
        if cover.is_file():
            with Image.open(cover).convert("RGB") as image:
                image.thumbnail((780, 620), Image.LANCZOS); canvas.paste(image, (x, y))
        else:
            draw.rounded_rectangle((x, y, x + 780, y + 620), 24, fill="#245266")
            draw.text((x + 35, y + 60), book["metadata"].get("title", "Puzzle Book")[:45], fill="#ffffff", font=body_font)
    if len(books) > 4:
        draw.rounded_rectangle((1480, 1530, 1880, 1880), 30, fill="#10a37f")
        draw.text((1565, 1650), f"+{len(books)-4} MORE", fill="#ffffff", font=body_font)
    canvas.save(target, quality=94)


def build_etsy_bundle(output_root: Path, title: str, books: list[dict], price: float) -> tuple[Path, dict]:
    if len(books) < 2:
        raise ValueError("Choose at least two completed books for an Etsy bundle.")
    issues = [f"{book['metadata'].get('title', 'Book')}: {error}" for book in books if (error := eligible_book_error(book))]
    if issues:
        raise ValueError("\n".join(issues))
    folder = output_root / "etsy_bundles" / f"{slug(title)}_{datetime.now():%Y%m%d_%H%M%S}"
    folder.mkdir(parents=True, exist_ok=False)
    upload = folder / "01_ETSY_UPLOAD_FILES"; upload.mkdir()
    included = folder / "02_INCLUDED_BOOKS"; included.mkdir()
    pdfs: list[tuple[str, Path]] = []
    for number, book in enumerate(books, 1):
        source = Path(str(book["metadata"].get("files", {}).get("printable_pdf") or book["metadata"].get("files", {}).get("print_interior")))
        clean_name = f"{number:02d}_{slug(book['metadata'].get('title', 'puzzle_book'))}.pdf"
        target = included / clean_name
        target.write_bytes(source.read_bytes())
        pdfs.append((clean_name, target))
    chunks: list[list[tuple[str, Path]]] = [[]]
    sizes = [0]
    for item in pdfs:
        size = item[1].stat().st_size
        if chunks[-1] and sizes[-1] + size > ETSY_PER_FILE_LIMIT:
            chunks.append([]); sizes.append(0)
        chunks[-1].append(item); sizes[-1] += size
    if len(chunks) > ETSY_FILE_LIMIT:
        raise ValueError("This bundle needs more than Etsy's five instant-download upload slots. Use fewer books or create two bundles.")
    uploads: list[str] = []
    for index, chunk in enumerate(chunks, 1):
        target = upload / ("puzzle_book_bundle.zip" if len(chunks) == 1 else f"puzzle_book_bundle_part_{index}_of_{len(chunks)}.zip")
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, source in chunk:
                archive.write(source, name)
        if target.stat().st_size > ETSY_PER_FILE_LIMIT:
            raise ValueError(f"{target.name} is over Etsy's 20 MB file limit. Use fewer books or lower PDF size.")
        uploads.append(target.name)
    _bundle_cover(books, folder / "bundle_cover.jpg", title)
    titles = [book["metadata"].get("title", "Puzzle Book") for book in books]
    tags = list(dict.fromkeys(tag for book in books for tag in book["metadata"].get("etsy_tags", []) if tag))[:13]
    description = f"{title} is an instant-download collection of {len(books)} complete puzzle books. Download, print at home, and enjoy a varied screen-free puzzle library with solutions included.\n\nIncluded books:\n" + "\n".join(f"• {name}" for name in titles)
    from .listing_copy import recommended_bundle_prices
    price_plan = recommended_bundle_prices(books)
    (folder / "ETSY_LISTING_KIT.txt").write_text(f"ETSY BUNDLE LISTING KIT\n\nStore: {ETSY_STORE_NAME}\nTitle: {title}\nSuggested starting price: ${price:.2f}\nAutomatic bundle guide: ${price_plan['etsy']:.2f} for Etsy / website digital bundle ({price_plan['savings_percent']}% bundle savings).\nProduct type: Digital files / instant download\n\nDescription:\n{description}\n\nTags:\n" + "\n".join(tags) + f"\n\nUPLOAD THESE FILES\n" + "\n".join(f"• 01_ETSY_UPLOAD_FILES/{name}" for name in uploads) + "\n\nLISTING IMAGE\n• bundle_cover.jpg\n\nETSY CHECK\n• Up to five instant-download files; each must be 20 MB or smaller.\n• Buyers receive puzzle interiors, not print-wrap cover PDFs.\n• Confirm current Etsy rules before publishing.\n", encoding="utf-8")
    (folder / "CUSTOMER_READ_ME.txt").write_text(f"Thank you for choosing {title}!\n\nThis download includes {len(books)} PDF puzzle books. Open the ZIP file(s), then print any pages you would like to solve. Solutions are included in each book.\n", encoding="utf-8")
    details = {"title": title, "price": price, "price_plan": price_plan, "books": titles, "upload_files": uploads, "created": datetime.now().isoformat(timespec="seconds")}
    return folder, details
