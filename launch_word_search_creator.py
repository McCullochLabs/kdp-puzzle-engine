"""Windows-friendly launcher that reports startup failures without a console window."""
from __future__ import annotations

import traceback
from pathlib import Path

# `out` is reserved for finished book packages. Startup diagnostics belong in
# the app's data area so a failed launch never looks like a partial book.
TRACE_FILE = Path(__file__).resolve().parent / "data" / "error_logs" / "startup_trace.txt"


def trace(message: str) -> None:
    TRACE_FILE.parent.mkdir(parents=True, exist_ok=True)
    TRACE_FILE.write_text(message + "\n", encoding="utf-8")


def show_startup_problem(details: str) -> None:
    log_folder = Path(__file__).resolve().parent / "data" / "error_logs"
    log_folder.mkdir(parents=True, exist_ok=True)
    log_file = log_folder / "startup_problem.txt"
    log_file.write_text(details, encoding="utf-8")
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk(); root.withdraw()
        messagebox.showerror(
            "Word Search Creator could not start",
            "The app could not open. A plain-English startup report was saved here:\n\n"
            f"{log_file}\n\nSend that file to Codex and I can fix it.",
            parent=root,
        )
        root.destroy()
    except Exception:
        pass


try:
    trace("Starting Word Search Creator launcher.")
    from word_search_creator import WordSearchCreator
    trace("Imported the app. Creating the main window.")
    app = WordSearchCreator()
    app.update_idletasks()
    trace(f"Main window created. state={app.state()} viewable={app.winfo_viewable()} geometry={app.winfo_geometry()}. Entering the app.")
    app.mainloop()
except Exception:
    trace("Startup failed. See startup_problem.txt.")
    show_startup_problem(traceback.format_exc())
