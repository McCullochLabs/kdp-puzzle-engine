"""Apply the red Explorer icon to every output package that passed the audits."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from publishing.folder_icons import create_red_folder_icon, mark_folder_red, refresh_explorer_icons

OUT = ROOT / "out"
REPORT = ROOT / "reports" / "ACTIVE_OUTPUT_AUDIT.json"
WORD_REPORT = ROOT / "reports" / "EDITORIAL_SALE_READINESS.json"
NONWORD_REPORT = ROOT / "reports" / "NONWORD_EDITORIAL_SALE_READINESS.json"
ICON = ROOT / "assets" / "system" / "red_sale_ready_folder.ico"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def ready_folder_names() -> list[str]:
    """Use the existing audit reports as the only source of marker decisions."""
    technical = load_json(REPORT)
    word = load_json(WORD_REPORT)
    nonword = load_json(NONWORD_REPORT)
    if int(word.get("editorial_holds") or 0) or int(nonword.get("editorial_holds") or 0):
        raise RuntimeError("Editorial holds remain. Resolve them before marking folders ready.")
    failed = [row.get("folder", "") for row in technical.get("rows", []) if not row.get("pass")]
    if failed:
        raise RuntimeError("Technical audit failures remain: " + ", ".join(failed))
    return [str(row["folder"]) for row in technical.get("rows", []) if row.get("pass")]


def main() -> None:
    create_red_folder_icon(ICON)
    names = ready_folder_names()
    marked = []
    for name in names:
        folder = OUT / name
        if not folder.is_dir():
            raise FileNotFoundError(f"Audited output folder is missing: {folder}")
        mark_folder_red(folder, ICON)
        marked.append(name)
    refresh_explorer_icons()
    print(json.dumps({"marked": len(marked), "icon": str(ICON), "folders": marked}, indent=2))


if __name__ == "__main__":
    main()

