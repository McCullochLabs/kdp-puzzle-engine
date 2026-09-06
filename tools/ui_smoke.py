"""Local Windows UI smoke check for the production windows.

This intentionally opens no production package and writes no files in the
project. It gives a quick regression check for Tkinter construction and the
new background cover-gallery path after UI changes.
"""
from __future__ import annotations

import tempfile
import time
import tkinter as tk
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from publishing.manager import PublishingService
from publishing.ui import PublishingManagerDialog, ProductionReadinessDialog, ApprovedProductionQueueDialog, RecoveryCenterDialog, SeriesMapDialog
from puzzle_book_studio import PuzzleBookStudio, PuzzleCoverGallery


def main() -> None:
    root = tk.Tk()
    root.withdraw()
    with tempfile.TemporaryDirectory(prefix="puzzle_ui_smoke_") as folder:
        service = PublishingService(Path(folder))
        manager = PublishingManagerDialog(root, service, sync_catalog=lambda: 0)
        manager.refresh_recommendations()
        readiness = ProductionReadinessDialog(root, service, lambda: None)
        approved = ApprovedProductionQueueDialog(manager, service, lambda: None)
        recovery = RecoveryCenterDialog(manager, service, lambda: None)
        series_map = SeriesMapDialog(manager, service)
        studio = PuzzleBookStudio(root, initial_kind="Sudoku")
        gallery = PuzzleCoverGallery(studio)
        result: dict[str, object] = {}
        def finish() -> None:
            result["rendered"] = bool(gallery.options)
            for window in (gallery, studio, series_map, recovery, approved, readiness, manager):
                if window.winfo_exists():
                    window.destroy()
            root.quit()
        root.after(18000, finish)
        root.mainloop()
        if not result.get("rendered"):
            raise RuntimeError("Puzzle cover gallery did not render any options.")
        root.destroy()
    print("UI smoke check passed: manager, queue, recovery, series map, readiness center, studio, and cover gallery opened successfully.")


if __name__ == "__main__":
    main()
