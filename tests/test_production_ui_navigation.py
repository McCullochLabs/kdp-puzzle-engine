from pathlib import Path


def test_main_studio_keeps_the_daily_creation_and_support_paths_visible():
    source = Path("word_search_creator.py").read_text(encoding="utf-8")
    for label in (
        "Start a new book",
        "Word Search library",
        "Sudoku books",
        "Production dashboard",
        "Publishing Center",
        "Open saved packages",
        "Help & explanations",
        "Error log",
        "New conversation",
        "Guided Word Search",
        "Show commands",
    ):
        assert label in source
    assert "def _show_word_search_workspace" in source
    assert "def _open_assistant_commands" in source
    assert "def _run_assistant_window_command" in source


def test_puzzle_studio_uses_a_clear_plan_design_review_flow():
    source = Path("puzzle_book_studio.py").read_text(encoding="utf-8")
    for label in ("1. BOOK PLAN", "2. DESIGN & READER EXPERIENCE", "3. REVIEW & CREATE", "Apply automatic plan"):
        assert label in source
    assert "self.after_idle(self._maximize_window)" in source


def test_publishing_center_exposes_connected_production_and_expansion_tools():
    source = Path("publishing/ui.py").read_text(encoding="utf-8")
    for label in ("Production dashboard", "Needs your attention first", "Plan safe expansion", "Content expansion plan", "BUYER COPY QUALITY", "Copy price"):
        assert label in source
