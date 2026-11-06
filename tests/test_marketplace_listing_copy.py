from pathlib import Path

from PIL import Image
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from publishing.listing_copy import listing_copy_text, recommended_prices, upload_notes_text
from publishing.manager import PublishingService
from publishing.database import MARKETPLACES


def _book(tmp_path: Path) -> dict:
    interior = tmp_path / "interior.pdf"
    writer = canvas.Canvas(str(interior), pagesize=letter)
    for heading in ("Garden Word Search", "Directions", "Puzzle 1 Word Search", "Puzzle 2 Word Search", "Answer Key"):
        writer.drawString(72, 720, heading); writer.showPage()
    writer.save()
    cover = tmp_path / "cover.pdf"; cover.write_bytes(b"cover")
    front = tmp_path / "front.png"; Image.new("RGB", (1275, 1650), "#2c6357").save(front)
    return {"book_id": "book-1", "metadata": {
        "title": "Garden Word Search", "subtitle": "48 relaxing puzzles", "author": "Jordan M. Slade",
        "series": "Garden Collection", "language": "English", "trim_size": "8.5x11",
        "page_count": 160, "puzzle_count": 48, "isbn": "9781234567890",
        "description": "A garden-themed collection with complete solutions.",
        "amazon_keywords": ["garden word search"], "etsy_tags": ["garden puzzle"],
        "website_tags": ["garden"], "ingram_subjects": ["Games & Activities / Word & Word Search"],
        "files": {"print_interior": str(interior), "print_cover": str(cover), "front_cover": str(front)},
    }}


def test_platform_copy_includes_platform_specific_information(tmp_path):
    book = _book(tmp_path); book["metadata"]["price"] = recommended_prices(book["metadata"])
    text = listing_copy_text(book, "etsy")
    assert "ETSY — READY-TO-COPY" in text
    assert "ETSY TAGS" in text
    assert "Suggested starting price: $4.99" in text
    assert "20 MB" in upload_notes_text(book, "etsy")


def test_barnes_noble_recommendation_respects_current_minimum(tmp_path):
    prices = recommended_prices(_book(tmp_path)["metadata"])
    assert prices["barnes_noble"] >= 14.99


def test_generated_metadata_keeps_non_word_search_puzzle_count(tmp_path):
    """Catalog imports need this count for marketplace preview and pricing."""
    from publishing.metadata_service import build_metadata
    meta = build_metadata({"title": "Mixed Brain Games", "puzzle_type": "Mixed Brain Games", "puzzle_count": 100})
    assert meta["puzzle_count"] == 100


def test_template_based_handoff_prepares_reusable_files_and_copy_sheet(tmp_path):
    book = _book(tmp_path); book["metadata"]["price"] = recommended_prices(book["metadata"])
    # The public service uses the same path as the Publishing Manager.
    service = PublishingService(tmp_path)
    service.db.upsert_book("book-1", "test:book-1", book["metadata"], str(tmp_path))
    target, issues = service.prepare("book-1", "barnes_noble")
    assert not issues
    assert (target / "interior_starting_file.pdf").is_file()
    assert (target / "READY_TO_COPY_LISTING.txt").is_file()
    assert (target / "UPLOAD_NOTES.txt").is_file()


def test_all_marketplaces_make_a_copy_ready_handoff_when_the_book_is_complete(tmp_path):
    book = _book(tmp_path); book["metadata"]["price"] = recommended_prices(book["metadata"])
    service = PublishingService(tmp_path)
    service.db.upsert_book("book-1", "test:book-1", book["metadata"], str(tmp_path))
    for marketplace in MARKETPLACES:
        target, issues = service.prepare("book-1", marketplace)
        assert not issues, marketplace
        if marketplace == "payhip":
            assert (target / "PAYHIP_PUBLISHING_SHEET.txt").is_file()
            assert not (target / "READY_TO_COPY_LISTING.txt").exists()
            assert (target / "customer_product.pdf").is_file()
            assert (target / "preview.pdf").is_file()
        else:
            assert (target / "READY_TO_COPY_LISTING.txt").is_file(), marketplace
            assert (target / "UPLOAD_NOTES.txt").is_file(), marketplace
