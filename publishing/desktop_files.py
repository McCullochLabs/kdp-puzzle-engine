"""Open an explicitly selected local output with the operating system."""
import os
from pathlib import Path
import subprocess
import sys


def open_local_path(path: Path) -> None:
    path = Path(path).resolve(strict=True)
    if hasattr(os, 'startfile'):
        os.startfile(path)
    else:
        subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', str(path)])
