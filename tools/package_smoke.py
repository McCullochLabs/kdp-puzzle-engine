"""Create disposable end-to-end packages using the same creators the UI calls.

Nothing is written to the project's ``out`` folder.  This is deliberately a
release check, not a production tool: each temporary package is removed after
its interior, front cover, wrap, listing kit, and proof gate are inspected.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))


def _require(folder: Path, names: tuple[str, ...]) -> None:
    # New production packages use the organized package layout, while legacy
    # packages remain flat.  Resolve through the shared compatibility helper
    # so this smoke test validates both layouts instead of flagging healthy
    # structured packages as incomplete.
    from publishing.package_layout import package_file
    missing = [name for name in names if not package_file(folder, name).is_file()]
    if missing:
        raise RuntimeError(f"{folder.name} is missing: {', '.join(missing)}")


def _contract(folder: Path) -> None:
    from publishing.package_layout import release_contract
    result = release_contract(folder)
    if not result["ready"]:
        raise RuntimeError(f"{folder.name} did not meet the release contract: {', '.join(result['missing'])}")


def _run_puzzle_books(root: Path) -> list[str]:
    import puzzle_book_studio as studio

    original_out = studio.OUT
    studio.OUT = root / "puzzle_books"
    try:
        results: list[str] = []
        plans = (
            ("Sudoku", "Quiet Symbols Sudoku", "Number, letter and shape puzzles for calm focus", 24, "Easy", "General Starter"),
            ("Cryptogram", "Night Sky Cryptograms", "Space-themed code puzzles with complete answers", 24, "Mixed", "Space & Astronomy"),
            ("Word Scramble + Trivia", "Curious Minds Scramble", "A bright mix of words and quick facts", 24, "Mixed", "General Starter"),
            ("Mixed Brain Games", "Everyday Brain Breaks", "Sudoku, codes, scrambles and trivia", 24, "Mixed", "General Starter"),
        )
        for index, plan in enumerate(plans, 1):
            kind, title, subtitle, count, difficulty, theme = plan
            folder = studio.create_package(kind, title, subtitle, "Jordan M. Slade", count, difficulty, 4100 + index, theme)
            _require(folder, ("interior.pdf", "front_cover.png", "kdp_full_wrap.pdf", "kdp_full_wrap_preview.png", "KDP_LISTING_KIT.txt", "PRODUCTION_PROOF_GATE.txt", "COVER_QUALITY_REPORT.txt"))
            from publishing.package_layout import package_file
            proof = package_file(folder, "PRODUCTION_PROOF_GATE.txt").read_text(encoding="utf-8")
            if "PASS" not in proof:
                raise RuntimeError(f"{kind} did not pass its production proof gate.")
            _contract(folder)
            results.append(f"{kind}: passed")
        return results
    finally:
        studio.OUT = original_out


def _run_word_search(root: Path) -> str:
    """Exercise the supported complete-package path without opening Tk windows."""
    import publishing
    import word_search_creator as studio
    theme = PROJECT / "themes" / "90s_nostalgia.json"
    if not theme.is_file():
        candidates = sorted((PROJECT / "themes").glob("*.json"))
        if not candidates:
            raise RuntimeError("No Word Search theme was available for the smoke package.")
        theme = candidates[0]
    data = json.loads(theme.read_text(encoding="utf-8-sig"))
    count = len(data.get("puzzles") or [])
    folder = root / "word_search"
    title = "Temporary Word Search Proof"
    author = "Jordan M. Slade"
    class _Value:
        def set(self, _value): pass
    class _Button:
        def configure(self, **_kwargs): pass
    class _Database:
        def set_approval_status(self, *_args, **_kwargs): pass
    class _PublishingService:
        def __init__(self, _project): self.db = _Database()
        def sync_theme(self, *_args, **_kwargs): return "temporary-smoke-book"
    result = {}
    runner = object.__new__(studio.WordSearchCreator)
    runner.status = _Value(); runner.generate_button = _Button(); runner.open_button = _Button()
    runner.after = lambda _delay, callback, *args: callback(*args)
    runner._studio_package_finished = lambda success, target, message: result.update(success=success, target=target, message=message)
    runner._load_theme_list = lambda: None
    original_service = publishing.PublishingService
    original_history, original_created, original_batch = studio.save_production_history, studio.record_package_created, studio.record_launch_batch_package
    publishing.PublishingService = _PublishingService
    studio.save_production_history = lambda _record: None
    studio.record_package_created = lambda *_args: None
    studio.record_launch_batch_package = lambda *_args: None
    settings = {
        "theme": str(theme), "title": title, "subtitle": "A temporary end-to-end proof package", "author": author,
        "badge": "NO REPEATED WORDS", "puzzle_count": count, "difficulty": "Standard",
        "format_label": "LARGE PRINT" if max((len(p.get("words", [])) for p in data.get("puzzles", []) if isinstance(p, dict)), default=0) <= 12 else "WORD SEARCH",
        "palette": str(data.get("palette") or "nature"), "style": str(data.get("cover_style") or "classic"),
        "art": "", "art_focus": "center", "signature_edition": False, "archive_after_package": False,
    }
    try:
        runner._run_studio_package(settings, 4110, folder)
    finally:
        publishing.PublishingService = original_service
        studio.save_production_history, studio.record_package_created, studio.record_launch_batch_package = original_history, original_created, original_batch
    if not result.get("success"):
        raise RuntimeError(result.get("message") or "Word Search complete-package smoke test failed.")
    _contract(folder)
    return "Word Search: passed"


def main() -> None:
    # PuzzleBookStudio deliberately registers successful packages in the
    # project ledger.  A disposable smoke run must leave that real production
    # record exactly as it found it, otherwise deleted temp folders appear as
    # phantom books in later readiness checks.
    with tempfile.TemporaryDirectory(prefix="puzzle_package_smoke_") as temporary:
        root = Path(temporary)
        state_paths = (
            PROJECT / "data" / "production_ledger.json",
            PROJECT / "data" / "word_reservations.json",
            PROJECT / "cover_assets" / "generated_background_index.json",
        )
        backups = []
        for index, state in enumerate(state_paths):
            backup = root / f"state_{index}.json"
            existed = state.is_file()
            if existed:
                shutil.copy2(state, backup)
            backups.append((state, backup, existed))
        try:
            results = [*_run_puzzle_books(root), _run_word_search(root)]
        finally:
            for state, backup, existed in backups:
                if existed and backup.is_file():
                    shutil.copy2(backup, state)
                elif not existed and state.exists():
                    state.unlink()
    print("Package smoke check passed: " + "; ".join(results))


if __name__ == "__main__":
    main()
