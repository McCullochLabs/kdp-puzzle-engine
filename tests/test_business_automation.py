from __future__ import annotations

from pathlib import Path

from PIL import Image

from publishing.business_automation import BusinessAutomation


class _DB:
    def __init__(self, books): self.books = books
    def list_books(self): return self.books
    def get_book(self, book_id): return next((item for item in self.books if item["book_id"] == book_id), None)
    def marketplace_records(self, _book_id): return {key: {"status": "Not Prepared"} for key in ("amazon", "payhip", "barnes_noble")}


class _Service:
    def __init__(self, project, books): self.project, self.db = project, _DB(books)
    def prepare(self, _book_id, _marketplace): return self.project / "prepared", []


def _book(tmp_path: Path, book_id="a", title="Space Puzzle Book", topic="Space"):
    cover = tmp_path / f"{book_id}.png"; Image.new("RGB", (900, 1200), "#234b67").save(cover)
    interior = tmp_path / f"{book_id}.pdf"; interior.write_bytes(b"pdf")
    package = tmp_path / f"package_{book_id}"; package.mkdir()
    source = tmp_path / f"{book_id}.json"; source.write_text("{}", encoding="utf-8")
    return {"book_id": book_id, "source_key": str(source), "package_path": str(package), "metadata": {"title": title, "author": "Jordan M. Slade", "theme": topic, "puzzle_type": "Word Search", "puzzle_count": 60, "production_status": "Complete package", "files": {"front_cover": str(cover), "print_interior": str(interior), "print_cover": str(interior)}}}


def test_opportunities_penalize_near_duplicate_titles(tmp_path):
    first = _book(tmp_path, "a", "Space Planet Word Search", "Space")
    second = _book(tmp_path, "b", "Space Planet Word Search for Adults", "Space")
    engine = BusinessAutomation(_Service(tmp_path, [first, second]))
    items = engine.opportunities()
    assert len(items) == 2
    assert all(item["dimensions"]["duplication_risk"] > 40 for item in items)


def test_queue_is_persistent_and_prioritizes_missing_marketplace_work(tmp_path):
    book = _book(tmp_path)
    engine = BusinessAutomation(_Service(tmp_path, [book]))
    tasks = engine.rebuild_queue()
    assert any(item["task_type"] == "PREPARE_AMAZON" for item in tasks)
    first = engine.next_action(); engine.complete_task(first["task_id"])
    assert BusinessAutomation(_Service(tmp_path, [book])).state()["tasks"][first["task_id"]]["status"] == "COMPLETED"


def test_marketing_kit_uses_real_cover_and_marks_revision(tmp_path):
    book = _book(tmp_path)
    engine = BusinessAutomation(_Service(tmp_path, [book]))
    folder = engine.generate_marketing_kit(book["book_id"])
    assert (folder / "social_square.png").is_file()
    assert (folder / "marketing_manifest.json").is_file()
    assert "uses_real_cover" in (folder / "marketing_manifest.json").read_text(encoding="utf-8")
