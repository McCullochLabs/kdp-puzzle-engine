"""Inventory one-off production scripts that must not become normal UI routes."""
from __future__ import annotations

from pathlib import Path


# These scripts remain available for deliberate historical recovery. New book
# creation must flow through the supported UI/orchestrator instead.
RECOVERY_ONLY_SCRIPTS = (
    "build_discussed_book_packages.py",
    "build_grade_packages.py",
    "build_sample_packages.py",
    "build_signature_kdp_fixed.py",
    "build_signature_launch_packages.py",
    "build_special_signature_packages.py",
    "build_top3_and_school_packages.py",
    "build_top5_market_packages.py",
    "rebuild_holiday_celebrations_kdp.py",
)

ACTIVE_UI_FILES = ("word_search_creator.py", "publishing/ui.py")


def recovery_script_inventory(project: str | Path) -> list[dict]:
    root = Path(project)
    return [{"name": name, "exists": (root / name).is_file(), "classification": "recovery_only"}
            for name in RECOVERY_ONLY_SCRIPTS]


def unsupported_ui_routes(project: str | Path) -> list[dict]:
    """Report accidental references; never edits, runs, or deletes a script."""
    root = Path(project); found: list[dict] = []
    for ui_name in ACTIVE_UI_FILES:
        path = root / ui_name
        if not path.is_file():
            continue
        source = path.read_text(encoding="utf-8-sig")
        for script in RECOVERY_ONLY_SCRIPTS:
            if script in source:
                found.append({"ui": ui_name, "script": script})
    return found
