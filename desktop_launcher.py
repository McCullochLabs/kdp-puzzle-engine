"""Small Windows launcher packaged as the Desktop Word Search Creator app.

The real studio remains in its project folder because it owns editable themes,
word banks, artwork, and generator scripts.  This launcher finds that folder
and starts its tested local Python environment without showing a console.
"""
from __future__ import annotations

import ctypes
import subprocess
import sys
from pathlib import Path


def project_folder() -> Path | None:
    start = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    for folder in (start, *start.parents):
        if (folder / "launch_word_search_creator.py").is_file() and (folder / "word_search_creator.py").is_file():
            return folder
    return None


def show_problem(message: str) -> None:
    ctypes.windll.user32.MessageBoxW(0, message, "Word Search Creator", 0x10)


def main() -> None:
    project = project_folder()
    if not project:
        show_problem("The Word Search Creator project folder could not be found. Keep this launcher inside the project’s dist folder, or use the Desktop shortcut created by setup.")
        return
    python = project / ".venv" / "Scripts" / "pythonw.exe"
    if not python.is_file():
        python = project / ".venv" / "Scripts" / "python.exe"
    if not python.is_file():
        show_problem("The app's local Python environment is missing. Open the project folder and run its normal setup before using the Desktop launcher.")
        return
    try:
        subprocess.Popen([str(python), str(project / "launch_word_search_creator.py")], cwd=project)
    except OSError as exc:
        show_problem(f"The studio could not be started.\n\n{exc}")


if __name__ == "__main__":
    main()
