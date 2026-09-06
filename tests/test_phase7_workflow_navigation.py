"""Static safety checks for Phase 7's four-area home navigation.

The main window is Tkinter-based, so this verifies the navigation wiring
without creating a desktop window in the automated test run.
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_home_groups_the_existing_tools_under_four_plain_english_areas():
    source = (ROOT / "word_search_creator.py").read_text(encoding="utf-8")
    for label in (
        "1  Create a book",
        "2  Check / fix a book",
        "3  Review / approve a cover",
        "4  Prepare / publish a package",
    ):
        assert label in source
    for route in (
        "self._open_create_new_book",
        "self._open_book_readiness",
        "self._open_cover_choices",
        "self._open_publishing_manager",
    ):
        assert route in source


def test_book_assistant_understands_the_four_plain_english_requests():
    source = (ROOT / "word_search_creator.py").read_text(encoding="utf-8")
    for phrase in ("check my book", "review my cover", "prepare my package"):
        assert phrase in source


def test_long_forms_and_book_readiness_use_a_real_page_scrollbar():
    studio = (ROOT / "word_search_creator.py").read_text(encoding="utf-8")
    operator = (ROOT / "publishing" / "operator_ui.py").read_text(encoding="utf-8")
    assert "def scrollable_dialog_page" in studio
    assert "frame = scrollable_dialog_page(self, padding=18)" in studio
    assert "frame=scrollable_dialog_page(self,padding=18)" in studio
    assert "root = scrollable_dialog_page(self, padding=20)" in operator
    assert "self._refresh_content_scrollbar" in studio
