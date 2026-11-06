"""Safely apply the September 2026 sales-polish changes to current packages."""
from __future__ import annotations

import hashlib
import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
sys.path.insert(0, str(ROOT))

import pypdf
import puzzle_book_studio as studio
from publishing.package_layout import package_file
from educational_value import educator_back_cover_section, is_educational_context


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""


def source_record(folder: Path) -> Path | None:
    records = list(folder.glob("**/PACKAGE_SOURCE_RECORD.json"))
    return records[0] if records else None


def stable_seed(record: dict) -> int:
    return int(record.get("puzzle_seed") or int(hashlib.sha256(record["title"].encode()).hexdigest()[:8], 16))


def word_search_back(record: dict) -> tuple[str, str]:
    count = int(record.get("puzzle_count") or 0)
    topic = record.get("cover_visual_topic") or "a favorite topic"
    heading = "RELAX, SEARCH, AND DISCOVER"
    body = (
        f"Explore {topic} through {count} carefully organized word search puzzles. Each page pairs a focused puzzle title with words that belong to that subject.\n\n"
        "INSIDE THIS BOOK\n\n"
        f"- {count} topic-focused word searches\n- No repeated puzzle words across the book\n- Complete solutions at the back\n\n"
        "MADE FOR PUZZLE TIME\n\n"
        "Easy-to-read pages make this collection a welcome choice for quiet mornings, travel, waiting rooms, and thoughtful gifts."
    )
    education = educator_back_cover_section(
        record.get("title"), record.get("subtitle"), record.get("theme"),
        record.get("cover_visual_topic"),
    )
    if education:
        body = f"{body}\n\n{education}"
    return heading, body


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--content-only", action="store_true", help="refresh only Scramble and Mixed packages")
    parser.add_argument("--interior-polish", action="store_true", help="refresh themed non-word interiors and educational word-search interiors")
    parser.add_argument("--education-only", action="store_true", help="refresh only educational word-search interiors and wraps")
    args = parser.parse_args()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive = OUT / "_recovery_archive" / f"sales_polish_{stamp}"
    report = []
    folders = [d for d in OUT.iterdir() if d.is_dir() and not d.name.startswith("_") and source_record(d)]
    for folder in sorted(folders):
        rec_path = source_record(folder)
        record = json.loads(rec_path.read_text(encoding="utf-8"))
        kind = record.get("puzzle_type") or "Word Search"
        if args.content_only and kind not in {"Word Scramble + Trivia", "Mixed Brain Games"}:
            continue
        educational_word_search = kind == "Word Search" and is_educational_context(
            record.get("title"), record.get("subtitle"), record.get("theme"), record.get("cover_visual_topic")
        )
        if args.interior_polish and kind not in {"Sudoku", "Cryptogram", "Mixed Brain Games"} and not educational_word_search:
            continue
        if args.education_only and not educational_word_search:
            continue
        if kind not in {"Word Search", "Sudoku", "Cryptogram", "Word Scramble + Trivia", "Mixed Brain Games"}:
            continue
        title = str(record.get("title") or folder.name)
        subtitle = str(record.get("subtitle") or "")
        author = str(record.get("author") or "Jordan M. Slade")
        count = int(record.get("puzzle_count") or 0)
        difficulty = str(record.get("difficulty") or "Standard")
        theme = str(record.get("theme") or record.get("cover_visual_topic") or "General Starter")
        palette = str(record.get("palette") or "nature")
        style = str(record.get("cover_style") or record.get("cover_layout") or "photo")
        art = Path(str(record.get("cover_art") or ""))
        if not art.is_absolute():
            art = ROOT / art
        interior = package_file(folder, "interior.pdf")
        front = package_file(folder, "front_cover.png")
        wrap = package_file(folder, "kdp_full_wrap.pdf")
        preview = package_file(folder, "kdp_full_wrap_preview.png", for_write=True)
        if not all(path.is_file() for path in (interior, front, wrap, art)):
            report.append({"folder": folder.name, "status": "SKIPPED", "reason": "required current artifact or approved art is missing"})
            continue

        old_hashes = {"interior.pdf": sha(interior), "front_cover.png": sha(front), "kdp_full_wrap.pdf": sha(wrap)}
        backup = archive / folder.name
        backup.mkdir(parents=True, exist_ok=True)
        for path in (interior, front, wrap, rec_path):
            shutil.copy2(path, backup / path.name)

        seed = stable_seed(record)
        rebuild_studio_interior = kind in {"Word Scramble + Trivia", "Mixed Brain Games"} or (
            args.interior_polish and kind in {"Sudoku", "Cryptogram", "Mixed Brain Games"}
        )
        if rebuild_studio_interior:
            if kind in {"Word Scramble + Trivia", "Mixed Brain Games", "Cryptogram"}:
                needed = studio.required_content_for_book(kind, count)
                checked, detail, available = studio.content_check(kind, theme)
                if not checked or available < needed:
                    report.append({"folder": folder.name, "status": "BLOCKED", "reason": f"needs {needed}; has {available}. {detail}"})
                    continue
            temp_interior = interior.with_suffix(".sales-polish.tmp.pdf")
            studio.make_interior(kind, title, subtitle, author, count, difficulty, seed, temp_interior, theme,
                                 str(record.get("interior_style") or "Studio Classic"),
                                 list(record.get("reader_bonus_pages") or []), "Automatic")
            temp_interior.replace(interior)
        elif (args.interior_polish or args.education_only) and educational_word_search:
            source_theme = Path(str(record.get("source_theme") or ""))
            if not source_theme.is_file():
                report.append({"folder": folder.name, "status": "BLOCKED", "reason": "educational source theme is missing"})
                continue
            temp_interior = interior.with_suffix(".education-polish.tmp.pdf")
            command = [sys.executable, str(ROOT / "wordsearch.py"), "--themes", str(source_theme),
                       "--out", str(temp_interior), "--title", title, "--subtitle", subtitle,
                       "--author", author, "--seed", str(seed)]
            if count >= 100:
                command.append("--signature-edition")
            subprocess.run(command, cwd=ROOT, check=True)
            temp_interior.replace(interior)

        badge = ("NO REPEATED WORDS" if kind == "Word Search" else
                 "NUMBER - LETTER - SHAPE GAMES" if kind == "Sudoku" else
                 "SUDOKU - CODES - WORD GAMES" if kind == "Mixed Brain Games" else
                 f"INCLUDES {count} PUZZLES")
        format_label = "LARGE PRINT WORD SEARCH" if kind == "Word Search" and "large-print" in subtitle.casefold() else kind.upper()
        cover_cmd = [sys.executable, str(ROOT / "cover.py"), "--title", title, "--subtitle", subtitle,
                     "--author", author, "--badge", badge, "--puzzle-count", str(count),
                     "--difficulty", difficulty, "--format-label", format_label, "--puzzle-type", kind,
                     "--palette", palette, "--theme", theme, "--style", style, "--art", str(art),
                     "--out", str(front)]
        source_theme = record.get("source_theme")
        if kind == "Word Search" and source_theme and Path(str(source_theme)).is_file():
            cover_cmd[2:2] = ["--theme-file", str(source_theme)]
        subprocess.run(cover_cmd, cwd=ROOT, check=True)

        pages = len(pypdf.PdfReader(str(interior)).pages)
        heading, back = studio.back_cover_copy(kind, theme, count, difficulty) if kind != "Word Search" else word_search_back(record)
        subprocess.run([sys.executable, str(ROOT / "wrap_cover.py"), "--front", str(front), "--pages", str(pages),
                        "--palette", palette, "--title", title, "--author", author, "--back", back,
                        "--back-heading", heading, "--puzzle-type", kind, "--puzzle-count", str(count),
                        "--theme", theme, "--out", str(wrap), "--preview-out", str(preview)], cwd=ROOT, check=True)

        # Update only marketplace copies that were byte-identical to a replaced master.
        new_files = {"interior.pdf": interior, "front_cover.png": front, "kdp_full_wrap.pdf": wrap}
        for name, master in new_files.items():
            for candidate in folder.rglob(name):
                if candidate == master or not candidate.is_file():
                    continue
                if sha(candidate) == old_hashes[name]:
                    shutil.copy2(master, candidate)

        record["sales_polish_revision"] = "interior-personality-education-value-v2" if (args.interior_polish or args.education_only) else "themed-trivia-back-cover-thumbnail-v1"
        record["sales_polish_refreshed"] = datetime.now().isoformat(timespec="seconds")
        record["pages"] = pages
        record["interior_pages"] = pages
        rec_path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        report.append({"folder": folder.name, "status": "UPDATED", "type": kind, "pages": pages,
                       "interior_changed": rebuild_studio_interior or ((args.interior_polish or args.education_only) and educational_word_search)})

    archive.mkdir(parents=True, exist_ok=True)
    report_path = OUT / "SALES_POLISH_MIGRATION_REPORT.json"
    report_path.write_text(json.dumps({"created": datetime.now().isoformat(), "archive": str(archive), "books": report}, indent=2), encoding="utf-8")
    print(report_path)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
