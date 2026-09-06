from pathlib import Path

from publishing.production_dashboard import production_attention, production_candidates


class FakeDb:
    def __init__(self, book): self.book = book
    def list_books(self): return [self.book]


class FakeService:
    def __init__(self, book): self.db = FakeDb(book)


def test_production_dashboard_ranks_only_ready_book_with_specific_copy(tmp_path):
    interior, cover = tmp_path / "interior.pdf", tmp_path / "cover.pdf"
    interior.write_bytes(b"pdf"); cover.write_bytes(b"pdf")
    book = {
        "book_id": "space",
        "metadata": {
            "title": "Planet Explorer Word Search", "author": "Jordan M. Slade", "theme": "Space & Astronomy",
            "puzzle_type": "Word Search", "puzzle_count": 48, "difficulty": "Standard", "production_status": "Passed",
            "files": {"print_interior": str(interior), "print_cover": str(cover), "front_cover": str(tmp_path / "front.png")},
        },
        "statuses": {},
    }
    rows = production_candidates(FakeService(book))
    assert len(rows) == 1
    assert rows[0]["copy_score"] >= 75
    assert "production gate" in rows[0]["reason"]


def test_production_dashboard_surfaces_blocked_book_before_ready_work():
    book = {
        "book_id": "needs-work",
        "metadata": {"title": "Unfinished Space Book", "puzzle_type": "Word Search", "puzzle_count": 0, "files": {}},
        "statuses": {},
    }
    rows = production_attention(FakeService(book))
    assert len(rows) == 1
    assert rows[0]["book"]["book_id"] == "needs-work"
    assert rows[0]["issue"]
