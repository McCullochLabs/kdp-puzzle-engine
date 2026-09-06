"""Canonical, read-only validation command for every project theme."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from project_checks import run_project_check


def validate(themes_dir: Path) -> int:
    problems, notes = run_project_check(themes_dir)
    for note in notes:
        print(f"NOTE: {note}")
    for problem in problems:
        print(f"ERROR: {problem}")
    print(f"Theme validation: {'FAILED' if problems else 'PASSED'}")
    return 1 if problems else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("themes_dir", nargs="?", type=Path,
                        default=PROJECT_ROOT / "themes")
    return validate(parser.parse_args().themes_dir)


if __name__ == "__main__":
    raise SystemExit(main())
