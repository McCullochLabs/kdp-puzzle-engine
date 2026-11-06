"""Windows Explorer folder markers for audited output packages.

The marker is intentionally a presentation aid, not a new readiness system.
Callers must supply package folders that have already passed the applicable
technical and editorial audits.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw


MARKER_COMMENT = "SladePuzzleCo audited-ready folder marker"


def create_red_folder_icon(path: Path) -> Path:
    """Create the reusable multi-resolution red-folder Windows icon."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    size = 256
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    # A familiar folder silhouette with enough contrast to stay recognizable
    # at Explorer's smallest icon size.
    draw.rounded_rectangle((34, 49, 137, 102), radius=18, fill="#ff767b", outline="#761c23", width=8)
    draw.rounded_rectangle((20, 76, 236, 216), radius=22, fill="#d9363e", outline="#761c23", width=9)
    draw.rounded_rectangle((30, 96, 226, 203), radius=16, fill="#ed4d54")
    draw.line((42, 113, 214, 113), fill="#ff8589", width=8)
    image.save(path, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return path


def desktop_ini_text(icon_path: Path) -> str:
    """Return the Windows folder-customization record for one shared icon."""
    absolute = Path(icon_path).resolve()
    return (
        "[.ShellClassInfo]\n"
        f"IconResource={absolute},0\n"
        f"IconFile={absolute}\n"
        "IconIndex=0\n"
        f"InfoTip={MARKER_COMMENT}\n"
    )


def mark_folder_red(folder: Path, icon_path: Path, *, apply_attributes: bool = True) -> Path:
    """Assign the red icon to one existing output folder."""
    folder = Path(folder)
    if not folder.is_dir():
        raise FileNotFoundError(f"Output package folder does not exist: {folder}")
    icon_path = Path(icon_path)
    if not icon_path.is_file():
        create_red_folder_icon(icon_path)
    marker = folder / "desktop.ini"
    if marker.exists() and apply_attributes and os.name == "nt":
        # Clear the shell-only attributes before refreshing an existing marker.
        subprocess.run(["attrib", "-h", "-s", str(marker)], check=True, capture_output=True)
    # Explorer's desktop.ini reader is most reliable with Windows Unicode
    # (UTF-16 with a byte-order mark), including paths containing spaces.
    marker.write_text(desktop_ini_text(icon_path), encoding="utf-16")
    if apply_attributes and os.name == "nt":
        subprocess.run(["attrib", "+h", "+s", str(marker)], check=True, capture_output=True)
        # On folders this attribute tells Explorer to read desktop.ini; it does
        # not make the package contents read-only.
        subprocess.run(["attrib", "+r", str(folder)], check=True, capture_output=True)
    return marker


def mark_sale_ready_folder(project: Path, folder: Path, *, apply_attributes: bool = True) -> Path:
    """Apply the project's shared marker after the real final-review gate."""
    project = Path(project)
    return mark_folder_red(
        Path(folder),
        project / "assets" / "system" / "red_sale_ready_folder.ico",
        apply_attributes=apply_attributes,
    )


def refresh_explorer_icons() -> None:
    """Ask Explorer to repaint customized folder icons without restarting it."""
    if os.name == "nt":
        subprocess.run(["ie4uinit.exe", "-show"], check=False, capture_output=True)
