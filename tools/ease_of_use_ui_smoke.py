"""Smoke-check the normal creation start and the book-level control center."""
from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from publishing.ui import BookPublishingDialog
from word_search_creator import CreateNewBookDialog


def main() -> None:
    root = tk.Tk(); root.withdraw()
    # Rendering this dialog needs only its displayed book record.  Avoiding a
    # disposable SQLite database keeps this smoke check reliable on Windows.
    book = {"book_id": "smoke-book", "package_path": "", "metadata": {"title": "Smoke Test Book", "subtitle": "", "author": "Test Author", "series": "", "isbn": "", "description": "", "files": {}, "page_count": 0, "trim_size": "8.5x11", "production_status": "Passed"}, "statuses": {}}
    wizard = CreateNewBookDialog(root)
    control = BookPublishingDialog(root, object(), book, lambda: None)
    result: dict[str, bool] = {}
    def finish() -> None:
        result["ready"] = bool(wizard.winfo_exists() and control.winfo_exists())
        wizard.destroy(); control.destroy(); root.quit()
    root.after(350, finish); root.mainloop()
    if not result.get("ready"):
        raise RuntimeError("Create New Book or Book Control Center did not render.")
    root.destroy()
    print("Ease-of-use UI smoke passed: Create New Book and Book Control Center rendered.")


if __name__ == "__main__":
    main()
