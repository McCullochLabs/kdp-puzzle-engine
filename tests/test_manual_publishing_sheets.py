"""Offline coverage for manual B&N and Payhip handoffs."""
import json
from pathlib import Path
import sys

from PIL import Image
from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from integrations.payhip.digital_factory import build_payhip_digital_handoff
from publishing.payhip_product import collection_for, marketplace_category_for, tags_for
from publishing.manual_sheets import render_manual_sheet, sheet_filename
from publishing.marketplaces import BarnesNoblePublisher, PayhipPublisher
from publishing.payhip_communications import store_receipt


def book(tmp_path):
    interior = tmp_path / "interior.pdf"
    writer = canvas.Canvas(str(interior), pagesize=letter)
    for heading in ("Garden Word Search", "Directions", "Puzzle 1 Word Search", "Puzzle 2 Word Search", "Answer Key"):
        writer.drawString(72, 720, heading); writer.showPage()
    writer.save()
    cover = tmp_path / "cover.pdf"; cover.write_bytes(b"local cover")
    image = tmp_path / "front.png"; Image.new("RGB", (1275, 1650), "#2c6357").save(image)
    return {"book_id": "garden-1", "metadata": {
        "title": "Garden Word Search", "subtitle": "48 calm puzzles", "author": "Jordan M. Slade",
        "theme": "Gardening", "puzzle_count": 48, "page_count": 96, "trim_size": "8.5x11",
        "difficulty": "Standard", "price": {"payhip": 5.99, "barnes_noble": 14.99},
        "files": {"print_interior": str(interior), "print_cover": str(cover), "front_cover": str(image)},
    }}


def test_bn_sheet_is_copy_ready_and_template_honest(tmp_path):
    item = book(tmp_path)
    text = render_manual_sheet(item, "barnes_noble", tmp_path / "bn")
    assert "GARDEN WORD SEARCH" in text.upper()
    assert "KDP cover is a visual reference only" in text
    assert "current B&N Press template" in text
    assert BarnesNoblePublisher().blocking_issues(BarnesNoblePublisher().validate(item)) == []
    assert "NOT a final upload cover" in text
    assert BarnesNoblePublisher().prepared_status(item) == "Prepared — Final Cover Needed"


def test_payhip_handoff_has_one_product_sheet_and_safe_customer_assets(tmp_path):
    item = book(tmp_path); target = tmp_path / "payhip"
    created = build_payhip_digital_handoff(item, target)
    names = {path.name for path in created}
    assert {"customer_product.pdf", "preview.pdf", "product_cover.png", "product_image_02.png", "product_image_03.png", "PAYHIP_PUBLISHING_SHEET.txt", "PAYHIP_STORE_SETUP_SHEET.txt", "payhip_manifest.json"} <= names
    sheet = (target / sheet_filename("payhip")).read_text(encoding="utf-8")
    assert "CUSTOMER EMAIL RECEIPT" not in sheet
    assert "PAYHIP KEYWORD" not in sheet
    assert "customer_product.pdf" in sheet
    assert "PAYHIP_STORE_SETUP_SHEET.txt once" in sheet
    assert "MARKETPLACE CATEGORY" in sheet
    assert "SELECT: Education" in sheet
    assert "ADD THESE TAGS ONE AT A TIME:" in sheet
    tags = tags_for(item["metadata"])
    assert tags and len(tags) == len({tag.casefold() for tag in tags})
    assert all(f"{index}. {tag}" in sheet for index, tag in enumerate(tags, 1))
    manifest = json.loads((target / "payhip_manifest.json").read_text(encoding="utf-8"))
    assert manifest["product_title"] == item["metadata"]["title"]
    assert manifest["marketplace_category"] == "Education"
    assert manifest["tags"] == tags
    assert len(PdfReader(str(target / "preview.pdf")).pages) <= len(PdfReader(str(item["metadata"]["files"]["print_interior"])).pages)
    assert "CUSTOMER EMAIL RECEIPT" in (target / "PAYHIP_STORE_SETUP_SHEET.txt").read_text(encoding="utf-8")
    assert PayhipPublisher().validate(item) == []


def test_payhip_collection_category_and_tags_are_separate_product_metadata():
    metadata = {"theme": "Astronomy", "puzzle_type": "Mixed Brain Games", "puzzle_count": 100,
                "difficulty": "Challenging", "amazon_keywords": ["space brain games"]}
    assert collection_for(metadata) == "Brain Games"
    assert marketplace_category_for(metadata) == "Education"
    tags = tags_for(metadata)
    assert "mixed puzzle book" in tags
    assert "space brain games" not in tags
    assert all("keyword" not in tag.casefold() for tag in tags)


def test_payhip_preview_uses_numbered_puzzles_not_title_or_notes(tmp_path):
    interior = tmp_path / "selection.pdf"
    writer = canvas.Canvas(str(interior), pagesize=letter)
    for heading in ("Space Word Search - 50 puzzles", "My Puzzle Notes", "Puzzle 1 Word Search", "Puzzle 2 Word Search", "Solutions"):
        writer.drawString(72, 720, heading); writer.showPage()
    writer.save()
    from integrations.payhip.digital_factory import preview_source_pages
    assert preview_source_pages(interior, "Word Search") == [2, 3]


def test_payhip_preview_recognizes_numbered_scramble_pages(tmp_path):
    from integrations.payhip.digital_factory import preview_source_pages
    from puzzle_book_studio import make_interior

    interior = tmp_path / "scramble.pdf"
    make_interior(
        "Word Scramble + Trivia", "Scramble Test", "24 games", "Jordan M. Slade",
        24, "Standard", 5521, interior,
    )
    selected = preview_source_pages(interior, "Word Scramble + Trivia")
    assert selected
    assert "UNSCRAMBLE:" in (PdfReader(str(interior)).pages[selected[0]].extract_text() or "")


def test_store_receipt_is_professional_and_contains_no_internal_details():
    receipt = store_receipt()
    assert "Thank" in receipt["subject"]
    assert "download" in receipt["message"].casefold()
    assert "API" not in receipt["message"]
