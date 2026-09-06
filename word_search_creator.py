"""Beginner-friendly Windows front end for the existing word-search engine.

This file deliberately calls wordsearch.py as a separate process instead of
changing its PDF-generation code.  The command-line workflow remains intact.
"""

from __future__ import annotations

import json
import hashlib
import math
import os
import random
import re
import csv
import shutil
import subprocess
import sys
import threading
import time
import tempfile
import tkinter as tk
import webbrowser
import zipfile
from datetime import datetime
from io import BytesIO
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from tkinter.scrolledtext import ScrolledText
from urllib.parse import quote_plus
from PIL import Image, ImageTk
from cover import PALETTES as COVER_PALETTES, cover_quality_report

import wordsearch as puzzle_engine
from openclipart_service import asset_record, download_openclipart, fetch_thumbnail, search_openclipart
from project_checks import run_project_check
from preflight import preflight, report_text as package_preflight_text
from theme_health import read_theme_health, record_theme_health
from publishing.package_layout import initialize_package_layout, package_file, package_layout_readme, proof_folder
from publishing.production_plan import content_capacity, production_plan_summary
from background_generation.index import BackgroundAssetIndex
from background_generation.routing import CoverRequest, request_from_mapping, select_cover_asset, select_cover_gallery, write_routing_diagnostics


APP_DIR = Path(__file__).resolve().parent
THEMES_DIR = APP_DIR / "themes"
OUTPUT_DIR = APP_DIR / "out"
ENGINE = APP_DIR / "wordsearch.py"
COVER_ENGINE = APP_DIR / "cover.py"
WRAP_ENGINE = APP_DIR / "wrap_cover.py"
WINDOWS_VENV_PYTHON = APP_DIR / ".venv" / "Scripts" / "python.exe"
PRESETS_FILE = APP_DIR / "production_presets.json"
USED_THEMES_DIR = THEMES_DIR / "Used Themes"
ARCHIVE_THEMES_DIR = THEMES_DIR / "_Archive"
RESEARCH_THEMES_DIR = THEMES_DIR / "_Research"
DRAFT_THEMES_DIR = THEMES_DIR / "_Drafts"
RELEASE_CATALOG_FILE = APP_DIR / "release_catalog.json"
RECENT_THEMES_FILE = APP_DIR / "recent_themes.json"
FAVORITE_THEMES_FILE = APP_DIR / "favorite_themes.json"
COVER_PREFERENCES_FILE = APP_DIR / "cover_preferences.json"
BRAND_KIT_FILE = APP_DIR / "brand_kit.json"
APP_PREFERENCES_FILE = APP_DIR / "app_preferences.json"
PRODUCTION_HISTORY_FILE = APP_DIR / "production_history.json"
ERROR_LOG_FILE = APP_DIR / "error_log.json"
WORD_BANKS_DIR = APP_DIR / "word_banks"
LIBRARY_AUDIT_FILE = WORD_BANKS_DIR / "library_audit_history.json"
WORD_REVIEW_QUEUE_FILE = WORD_BANKS_DIR / "word_review_queue.json"
TOPIC_READINESS_FILE = WORD_BANKS_DIR / "TOPIC_LIBRARY_READINESS.json"
TOPIC_WORD_AUDIT_FILE = WORD_BANKS_DIR / "TOPIC_WORD_AUDIT.json"
SAVED_THEME_SOURCE_AUDIT_FILE = WORD_BANKS_DIR / "SAVED_THEME_SOURCE_AUDIT.json"
THEME_HEALTH_CACHE_FILE = APP_DIR / "data" / "theme_readiness_cache.json"
COVER_ASSETS_DIR = APP_DIR / "cover_assets"
CUSTOM_TOPIC_PACKS_FILE = WORD_BANKS_DIR / "custom_topic_packs.json"
NICHE_COVER_MEMORY_FILE = APP_DIR / "niche_cover_memory.json"
ART_FAVORITES_FILE = COVER_ASSETS_DIR / "openclipart" / "favorites.json"
ART_USAGE_HISTORY_FILE = COVER_ASSETS_DIR / "openclipart" / "cover_art_history.json"
BACKGROUND_PHOTO_LIBRARY_FILE = COVER_ASSETS_DIR / "background_photo_library.json"
COMPETITOR_NOTES_FILE = APP_DIR / "competitor_notes.json"
MARKET_PULSE_FILE = APP_DIR / "market_pulse.json"
VERSION_FILE = APP_DIR / "VERSION.txt"
CHANGELOG_FILE = APP_DIR / "CHANGELOG.md"
PRODUCTION_LOCK_FILE = APP_DIR / "production_lock.json"
LAUNCH_BATCH_FILE = APP_DIR / "launch_batch_tracker.json"
try:
    APP_VERSION = VERSION_FILE.read_text(encoding="utf-8-sig").strip() or "2.2.0"
except OSError:
    APP_VERSION = "2.2.0"  # Keeps the app usable if the small version file is ever moved.

DEFAULT_CONTRIBUTOR = "Jordan M. Slade"
BRAND_NAME = "Slade Puzzles"


class HoverHelp:
    """A small plain-English explanation shown when the pointer rests on a control."""

    def __init__(self, widget: tk.Widget, message: str) -> None:
        self.widget, self.message, self.window = widget, message, None
        widget.bind("<Enter>", self.show, add="+")
        widget.bind("<Leave>", self.hide, add="+")
        widget.bind("<ButtonPress>", self.hide, add="+")

    def show(self, _event=None) -> None:
        if self.window or not self.message:
            return
        try:
            x = self.widget.winfo_rootx() + 12; y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
            self.window = tk.Toplevel(self.widget); self.window.wm_overrideredirect(True); self.window.wm_geometry(f"+{x}+{y}")
            ttk.Label(self.window, text=self.message, padding=(8, 5), wraplength=300, justify="left", relief="solid").pack()
        except tk.TclError:
            self.window = None

    def hide(self, _event=None) -> None:
        if self.window:
            self.window.destroy(); self.window = None


def add_hover_help(widget: tk.Widget, message: str) -> None:
    HoverHelp(widget, message)


def scrollable_dialog_page(dialog: tk.Toplevel, *, padding: int = 18) -> ttk.Frame:
    """Return a dialog page that stays reachable on shorter Windows screens.

    Several production forms contain a useful final review or action row below
    their editable content. A fixed dialog height can hide that row behind the
    taskbar. Keeping the page in a canvas gives those forms one honest
    scrollbar without changing Text and Treeview controls inside them.
    """
    shell = ttk.Frame(dialog)
    shell.pack(fill="both", expand=True)
    shell.columnconfigure(0, weight=1)
    shell.rowconfigure(0, weight=1)
    canvas = tk.Canvas(shell, highlightthickness=0, borderwidth=0)
    canvas.grid(row=0, column=0, sticky="nsew")
    scrollbar = ttk.Scrollbar(shell, orient="vertical", command=canvas.yview)
    scrollbar.grid(row=0, column=1, sticky="ns")
    canvas.configure(yscrollcommand=scrollbar.set, yscrollincrement=18)
    page = ttk.Frame(canvas, padding=padding)
    page_window = canvas.create_window((0, 0), window=page, anchor="nw")

    def refresh_region(_event=None) -> None:
        canvas.configure(scrollregion=canvas.bbox("all"))

    def fit_width(event) -> None:
        canvas.itemconfigure(page_window, width=event.width)
        refresh_region()

    def scroll_page(event):
        if isinstance(event.widget, (tk.Text, ttk.Treeview)):
            return None
        steps = int(event.delta / 120) if event.delta else 0
        if steps:
            canvas.yview_scroll(-steps, "units")
            return "break"
        return None

    page.bind("<Configure>", refresh_region)
    canvas.bind("<Configure>", fit_width)

    def attach_wheel_handlers() -> None:
        def attach(widget: tk.Misc) -> None:
            widget.bind("<MouseWheel>", scroll_page, add="+")
            for child in widget.winfo_children():
                attach(child)
        attach(page)

    dialog.after_idle(attach_wheel_handlers)
    dialog._scrollable_page = (canvas, scrollbar, page)  # type: ignore[attr-defined]
    return page


def saved_theme_files() -> list[Path]:
    """Return active book JSON files, including organized series subfolders."""
    files: list[Path] = []
    for path in THEMES_DIR.rglob("*.json"):
        if any(folder in path.parents for folder in (USED_THEMES_DIR, ARCHIVE_THEMES_DIR, RESEARCH_THEMES_DIR, DRAFT_THEMES_DIR)):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            if bool(data.get("draft")):
                continue
            if isinstance(data.get("puzzles"), list):
                files.append(path)
        except (OSError, json.JSONDecodeError):
            continue
    return sorted(files, key=lambda item: (str(item.parent).lower(), item.name.lower()))


def quick_theme_readiness(data: dict) -> tuple[bool, str]:
    """Fast format-and-safety check; the full Check Book also validates topic fit."""
    puzzles = data.get("puzzles")
    if not isinstance(puzzles, list) or not puzzles:
        return False, "Needs review"
    if len(puzzles) < 48:
        return False, f"Needs {48 - len(puzzles)} more puzzles"
    if not str(data.get("title") or "").strip():
        return False, "Needs title"
    for puzzle in puzzles:
        words = puzzle.get("words") if isinstance(puzzle, dict) else None
        if not isinstance(words, list) or not (12 <= len(words) <= 25):
            return False, "Needs 12 words per puzzle"
    all_words = [re.sub(r"[^A-Z]", "", str(word).upper()) for puzzle in puzzles for word in puzzle.get("words", [])]
    all_words = [word for word in all_words if word]
    if len(all_words) != len(set(all_words)):
        return False, "Repeated words need replacement"
    flagged = sorted(set(all_words) & REVIEW_REQUIRED_TERMS)
    if flagged:
        return False, "Needs safe word replacements"
    ordered_lists = [
        [re.sub(r"[^A-Z]", "", str(word).upper()) for word in puzzle.get("words", [])]
        for puzzle in puzzles if isinstance(puzzle, dict)
    ]
    alphabetized = sum(1 for words in ordered_lists if len(words) >= 6 and words == sorted(words))
    if ordered_lists and alphabetized / len(ordered_lists) >= 0.5:
        return False, "Alphabetized word lists need rebuilding"
    return True, "Format complete - run content check"


def word_bank_freshness(data: dict) -> tuple[int, str]:
    """Score variety across a book's puzzle lists without changing its content."""
    puzzles = data.get("puzzles", [])
    all_words = [str(word).upper() for puzzle in puzzles if isinstance(puzzle, dict) for word in puzzle.get("words", [])]
    if not all_words: return 0, "Needs words"
    score = round(100 * len(set(all_words)) / len(all_words))
    label = "Excellent variety" if score >= 55 else ("Good variety" if score >= 35 else "High repetition")
    return score, label


def series_consistency_notes(path: Path, data: dict) -> list[str]:
    series = str(data.get("series") or "").strip()
    if not series:
        return []
    members: list[dict] = []
    for candidate in saved_theme_files():
        try:
            item = json.loads(candidate.read_text(encoding="utf-8-sig"))
            if candidate != path and str(item.get("series") or "").strip().casefold() == series.casefold(): members.append(item)
        except (OSError, json.JSONDecodeError):
            continue
    if not members: return [f"Series check: '{series}' has no other active members yet."]
    notes: list[str] = []
    for key, label in (("author", "author"), ("palette", "palette"), ("cover_style", "cover layout")):
        values = {str(member.get(key) or "").strip() for member in members}
        current = str(data.get(key) or "").strip()
        if current and values and current not in values:
            notes.append(f"Series check: this book’s {label} differs from other '{series}' books.")
    return notes or [f"Series check: consistent with {len(members)} other active '{series}' book(s)."]


def puzzle_difficulty_label(data: dict) -> str:
    saved = str(data.get("difficulty_label") or "").strip().title()
    if saved in {"Relaxing", "Standard", "Challenging"}:
        return saved
    puzzles = data.get("puzzles", [])
    word_counts = [len(puzzle.get("words", [])) for puzzle in puzzles if isinstance(puzzle, dict)]
    longest = max((len(str(word).replace(" ", "")) for puzzle in puzzles if isinstance(puzzle, dict) for word in puzzle.get("words", [])), default=0)
    average = sum(word_counts) / len(word_counts) if word_counts else 0
    if average <= 12 and longest <= 11: return "Relaxing"
    if average <= 16 and longest <= 14: return "Standard"
    return "Challenging"


def puzzle_variety_notes(data: dict) -> list[str]:
    puzzles = [p for p in data.get("puzzles", []) if isinstance(p, dict)]
    notes: list[str] = []
    seen: set[tuple[str, ...]] = set()
    for index, puzzle in enumerate(puzzles, 1):
        words = tuple(sorted({str(word).upper() for word in puzzle.get("words", [])}))
        if words in seen: notes.append(f"Puzzle variety: Puzzle {index} repeats an earlier word group.")
        seen.add(words)
    for left in range(len(puzzles)):
        a = {str(word).upper() for word in puzzles[left].get("words", [])}
        for right in range(left + 1, len(puzzles)):
            b = {str(word).upper() for word in puzzles[right].get("words", [])}
            if a and b and len(a & b) / max(len(a | b), 1) >= .85:
                notes.append(f"Puzzle variety: Puzzles {left + 1} and {right + 1} are very similar."); return notes
    return notes or ["Puzzle variety: no repeated or near-duplicate puzzle word groups found."]


def archive_used_theme(path: Path) -> Path:
    """Move a successfully packaged theme out of the active library safely."""
    USED_THEMES_DIR.mkdir(parents=True, exist_ok=True)
    target = USED_THEMES_DIR / path.name
    if target.exists():
        target = USED_THEMES_DIR / f"{path.stem}_{datetime.now():%Y%m%d_%H%M%S}{path.suffix}"
    shutil.move(str(path), str(target))
    return target


def load_release_catalog() -> dict[str, dict[str, object]]:
    try:
        data = json.loads(RELEASE_CATALOG_FILE.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_release_catalog(catalog: dict[str, dict[str, object]]) -> None:
    RELEASE_CATALOG_FILE.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")


def record_package_created(theme_path: Path, title: str, folder: Path, pages: int) -> None:
    """Make completed packages visible in My Books Dashboard automatically."""
    catalog = load_release_catalog()
    record = catalog.setdefault(theme_path.name, {})
    if str(record.get("stage") or "") not in {"Published", "Paused"}:
        record["stage"] = "Ready"
    record.update({"title_at_package": title, "package": str(folder), "package_created": datetime.now().isoformat(timespec="seconds"), "interior_pages": pages, "release_status": "Ready for KDP Print Previewer"})
    save_release_catalog(catalog)


def contributor_safety_notes(author: str) -> list[str]:
    """Keep the publishing brand out of KDP's contributor field."""
    clean = " ".join(str(author or "").split())
    if not clean:
        return ["BLOCK - Add a real author or pen name before creating a package."]
    if clean.casefold() == BRAND_NAME.casefold() or "puzzles" in clean.casefold():
        return [f"BLOCK - '{clean}' looks like a publishing brand, not a contributor name. Use your pen name, such as {DEFAULT_CONTRIBUTOR}."]
    return []


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_release_safety_files(folder: Path, theme_path: Path, data: dict, settings: dict[str, object], pages: int) -> list[str]:
    """Write one audit trail per package and return only true blocking issues.

    This intentionally verifies file metadata and written listing data. It does
    not pretend to read pixels or replace KDP's Print Previewer.
    """
    from pypdf import PdfReader
    expected_author = " ".join(str(settings.get("author") or data.get("author") or "").split())
    title = str(settings.get("title") or data.get("title") or "Word Search").strip()
    subtitle = str(settings.get("subtitle") or data.get("subtitle") or "").strip()
    blockers = contributor_safety_notes(expected_author)
    interior = package_file(folder, "interior.pdf")
    listing = package_file(folder, "KDP_LISTING_KIT.txt")
    actual_author = ""
    try:
        actual_author = " ".join(str((PdfReader(str(interior)).metadata.author if interior.exists() else "") or "").split())
    except Exception as exc:
        blockers.append(f"BLOCK - Could not read interior author metadata: {exc}")
    if actual_author != expected_author:
        blockers.append(f"BLOCK - Interior author metadata is '{actual_author or 'blank'}', not '{expected_author}'.")
    listing_text = listing.read_text(encoding="utf-8") if listing.exists() else ""
    for label, value in (("title", title), ("author", expected_author)):
        if value and value not in listing_text:
            blockers.append(f"BLOCK - KDP listing kit does not contain the selected {label}: {value}.")
    author_report = ["AUTHOR & METADATA CONSISTENCY", "=" * 48, f"Expected contributor: {expected_author}", f"Interior PDF contributor: {actual_author or 'NOT FOUND'}", f"Listing kit contains title: {'YES' if title in listing_text else 'NO'}", f"Listing kit contains contributor: {'YES' if expected_author in listing_text else 'NO'}", "", "Result: BLOCK — fix the items below." if blockers else "Result: PASS — package metadata uses one contributor name."]
    author_report.extend(blockers or ["PASS - The author field is a contributor name, not the Slade Puzzles brand."])
    package_file(folder, "AUTHOR_CONSISTENCY_REPORT.txt", for_write=True).write_text("\n".join(author_report) + "\n", encoding="utf-8")

    art_path = Path(str(settings.get("art") or "")) if str(settings.get("art") or "").strip() else None
    approved_background = BackgroundAssetIndex().ledger_details(art_path) if art_path and art_path.exists() else None
    routing_request = request_from_mapping(
        str(settings.get("creation_route") or "Word Search package"),
        {**data, "theme_path": str(theme_path)},
        title=title, subtitle=subtitle, author=expected_author,
        preferred_asset=str(art_path) if art_path else "",
    )
    routing_decision = select_cover_asset(routing_request)
    write_routing_diagnostics(package_file(folder, "COVER_ROUTING.json", for_write=True), routing_decision)
    art = asset_record(art_path, COVER_ASSETS_DIR) if art_path and art_path.exists() else None
    if not approved_background:
        blockers.append("BLOCK - This package has no current, explicitly approved cover background. Choose an approved background or generate and review one before creating a production package.")
    ledger = ["COVER ART & RIGHTS LEDGER", "=" * 48, f"Brand / imprint: {BRAND_NAME}", f"Contributor shown in package: {expected_author}", f"Selected image: {art_path.name if art_path else 'No external image selected'}"]
    if approved_background:
        provenance = approved_background.get("provenance", {})
        ledger += [
            f"Asset ID: {approved_background.get('asset_id', '')}",
            f"Production approval: {approved_background.get('production_approved', False)}",
            f"Classification: {approved_background.get('classification', '')}",
            f"Generation provider: {provenance.get('provider', '')}",
            f"Generation model: {provenance.get('model', 'project background library')}",
            f"File checksum: {approved_background.get('sha256', '')}",
        ]
    elif art:
        ledger += [f"Artwork title: {art.get('title', '')}", f"Artist: {art.get('artist_name', '')}", f"License: {art.get('license', 'review source record')}", f"Source page: {art.get('page_url', '')}"]
    else:
        ledger += ["Source record: locally generated or built-in artwork.", "Before publishing, confirm you have rights to any image, font, or asset you added yourself."]
    package_file(folder, "COVER_ART_RIGHTS_LEDGER.txt", for_write=True).write_text("\n".join(ledger) + "\n", encoding="utf-8")

    thumbnail = package_file(folder, "front_cover_thumbnail.png")
    dimensions = "not found"
    try:
        with Image.open(package_file(folder, "front_cover.png")) as cover:
            dimensions = f"{cover.width} x {cover.height} pixels"
    except OSError:
        blockers.append("BLOCK - Could not inspect the front-cover image.")
    thumb_lines = ["COVER THUMBNAIL REVIEW", "=" * 48, f"Print cover size: {dimensions}", f"Small review image: {'available' if thumbnail.exists() else 'not found'}", "", "Human check: open buyer_thumbnail.png and make sure the title, badge, and topic can be understood at a small size."]
    package_file(folder, "COVER_THUMBNAIL_REVIEW.txt", for_write=True).write_text("\n".join(thumb_lines) + "\n", encoding="utf-8")

    overlaps = cross_book_similarity_report(theme_path, data)
    duplicate_lines = ["PUBLISHED-CATALOG DUPLICATE GUARD", "=" * 48]
    blocked_overlap = [item for item in overlaps if item["level"] == "block"]
    if blocked_overlap:
        blockers.append("BLOCK - This book is extremely similar to an existing saved theme. Review ORIGINALITY_CHECK.txt before packaging.")
        duplicate_lines += [f"BLOCK - {item['title']}: {float(item['overlap']):.0%} shared vocabulary" for item in blocked_overlap]
    else:
        duplicate_lines.append("PASS - No near-duplicate saved book was found.")
    package_file(folder, "PUBLISHED_CATALOG_DUPLICATE_GUARD.txt", for_write=True).write_text("\n".join(duplicate_lines) + "\n", encoding="utf-8")

    manifest = {"app_version": APP_VERSION, "created": datetime.now().isoformat(timespec="seconds"), "source_theme": str(theme_path), "source_theme_sha256": _file_sha256(theme_path) if theme_path.exists() else "", "title": title, "subtitle": subtitle, "author": expected_author, "brand": BRAND_NAME, "puzzle_type": str(data.get("puzzle_type") or "Word Search"), "cover_puzzle_type": "Word Search", "cover_visual_topic": str(data.get("detected_topic") or data.get("theme") or ""), "difficulty": str(data.get("difficulty") or data.get("difficulty_label") or "standard"), "puzzle_count": len(data.get("puzzles", [])), "interior_pages": pages, "palette": settings.get("palette", ""), "cover_layout": settings.get("style", ""), "cover_art": str(art_path) if art_path else "", "cover_art_id": str((approved_background or {}).get("asset_id") or ""), "cover_art_sha256": str((approved_background or {}).get("sha256") or ""), "cover_art_approval_revision": (approved_background or {}).get("approval_revision") or (approved_background or {}).get("updated_at") or "", "cover_art_approval_state": str((approved_background or {}).get("approval_state") or ("approved" if approved_background else "missing")), "cover_art_provenance": dict((approved_background or {}).get("provenance") or {}), "cover_routing": routing_decision.diagnostics(), "release_status": "Needs fixes" if blockers else "Ready for KDP Print Previewer"}
    package_file(folder, "PACKAGE_SOURCE_RECORD.json", for_write=True).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    final_steps = ["FINAL KDP UPLOAD STEPS", "=" * 48, f"Book: {title}", f"Contributor: {expected_author}", "", "1. Confirm the KDP contributor field is exactly the contributor above—not the Slade Puzzles brand.", "2. Upload interior.pdf and kdp_full_wrap.pdf.", "3. Copy the title, subtitle, description, and seven keywords from KDP_LISTING_KIT.txt.", "4. Confirm rights, territories, categories, pricing, and AI-content disclosure based on the actual book.", "5. Run the current KDP Print Previewer and correct every warning before publishing.", "6. Save the ASIN and Amazon link in My Books Dashboard after the book goes live."]
    package_file(folder, "FINAL_KDP_UPLOAD_STEPS.txt", for_write=True).write_text("\n".join(final_steps) + "\n", encoding="utf-8")
    first = ["FIX THIS FIRST", "=" * 48]
    first += blockers if blockers else ["PASS - Automated package checks passed. Your remaining required step is KDP Print Previewer."]
    package_file(folder, "FIX_THIS_FIRST.txt", for_write=True).write_text("\n".join(first) + "\n", encoding="utf-8")
    truth = intelligence_production_truth(data)
    truth_lines = ["PRODUCTION TRUTH REPORT", "=" * 48]
    if truth is None:
        truth_lines.append("Review note — this legacy theme has no recognized Master Library topic, so mini-theme coherence was not certified.")
    else:
        truth_lines.append(f"Result: {truth.status}")
        truth_lines.append(f"Repeat-free format available: {truth.recommended_puzzles} puzzles × {truth.recommended_words_per_puzzle} words")
        truth_lines += ["", "Blocking findings:"] + (truth.errors or ["None"])
        truth_lines += ["", "Review notes:"] + (truth.warnings or ["None"])
    package_file(folder, "PRODUCTION_TRUTH_REPORT.txt", for_write=True).write_text("\n".join(truth_lines) + "\n", encoding="utf-8")
    return blockers


def load_recent_theme_paths(limit: int = 6) -> list[Path]:
    """Read recent choices without ever making the theme library depend on them."""
    try:
        items = json.loads(RECENT_THEMES_FILE.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return []
    paths: list[Path] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, str):
            continue
        path = Path(item)
        if not path.is_absolute():
            path = APP_DIR / path
        try:
            if path.exists() and path.suffix.lower() == ".json" and path not in paths:
                paths.append(path)
        except OSError:
            continue
    return paths[:limit]


def record_recent_theme(path: Path, limit: int = 6) -> None:
    """Keep a short local history of themes opened in Book Studio."""
    try:
        stored = str(path.resolve().relative_to(APP_DIR.resolve()))
    except ValueError:
        stored = str(path.resolve())
    existing: list[str] = []
    for old_path in load_recent_theme_paths(limit=50):
        try:
            value = str(old_path.resolve().relative_to(APP_DIR.resolve()))
        except ValueError:
            value = str(old_path.resolve())
        if value != stored:
            existing.append(value)
    try:
        RECENT_THEMES_FILE.write_text(json.dumps([stored, *existing][:limit], indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass  # A recent-history shortcut should never interrupt normal book work.


def _stored_theme_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(APP_DIR.resolve()))
    except ValueError:
        return str(path.resolve())


def load_favorite_theme_paths() -> list[Path]:
    try:
        values = json.loads(FAVORITE_THEMES_FILE.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return []
    paths: list[Path] = []
    for value in values if isinstance(values, list) else []:
        if not isinstance(value, str):
            continue
        path = Path(value)
        if not path.is_absolute(): path = APP_DIR / path
        if path.exists() and path.suffix.lower() == ".json" and path not in paths:
            paths.append(path)
    return paths


def toggle_favorite_theme(path: Path) -> bool:
    """Toggle a local favorite and return its new saved state."""
    stored = _stored_theme_path(path)
    values = [_stored_theme_path(item) for item in load_favorite_theme_paths()]
    if stored in values:
        values.remove(stored); saved = False
    else:
        values.insert(0, stored); saved = True
    try:
        FAVORITE_THEMES_FILE.write_text(json.dumps(values, indent=2) + "\n", encoding="utf-8")
    except OSError:
        return False
    return saved


def load_cover_preferences(path: Path) -> dict[str, str]:
    try:
        data = json.loads(COVER_PREFERENCES_FILE.read_text(encoding="utf-8-sig"))
        saved = data.get(_stored_theme_path(path), {}) if isinstance(data, dict) else {}
        return {str(key): str(value) for key, value in saved.items()} if isinstance(saved, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_cover_preferences(path: Path, settings: dict[str, str]) -> None:
    try:
        data = json.loads(COVER_PREFERENCES_FILE.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict): data = {}
    except (OSError, json.JSONDecodeError):
        data = {}
    data[_stored_theme_path(path)] = {key: settings[key] for key in ("palette", "style", "badge", "imprint", "art", "art_focus") if key in settings}
    try:
        COVER_PREFERENCES_FILE.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass


def load_app_preferences() -> dict[str, object]:
    """Read optional comfort settings without ever blocking app startup."""
    try:
        data = json.loads(APP_PREFERENCES_FILE.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_app_preferences(settings: dict[str, object]) -> None:
    try:
        APP_PREFERENCES_FILE.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass


def load_brand_kit() -> dict[str, str]:
    try:
        data = json.loads(BRAND_KIT_FILE.read_text(encoding="utf-8-sig")); return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError): return {}


def save_production_history(record: dict[str, object]) -> None:
    try: history = json.loads(PRODUCTION_HISTORY_FILE.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError): history = []
    if not isinstance(history, list): history = []
    history.insert(0, record)
    try: PRODUCTION_HISTORY_FILE.write_text(json.dumps(history[:250], indent=2) + "\n", encoding="utf-8")
    except OSError: pass


def log_plain_error(action: str, book: str, error: object, suggestion: str) -> None:
    """Save a beginner-friendly record without exposing a stack trace in the app."""
    try: entries = json.loads(ERROR_LOG_FILE.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError): entries = []
    if not isinstance(entries, list): entries = []
    entries.insert(0, {"time": datetime.now().isoformat(timespec="seconds"), "action": action, "book": book or "No book selected", "what_happened": str(error), "suggestion": suggestion})
    try: ERROR_LOG_FILE.write_text(json.dumps(entries[:200], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except OSError: pass


def load_error_log() -> list[dict[str, str]]:
    try:
        data=json.loads(ERROR_LOG_FILE.read_text(encoding="utf-8-sig")); return [item for item in data if isinstance(item,dict)] if isinstance(data,list) else []
    except (OSError,json.JSONDecodeError): return []


def load_master_word_bank() -> dict:
    try:
        data=json.loads((WORD_BANKS_DIR / "Guided_Builder_Master_Word_Bank.json").read_text(encoding="utf-8-sig"))
        return data if isinstance(data,dict) else {}
    except (OSError,json.JSONDecodeError): return {}


def load_json_record(path: Path) -> dict:
    """Read an optional support report without making the app depend on it."""
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def library_intelligence_summary() -> dict[str, int]:
    """Return small, display-safe facts from the generated library reports."""
    readiness = load_json_record(TOPIC_READINESS_FILE).get("summary", {})
    audit = load_json_record(TOPIC_WORD_AUDIT_FILE).get("summary", {})
    return {
        "ready_48": int(readiness.get("ready_for_standard", 0)) if isinstance(readiness, dict) else 0,
        "ready_100": int(readiness.get("ready_for_signature", 0)) if isinstance(readiness, dict) else 0,
        "needs_expansion": int(readiness.get("needs_expansion", 0)) if isinstance(readiness, dict) else 0,
        "dictionary_confirmed": int(audit.get("dictionary_confirmed_entries", 0)) if isinstance(audit, dict) else 0,
        "review_terms": int(audit.get("entries_needing_human_or_source_review", 0)) if isinstance(audit, dict) else 0,
    }


def refresh_library_intelligence() -> tuple[bool, str]:
    """Safely rebuild every library report used by the app.

    This deliberately does not touch theme files or create books.  It refreshes
    the Master Library, candidate catalog, readiness map, and audits in the
    order their data depends on each other.
    """
    python = WINDOWS_VENV_PYTHON if WINDOWS_VENV_PYTHON.exists() else Path(sys.executable)
    scripts = (
        "classify_dictionary_candidates.py", "build_master_word_bank.py",
        "build_topic_readiness_queue.py", "audit_topic_library.py", "audit_saved_theme_sources.py",
    )
    for script in scripts:
        result = subprocess.run([str(python), str(APP_DIR / script)], cwd=APP_DIR,
                                capture_output=True, text=True,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode:
            return False, result.stderr.strip() or result.stdout.strip() or f"{script} could not finish."
    summary = library_intelligence_summary()
    return True, (f"Library intelligence refreshed: {summary['ready_48']} topics ready for standard books, "
                  f"{summary['ready_100']} ready for Signature Editions, and {summary['needs_expansion']} safely held for expansion.")


def run_library_audit() -> tuple[dict[str, object], list[dict[str, str]]]:
    """Create a dated, non-destructive health snapshot for the reusable library."""
    library = load_master_word_bank()
    topics = library.get("topics", {}) if isinstance(library, dict) else {}
    capacities = library.get("topic_capacities", {}) if isinstance(library, dict) else {}
    review_queue: list[dict[str, str]] = []
    ready_48 = ready_100 = 0
    for topic, values in sorted(topics.items(), key=lambda item: str(item[0]).casefold()):
        clean = {re.sub(r"[^A-Z]", "", str(word).upper()) for word in values if re.sub(r"[^A-Z]", "", str(word).upper())}
        cap = capacities.get(str(topic), {}) if isinstance(capacities, dict) else {}
        if len(clean) >= 48 * 12: ready_48 += 1
        if len(clean) >= SIGNATURE_PUZZLE_TARGET * 12: ready_100 += 1
        flagged = sorted(clean & REVIEW_REQUIRED_TERMS)
        if flagged:
            review_queue.append({"topic": str(topic), "reason": "Possible protected-name term — keep out of automatic books until reviewed.", "examples": ", ".join(flagged[:8])})
        if len(clean) < 48 * 12:
            review_queue.append({"topic": str(topic), "reason": "Not yet large enough for a repeat-free 48-puzzle, 12-word book.", "examples": f"{len(clean)} unique words available; needs {48 * 12 - len(clean)} more."})
        if cap and int(cap.get("unique_words", len(clean))) != len(clean):
            review_queue.append({"topic": str(topic), "reason": "Capacity record is out of date; rebuild the Master Library.", "examples": f"Recorded {cap.get('unique_words')} vs. {len(clean)} words."})
    snapshot: dict[str, object] = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "library_schema": library.get("schema_version", "unknown") if isinstance(library, dict) else "missing",
        "unique_words": int(library.get("total_unique_words", 0)) if isinstance(library, dict) else 0,
        "topic_count": len(topics), "topics_ready_for_48": ready_48,
        "topics_ready_for_100": ready_100, "review_items": len(review_queue),
    }
    try:
        previous = json.loads(LIBRARY_AUDIT_FILE.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        previous = []
    history = previous if isinstance(previous, list) else []
    history.insert(0, snapshot)
    try:
        WORD_BANKS_DIR.mkdir(parents=True, exist_ok=True)
        LIBRARY_AUDIT_FILE.write_text(json.dumps(history[:100], indent=2) + "\n", encoding="utf-8")
        WORD_REVIEW_QUEUE_FILE.write_text(json.dumps({"created": snapshot["time"], "items": review_queue}, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass
    return snapshot, review_queue


def word_bank_balance_notes(words: list[str]) -> list[str]:
    cleaned=BookBlueprintDialog._clean_items(words) if "BookBlueprintDialog" in globals() else list(dict.fromkeys(words))
    long=sum(1 for word in cleaned if len(word)>15); short=sum(1 for word in cleaned if len(word)<3)
    notes=[]
    if long: notes.append(f"{long} very long word(s) may need larger grids.")
    if short: notes.append(f"{short} very short word(s) may be too easy.")
    if len(cleaned)<60: notes.append("Add more words for a deeper 20-word book.")
    return notes or ["Word bank looks balanced for the selected format."]


def title_options(topic: str, count: int, audience: str) -> list[tuple[str,str]]:
    topic=topic.strip() or "Everyday Discovery"; short=topic.replace("Word Search","").strip()
    return [(f"{short} Word Search",f"{count} themed puzzles for {audience.lower()}"),(f"The {short} Word Search Collection",f"Relax, discover, and solve {count} satisfying puzzles"),(f"Discover {short}",f"A themed word search book with {count} puzzles"),(f"{short} Puzzle Journey",f"{count} word searches for calm screen-free fun"),(f"The Big Book of {short} Word Searches",f"{count} engaging puzzles with solutions")]


def save_competitor_note(niche: str, note: str) -> None:
    try: data=json.loads(COMPETITOR_NOTES_FILE.read_text(encoding="utf-8-sig"))
    except (OSError,json.JSONDecodeError): data=[]
    if not isinstance(data,list): data=[]
    data.insert(0,{"time":datetime.now().isoformat(timespec="seconds"),"niche":niche,"note":note})
    COMPETITOR_NOTES_FILE.write_text(json.dumps(data[:300],indent=2,ensure_ascii=False)+"\n",encoding="utf-8")


def save_niche_cover_memory(niche: str, settings: dict[str,str]) -> None:
    try:data=json.loads(NICHE_COVER_MEMORY_FILE.read_text(encoding="utf-8-sig"))
    except (OSError,json.JSONDecodeError):data={}
    if not isinstance(data,dict):data={}
    data[niche]={"palette":settings.get("palette","nature"),"style":settings.get("style","classic")}
    NICHE_COVER_MEMORY_FILE.write_text(json.dumps(data,indent=2)+"\n",encoding="utf-8")


def load_cover_memory(identity: str) -> dict:
    try:
        data = json.loads(NICHE_COVER_MEMORY_FILE.read_text(encoding="utf-8-sig"))
        return dict(data.get(identity) or {}) if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _read_art_records(path: Path) -> list[dict]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _write_art_records(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records[:500], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def art_quality_report(path: Path | None) -> tuple[int, str]:
    """Return a simple buyer-facing artwork score before it reaches a cover."""
    if not path or not path.exists():
        return 0, "No picture selected yet."
    try:
        with Image.open(path) as image:
            width, height = image.size
            tiny = min(width, height) < 900
            sample = image.convert("L").resize((80, 80))
            values = list(sample.getdata())
    except (OSError, ValueError):
        return 25, "This picture could not be read reliably. Choose another one."
    contrast = max(values) - min(values) if values else 0
    score = 100
    notes: list[str] = []
    if tiny:
        score -= 35; notes.append("small image")
    if contrast < 55:
        score -= 18; notes.append("low contrast")
    if width / max(1, height) > 2.4 or height / max(1, width) > 2.8:
        score -= 8; notes.append("unusual shape")
    if score >= 90: return score, "Excellent cover-picture quality."
    return max(score, 0), "Usable, but " + ", ".join(notes) + ". The app will protect the title automatically."


def nearest_cover_palette(path: Path | None, fallback: str = "nature") -> tuple[str, str]:
    """Match a real picture to an existing proven print palette, not a risky custom color."""
    if not path or not path.exists():
        return fallback, "Keeping this theme’s recommended colors."
    try:
        with Image.open(path) as image:
            image = image.convert("RGB").resize((40, 40))
            pixels = list(image.getdata())
            # Ignore near-white background pixels common in transparent clipart conversions.
            colored = [pixel for pixel in pixels if max(pixel) - min(pixel) > 22 and sum(pixel) < 710] or pixels
            average = tuple(sum(pixel[i] for pixel in colored) / len(colored) for i in range(3))
    except (OSError, ValueError):
        return fallback, "Keeping this theme’s recommended colors."
    def distance(palette: dict) -> float:
        accent, hi = palette["accent"], palette["hi"]
        return min(sum((average[i] - color[i]) ** 2 for i in range(3)) for color in (accent, hi))
    name = min(COVER_PALETTES, key=lambda item: distance(COVER_PALETTES[item]))
    return name, f"Matched the cover colors to your picture: {name.replace('-', ' ').title()}."


def save_art_favorite(record: dict[str, object]) -> None:
    rows = [item for item in _read_art_records(ART_FAVORITES_FILE) if item.get("local_file") != record.get("local_file")]
    rows.insert(0, dict(record)); _write_art_records(ART_FAVORITES_FILE, rows)


def record_cover_art_use(path: Path, title: str, theme: str) -> None:
    rows = _read_art_records(ART_USAGE_HISTORY_FILE)
    rows.insert(0, {"local_file": str(path), "title": title, "theme": theme, "used_at": datetime.now().isoformat(timespec="seconds")})
    _write_art_records(ART_USAGE_HISTORY_FILE, rows)
    # Approved project backgrounds additionally keep a usage trail in their
    # own rights/provenance ledger. Unknown or external art is never promoted
    # by this call.
    BackgroundAssetIndex().record_use(path, title=title, theme=theme)


def art_use_note(path: Path | None) -> str:
    if not path: return ""
    uses = [item for item in _read_art_records(ART_USAGE_HISTORY_FILE) if str(item.get("local_file")) == str(path)]
    return "" if not uses else f"This picture has already been used on {len(uses)} book(s)."


def load_background_photo_library() -> list[dict[str, object]]:
    # The generated-art index is the production authority. It deliberately
    # fails closed: assets without a reconciled, project-generation provenance
    # record cannot be selected automatically.
    index = BackgroundAssetIndex()
    index.ensure_provenance_audited()
    grouped: dict[str, dict[str, object]] = {}
    for asset in index.assets():
        if not index.production_selectable(asset):
            continue
        if not (APP_DIR / str(asset.get("path") or "")).exists():
            continue
        name = str(asset.get("name") or "Approved background")
        entry = grouped.setdefault(name, {"name": name, "files": [], "focus": asset.get("focus", "center"), "palette": asset.get("palette", ""), "match_terms": asset.get("topics", [])})
        entry["files"].append(asset.get("path"))
    return list(grouped.values())


def _school_cover_level(haystack: str) -> str:
    """Identify the education level so school covers never cross over."""
    if any(term in haystack for term in ("grade 5", "grade school", "elementary school", "elementary vocabulary")):
        return "Elementary"
    if any(term in haystack for term in ("middle school", "grade 6", "grade 7", "grade 8", "middle vocabulary")):
        return "Middle"
    if any(term in haystack for term in ("high school", "grade 9", "grade 10", "grade 11", "grade 12", "high school vocabulary")):
        return "High"
    return ""


def recommend_background_photo(data: dict) -> dict[str, object] | None:
    """Choose a stable, topic-matched reusable photo background.

    A library entry may offer several variations.  The selected variation is
    deterministic for a given book title, which keeps a regenerated book
    visually consistent while allowing different titles to use different art.
    """
    haystack = " ".join(str(data.get(key) or "") for key in ("title", "subtitle", "detected_topic", "series")).casefold()
    stable_number = sum(ord(character) for character in haystack) or 1
    request = request_from_mapping(
        str(data.get("_creation_route") or "Word Search"), data,
        theme_path=str(data.get("_theme_path") or ""), selection_seed=stable_number,
    )
    decision = select_cover_asset(request)
    if not decision.asset:
        return None
    return {**decision.asset, "routing_diagnostics": decision.diagnostics()}


def background_photo_choices(data: dict) -> list[dict[str, object]]:
    """Return every usable best-match photo choice for the cover picker."""
    approved = BackgroundAssetIndex().production_choices(data)
    if not approved:
        return []
    best = max(int(item.get("match_score") or 0) for item in approved)
    return [dict(item) for item in approved if int(item.get("match_score") or 0) == best]


def photo_choice_palette(choice: dict[str, object], fallback: str = "nature") -> str:
    """Use the art director's palette pairing, with image analysis as a fallback."""
    requested = str(choice.get("palette") or "")
    if requested in CoverCreatorDialog.PALETTES:
        return requested
    path = APP_DIR / str(choice.get("file") or "")
    palette, _note = nearest_cover_palette(path if path.exists() else None, fallback)
    return palette


def all_book_theme_files() -> list[Path]:
    files: list[Path] = []
    for path in THEMES_DIR.rglob("*.json"):
        if any(folder in path.parents for folder in (USED_THEMES_DIR, ARCHIVE_THEMES_DIR, RESEARCH_THEMES_DIR, DRAFT_THEMES_DIR)):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            if bool(data.get("draft")):
                continue
            if isinstance(data.get("puzzles"), list):
                files.append(path)
        except (OSError, json.JSONDecodeError):
            continue
    return sorted(files, key=lambda item: item.name.lower())


TOPIC_PROFILES = {
    "Space and Astronomy": ("midnight-gold", "halo", ("SPACE", "ASTRONOMY", "PLANET", "ORBIT", "GALAXY", "STAR", "COMET", "ASTEROID", "TELESCOPE", "LUNAR")),
    "Dog Breeds": ("animals", "playful", ("DOG", "PUPPY", "RETRIEVER", "POODLE", "BEAGLE", "CANINE", "TERRIER", "HUSKY", "BULLDOG")),
    "Cat Lover": ("candy-pop", "playful", ("CAT", "KITTEN", "FELINE", "WHISKER", "PURR", "TABBY", "SIAMESE", "CATNIP")),
    "Bible and Faith": ("bible", "classic", ("BIBLE", "PSALM", "SCRIPTURE", "GOSPEL", "PRAYER", "JESUS", "APOSTLE", "FAITH", "GRACE")),
    "National Parks": ("nature", "gallery", ("PARK", "RANGER", "TRAIL", "WILDLIFE", "CANYON", "MOUNTAIN", "FOREST", "GLACIER", "CAMPGROUND")),
    "Travel and Geography": ("coastal-blue", "stripe", ("COUNTRY", "CAPITAL", "AIRPORT", "PASSPORT", "JOURNEY", "ROAD", "MAP", "CITY", "TRAVEL")),
    "Gardening": ("spring-meadow", "gallery", ("GARDEN", "FLOWER", "SEED", "SOIL", "HARVEST", "TROWEL", "PLANT", "BLOOM", "HERB")),
    "Baking and Food": ("food", "ticket", ("BAKE", "FLOUR", "SUGAR", "OVEN", "RECIPE", "COOKIE", "CAKE", "SPICE", "KITCHEN")),
    "Ocean Life": ("ocean-life", "stripe", ("OCEAN", "WHALE", "DOLPHIN", "SHARK", "CORAL", "FISH", "SEAL", "TURTLE", "MARINE")),
    "Holidays": ("holly-jolly", "playful", ("CHRISTMAS", "HALLOWEEN", "PUMPKIN", "SANTA", "EASTER", "THANKSGIVING", "HOLIDAY", "ORNAMENT")),
    "Sports and Hobbies": ("sports", "bold", ("GOLF", "FISHING", "QUILT", "SEWING", "TEAM", "SPORT", "FAIRWAY", "TACKLE", "CRAFT")),
    "Mindfulness": ("lavender-pop", "halo", ("CALM", "MINDFUL", "GRATITUDE", "PEACE", "BREATHE", "WELLNESS", "BALANCE", "JOY")),
    "Cocktail Hour, Nightlife & Social Club": ("midnight-gold", "bold", ("COCKTAIL", "MARTINI", "LOUNGE", "NIGHTLIFE", "MIXOLOGY", "ROOFTOP", "HAPPY HOUR", "SOCIAL CLUB")),
    "Cannabis Culture, Chill & Legal Lifestyle": ("forest-cabin", "gallery", ("CANNABIS", "CBD", "HEMP", "TERPENE", "DISPENSARY", "CHILL", "COZY", "RELAXATION")),
    "Date Night, Romance & Relationship Fun": ("royal-plum", "halo", ("DATE NIGHT", "ROMANCE", "ANNIVERSARY", "CANDLELIGHT", "CONNECTION", "COUPLES", "LOVE LETTER", "GETAWAY")),
    "Responsible Firearms, Range & Outdoor Heritage": ("graphite-copper", "gallery", ("RANGE SAFETY", "RESPONSIBLE OWNERSHIP", "LOCKED STORAGE", "RANGE OFFICER", "OUTDOOR HERITAGE", "EAR PROTECTION", "SAFETY FIRST")),
}

COVER_LAYOUT_GUIDANCE = {
    "Gallery Frame": "Best for classic, premium-looking books and longer titles.",
    "Color Block": "Best for bold, simple titles that need strong thumbnail contrast.",
    "Halo Spotlight": "Best for calm, nature, and mindfulness collections.",
    "Ticket Stub": "Best for playful hobbies, travel, and retro themes.",
    "Diagonal Stripe": "Best for energetic topics with short, punchy titles.",
    "Retro Pop": "Best for colorful nostalgia, teen, and fun seasonal books.",
    "Playful Illustrated": "Best for friendly, illustrated books with broad buyer appeal.",
    "Photo Hero": "Best when you have one strong licensed image with room for readable text.",
}


def compatible_cover_choice(data: dict, title: str) -> tuple[str, str]:
    """Pick a deterministic, on-topic palette/layout pairing for the current book."""
    recommendation = recommend_theme_from_words(data.get("puzzles", []))
    palettes = ("nature", "coastal-blue", "royal-plum", "forest-cabin", "tropical-pop", "candy-pop", "midnight-gold", "spring-meadow", "autumn-harvest", "holly-jolly")
    styles = tuple(PublishReadyDialog.STYLE_MAP) if "PublishReadyDialog" in globals() else tuple(COVER_LAYOUT_GUIDANCE)
    chooser = random.Random(f"{title}|{len(data.get('puzzles', []))}|cover")
    preferred_palette = str(data.get("recommended_palette") or data.get("palette") or recommendation["palette"])
    preferred_style_value = str(data.get("recommended_cover_style") or data.get("cover_style") or recommendation["style"])
    preferred_style = next((label for label, value in PublishReadyDialog.STYLE_MAP.items() if value == preferred_style_value), None) if "PublishReadyDialog" in globals() else None
    palette = preferred_palette if preferred_palette in palettes and chooser.random() < .7 else chooser.choice(palettes)
    style = preferred_style if preferred_style and chooser.random() < .7 else chooser.choice(styles)
    return palette, style


def recommend_theme_from_words(puzzles: list[dict], topic_hint: str = "") -> dict[str, object]:
    """Give a transparent local recommendation from the word-bank vocabulary."""
    words = [str(word).upper() for puzzle in puzzles for word in puzzle.get("words", [])]
    joined = " ".join(words)
    scores = {name: sum(1 for keyword in keywords if keyword in joined) for name, (_palette, _style, keywords) in TOPIC_PROFILES.items()}
    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    hint_tokens = {token for token in re.findall(r"[a-z0-9]+", topic_hint.casefold()) if token not in {"and", "the", "for", "of"}}
    hinted = []
    for name in TOPIC_PROFILES:
        name_tokens = {token for token in re.findall(r"[a-z0-9]+", name.casefold()) if token not in {"and", "the", "for", "of"}}
        overlap = len(hint_tokens & name_tokens)
        if overlap:
            hinted.append((overlap / max(1, len(hint_tokens)), overlap, name))
    hinted.sort(reverse=True)
    if hinted and hinted[0][0] >= .5:
        topic = hinted[0][2]
        score = max(2, scores.get(topic, 0))
    else:
        topic, score = ordered[0] if ordered else ("General Interest", 0)
    palette, style, _keywords = TOPIC_PROFILES.get(topic, ("nature", "classic", ()))
    average = (sum(len(puzzle.get("words", [])) for puzzle in puzzles) / len(puzzles)) if puzzles else 0
    notes: list[str] = []
    if score < 2:
        topic, palette, style = "General Interest", "nature", "classic"
        notes.append("No strong single topic was detected; give the book a clear niche title before publishing.")
    elif len(ordered) > 1 and ordered[1][1] >= max(2, score - 1):
        notes.append(f"This mixes {topic} with {ordered[1][0]}; consider presenting it as a deliberate mixed-theme collection.")
    if average < 8:
        notes.append("Several puzzles are light on words; aim for 12 words per puzzle for your large-print format.")
    elif average > 20:
        notes.append("This is a denser collection; the generator will use larger grids instead of calling it Large Print.")
    return {"topic": topic, "palette": palette, "style": style, "average_words": average, "notes": notes, "score": score}


def clipart_search_terms(data: dict) -> str:
    """Build a useful, specific artwork search from the actual word bank."""
    puzzles = data.get("puzzles", []) if isinstance(data, dict) else []
    recommendation = recommend_theme_from_words(puzzles)
    topic = str(data.get("detected_topic") or recommendation["topic"])
    generic = {"WORDSEARCH", "PUZZLETIME", "RELAX", "DISCOVER", "BRAINGAME", "FAVORITE", "HOBBY", "COLLECTION", "LEISURE", "WEEKEND", "ENJOY", "SOLVE", "FIND", "LETTER", "CHALLENGE", "INTEREST", "MEMORY", "SMILE", "QUIETTIME", "FREETIME"}
    words = []
    for puzzle in puzzles:
        for word in puzzle.get("words", []):
            cleaned = re.sub(r"[^A-Z]", "", str(word).upper())
            if cleaned and cleaned not in generic and cleaned not in words:
                words.append(cleaned)
    details = " ".join(words[:3]).title()
    return f"{topic} {details} illustration clipart transparent background".strip()


def openclipart_query(data: dict) -> str:
    """Turn a long SEO-style art note into a short query that image search understands."""
    topic = str(data.get("detected_topic") or recommend_theme_from_words(data.get("puzzles", [])) ["topic"]).strip()
    words = [re.sub(r"[^A-Z]", "", str(word).upper()) for puzzle in data.get("puzzles", []) for word in puzzle.get("words", [])]
    words = [word for word in words if len(word) >= 3 and word not in {"WORDSEARCH", "PUZZLE", "PUZZLES", "RELAX", "DISCOVER"}]
    simple_topic = " ".join(topic.split()[:2])
    return simple_topic or (words[0].lower() if words else "word search")


def suggest_art_plan(path: Path | None) -> tuple[str, str]:
    """Choose the safest crop focus for the current Photo Hero renderer."""
    if not path or not path.exists():
        return "center", "Choose an OpenClipart image and I will suggest its crop focus automatically."
    try:
        with Image.open(path) as image:
            ratio = image.width / max(1, image.height)
    except (OSError, ValueError):
        return "center", "Use center focus; the image shape could not be read."
    if ratio < .82:
        return "top", "Portrait artwork: use top focus so the lower portion can support the badge and author."
    if ratio > 1.35:
        return "center", "Wide artwork: use center focus; Photo Hero will crop the outer sides for the book shape."
    return "center", "Balanced artwork: use center focus for the most reliable title-and-image balance."


def enrich_theme_intelligence(data: dict) -> bool:
    """Add missing Smart Theme metadata without replacing a saved design choice."""
    puzzles = data.get("puzzles", [])
    if not isinstance(puzzles, list):
        return False
    recommendation = recommend_theme_from_words(puzzles)
    changed = False
    defaults = {
        "detected_topic": recommendation["topic"],
        "recommended_palette": recommendation["palette"],
        "recommended_cover_style": recommendation["style"],
    }
    for key, value in defaults.items():
        if not data.get(key):
            data[key] = value
            changed = True
    if not data.get("palette"):
        data["palette"] = recommendation["palette"]
        changed = True
    if not data.get("cover_style"):
        data["cover_style"] = recommendation["style"]
        changed = True
    search_terms = clipart_search_terms(data)
    if data.get("clipart_search_terms") != search_terms:
        data["clipart_search_terms"] = search_terms
        changed = True
    return changed


def refresh_all_theme_intelligence() -> tuple[int, int]:
    """Read every usable JSON theme, enriching only missing recommendation data."""
    scanned = changed = 0
    for path in all_book_theme_files():
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            scanned += 1
            if enrich_theme_intelligence(data):
                path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                changed += 1
        except (OSError, json.JSONDecodeError):
            continue
    return scanned, changed


def load_production_presets() -> list[dict[str, str]]:
    try:
        presets = json.loads(PRESETS_FILE.read_text(encoding="utf-8-sig"))
        return [preset for preset in presets if isinstance(preset, dict) and preset.get("name")]
    except (OSError, json.JSONDecodeError):
        return []


def save_production_preset(preset: dict[str, str]) -> None:
    presets = [item for item in load_production_presets() if item["name"].lower() != preset["name"].lower()]
    presets.append(preset)
    PRESETS_FILE.write_text(json.dumps(presets, indent=2) + "\n", encoding="utf-8")


def automatic_theme_backup(reason: str) -> Path | None:
    """Keep one recoverable safety snapshot before meaningful theme-library edits."""
    folder = OUTPUT_DIR / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    recent = sorted(folder.glob("automatic_theme_backup_*.zip"), key=lambda item: item.stat().st_mtime, reverse=True)
    if recent and (time.time() - recent[0].stat().st_mtime) < 300:
        return recent[0]
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive = shutil.make_archive(str(folder / f"automatic_theme_backup_{stamp}"), "zip", APP_DIR, "themes")
    marker = folder / f"automatic_theme_backup_{stamp}.txt"
    marker.write_text(f"Created automatically before: {reason}\n", encoding="utf-8")
    return Path(archive)


def create_production_lock() -> tuple[Path, Path]:
    """Freeze the practical production baseline without touching live files."""
    folder = OUTPUT_DIR / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive = folder / f"production_lock_{stamp}.zip"
    include_roots = ("themes", "word_banks", "cover_assets")
    include_files = {"word_search_creator.py", "wordsearch.py", "cover.py", "wrap_cover.py", "preflight.py", "project_checks.py", "VERSION.txt", "CHANGELOG.md", "production_presets.json", "brand_kit.json"}
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as package:
        for name in include_roots:
            root = APP_DIR / name
            if root.exists():
                for item in root.rglob("*"):
                    if item.is_file():
                        package.write(item, item.relative_to(APP_DIR))
        for name in include_files:
            item = APP_DIR / name
            if item.is_file():
                package.write(item, item.relative_to(APP_DIR))
    lock = {"created": datetime.now().isoformat(timespec="seconds"), "version": APP_VERSION,
            "archive": str(archive), "purpose": "Stable baseline before production", "launch_batch_size": 5}
    PRODUCTION_LOCK_FILE.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
    LAUNCH_BATCH_FILE.write_text(json.dumps({"created": lock["created"], "target": 5, "books": []}, indent=2) + "\n", encoding="utf-8")
    tracker = folder / "FIRST_FIVE_BOOKS_REVIEW.txt"
    tracker.write_text("FIRST FIVE BOOKS - PRODUCTION REVIEW\n\nFor each package, complete these before expanding production:\n[ ] KDP Print Previewer has no unresolved issue\n[ ] Amazon detail page title, subtitle, author, price, and cover look correct\n[ ] Description, keywords, and categories accurately match the interior\n[ ] Ordered proof or buyer-view review completed\n\nBooks are added automatically as packages are created.\n", encoding="utf-8")
    return archive, tracker


def automatic_production_snapshot() -> Path:
    """Capture reusable production inputs before a queue begins.

    This protects themes, word banks, cover assets, presets, and the engine
    together.  It is deliberately separate from package outputs and reuses a
    very recent snapshot so repeated clicks do not create needless archives.
    """
    folder = OUTPUT_DIR / "backups"
    recent = sorted(folder.glob("production_lock_*.zip"), key=lambda item: item.stat().st_mtime, reverse=True) if folder.exists() else []
    if recent and (time.time() - recent[0].stat().st_mtime) < 300:
        return recent[0]
    archive, _tracker = create_production_lock()
    return archive


def record_launch_batch_package(title: str, folder: Path) -> None:
    """Add only the first five packages after a production lock to the proof list."""
    try:
        tracker = json.loads(LAUNCH_BATCH_FILE.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return
    books = tracker.get("books") if isinstance(tracker, dict) else None
    if not isinstance(books, list) or len(books) >= int(tracker.get("target", 5)):
        return
    if any(str(item.get("package")) == str(folder) for item in books if isinstance(item, dict)):
        return
    books.append({"title": title, "package": str(folder), "created": datetime.now().isoformat(timespec="seconds"),
                  "kdp_previewer": False, "detail_page": False, "buyer_review": False})
    tracker["books"] = books
    LAUNCH_BATCH_FILE.write_text(json.dumps(tracker, indent=2) + "\n", encoding="utf-8")


def production_stop_errors(path: Path, seed: int, settings: dict[str, str]) -> tuple[list[str], list[str], list[str]]:
    """The non-negotiable checks used immediately before a package is made."""
    errors, warnings, notes = quality_gate(path, seed)
    title, subtitle, author = (settings.get("title", "").strip(), settings.get("subtitle", "").strip(), settings.get("author", "").strip())
    if not title or not subtitle or not author:
        errors.append("Production stop: title, subtitle, and author must all be filled in before creating a package.")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return errors, warnings, notes
    edition = data.get("signature_edition") if isinstance(data.get("signature_edition"), dict) else {}
    if edition.get("candidate"):
        reason = str(edition.get("reason") or "This source still needs enough topic-linked words for 100 puzzles.")
        errors.append(f"Production stop: Signature candidate is not ready yet. {reason}")
    words = [re.sub(r"[^A-Z]", "", str(word).upper()) for puzzle in data.get("puzzles", []) if isinstance(puzzle, dict) for word in puzzle.get("words", [])]
    words = [word for word in words if word]
    if not data.get("no_repeat_words") or len(words) != len(set(words)):
        errors.append("Production stop: this book must have the no-repeated-words promise and no repeated puzzle words.")
    direct_fit, direct_rule = direct_topic_fit_report(data)
    if direct_fit is not None and direct_fit < 50:
        errors.append(f"Production stop: topic fit is {direct_fit}% for this {direct_rule.title()} book. Strengthen the word bank before packaging it.")
    elif direct_fit is not None and direct_fit < 70:
        warnings.append(f"Production review: topic fit is {direct_fit}% for this {direct_rule.title()} book. The package can be made, but review the word bank before publishing.")
    style = settings.get("style", "")
    if style == "photo" and not Path(settings.get("art", "")).is_file():
        errors.append("Production stop: Photo Hero needs a valid local cover picture.")
    package_data = package_data_from_settings(data, settings)
    listing = listing_kit_text(package_data)
    if len(kdp_keyword_phrases(package_data)) != 7 or "COPY-READY DESCRIPTION — PASTE DIRECTLY INTO KDP" not in listing:
        errors.append("Production stop: the KDP listing kit is incomplete. Re-run the book setup.")
    metadata_errors, metadata_warnings = kdp_metadata_compliance_report(package_data)
    errors.extend(f"Production stop: KDP listing detail — {item}" for item in metadata_errors)
    warnings.extend(f"KDP listing review: {item}" for item in metadata_warnings)
    errors, warnings = list(dict.fromkeys(errors)), list(dict.fromkeys(warnings))
    try:
        record_theme_health(THEME_HEALTH_CACHE_FILE, path, errors, warnings)
    except OSError:
        pass
    return errors, warnings, notes


def is_signature_edition(data: dict) -> bool:
    edition = data.get("signature_edition") if isinstance(data, dict) else None
    # Older files often stored design notes with Signature enabled even when
    # they only had 48 or 60 puzzles.  Preserve those files, but never present
    # a shorter collection to a buyer as the premium 100-puzzle edition.
    return bool(edition.get("enabled")) and len(data.get("puzzles", [])) >= SIGNATURE_PUZZLE_TARGET if isinstance(edition, dict) else False


def signature_requested(settings: dict[str, object] | None) -> bool:
    """Return the explicit package-time Signature Edition choice.

    A saved theme may contain Signature Edition design notes.  Those notes do
    not turn a standard package into a Signature Edition on their own.
    """
    value = (settings or {}).get("signature_edition", False)
    return value is True or (isinstance(value, str) and value.strip().casefold() in {"1", "true", "yes", "on"})


def theme_defaults_to_signature(path: Path, data: dict) -> bool:
    """Recognize intentionally named Signature Edition theme files only.

    Earlier versions saved a Signature configuration on many standard themes,
    so its presence alone is not a safe default for a new package.
    """
    title = str(data.get("title") or "").casefold()
    edition = data.get("signature_edition") if isinstance(data, dict) else None
    return bool(isinstance(edition, dict) and edition.get("enabled")) and ("signature edition" in title or path.stem.casefold().startswith("signature_"))


SIGNATURE_PUZZLE_TARGET = 100


def signature_puzzle_target(data: dict) -> int:
    """Return the saved target for newly created Signature Editions.

    Older themes may contain optional Signature-page design notes.  They remain
    ordinary books unless the user explicitly chooses Signature packaging.
    """
    return SIGNATURE_PUZZLE_TARGET if is_signature_edition(data) else 48


def recommended_us_paperback_price(page_count: int, signature: bool = False) -> tuple[float, float]:
    """Conservative US price guide; KDP alone calculates the final print royalty."""
    # Amazon.com moves from the 50% to 60% paperback royalty tier at $9.99.
    # These are pricing suggestions only; KDP's final calculator owns print cost.
    if page_count <= 110:
        price = 9.99
    elif page_count <= 160:
        price = 10.99
    elif page_count <= 220:
        price = 11.99
    elif page_count <= 300:
        price = 12.99
    else:
        price = 13.99
    if signature:
        # A Signature book is now a 100-puzzle collection with bonus pages,
        # not merely the same book with a different label.
        price += 2.00 if page_count >= 150 else 1.00
    return price, 0.0


def book_format_label(data: dict) -> str:
    """Only use 'Large Print' when every puzzle keeps the 15 x 15 grid."""
    puzzles = data.get("puzzles", []) if isinstance(data, dict) else []
    largest_word_bank = max((len(item.get("words", [])) for item in puzzles if isinstance(item, dict)), default=0)
    return "LARGE PRINT PUZZLES" if largest_word_bank <= 12 else "WORD SEARCH PUZZLES"


def book_description(count: int, data: dict) -> str:
    topic = str(data.get("detected_topic") or data.get("series") or "your favorite topic").strip()
    no_repeat = " Every puzzle uses a different word list across the book." if data.get("no_repeat_words") else ""
    bonus = " Includes Signature Edition bonus pages." if is_signature_edition(data) else ""
    details = " Includes a collection guide and puzzle-notes page." if detail_page_count(data) else ""
    if book_format_label(data) == "LARGE PRINT PUZZLES":
        return (f"Relax with {count} large-print {topic} word search puzzles. "
                "Clear, easy-to-read grids and complete solutions make this a satisfying screen-free activity." + no_repeat + details + bonus)
    return (f"Relax with {count} themed word search puzzles about {topic}. "
            "Clear grids and complete solutions make this a satisfying screen-free activity." + no_repeat + details + bonus)


def topic_back_cover_copy(count: int, data: dict) -> str:
    """Create warm, topic-specific back-cover copy without generic filler."""
    topic = str(data.get("detected_topic") or data.get("series") or data.get("title") or "this collection").strip()
    title = str(data.get("title") or topic).strip()
    words = [str(word).replace("_", " ").title() for puzzle in data.get("puzzles", []) if isinstance(puzzle, dict) for word in puzzle.get("words", [])]
    examples = ", ".join(list(dict.fromkeys(words))[:4]) or topic
    topic_key = f"{topic} {title}".casefold()
    notes = [
        (("bible", "faith", "scripture"), "From parables to Psalms, Bible vocabulary carries stories, places, and ideas that have been shared for generations."),
        (("national park", "park", "trail", "outdoor"), "National parks protect remarkable landscapes, wildlife habitats, and places of discovery for future generations."),
        (("pet", "cat", "dog", "animal"), "Pets bring companionship, personality, and plenty of memorable everyday moments to a puzzle collection."),
        (("nostalgia", "decade", "1950", "1960", "1970", "1980", "1990", "2000"), "A favorite decade can bring back the music, objects, places, and everyday moments that make a generation memorable."),
        (("space", "astronomy", "planet"), "A light-year measures distance, not time—one reason space is full of astonishing scale."),
        (("bird",), "Birds use remarkable clues, including the Sun, stars, and Earth’s magnetic field, to help them navigate."),
        (("weather", "climate", "storm"), "A rainbow appears when sunlight enters, reflects inside, and leaves countless tiny water droplets."),
        (("american history", "u.s. history", "united states"), "The National Archives preserves the Declaration of Independence, Constitution, and Bill of Rights."),
        (("car", "truck", "vehicle", "road trip"), "Every road trip blends design, motion, and memory—making vehicles a great puzzle subject for every kind of enthusiast."),
        (("ocean", "marine", "coast", "coral", "tide"), "The ocean covers more than two-thirds of Earth’s surface and is home to an extraordinary variety of life."),
        (("garden", "herb", "homestead"), "Gardens connect seasons, patience, and discovery—there is always another plant, tool, or harvest to learn about."),
        (("christmas", "winter"), "Seasonal traditions, cozy weather, and familiar symbols make winter puzzles especially satisfying to share."),
    ]
    discovery = next((note for keys, note in notes if any(key in topic_key for key in keys)),
                     f"Explore the details that make {topic} memorable, one satisfying word at a time.")
    format_line = "large-print" if book_format_label(data) == "LARGE PRINT PUZZLES" else "themed"
    no_repeat = " Every puzzle uses a fresh word list—no repeated words across the book." if data.get("no_repeat_words") else ""
    return (f"INSIDE THIS BOOK\n\n"
            f"Take a relaxing {format_line} journey through {topic}. This collection includes {count} carefully selected word search puzzles with clear grids and complete solutions. Expect to discover words such as {examples}.{no_repeat}\n\n"
            f"DISCOVERY NOTE\n\n{discovery}\n\n"
            f"MADE FOR RELAXING\n\nA thoughtful screen-free activity for quiet moments, travel, gifting, and anyone who enjoys the world of {topic}.")


def detail_page_count(data: dict) -> int:
    """Return the automatic non-puzzle pages supplied by the interior engine."""
    config = data.get("detail_pages", {}) if isinstance(data, dict) else {}
    return 0 if isinstance(config, dict) and config.get("enabled") is False else 2


def estimated_page_count(data: dict) -> int:
    """Match the current interior structure without generating a temporary PDF."""
    puzzles = data.get("puzzles", []) if isinstance(data, dict) else []
    count = len(puzzles)
    signature_pages_count = 0
    signature = data.get("signature_edition", {})
    if is_signature_edition(data):
        signature_pages_count = math.ceil(count / 60) + 1
        if signature.get("fact_cards"):
            signature_pages_count += 1
    # 3 front-matter pages + the themed welcome page + automatic detail pages,
    # optional interior chapter dividers, then puzzles, solutions, and back
    # matter.  Keep this in sync with wordsearch.py so the cover spine always
    # reflects the exact PDF that will be produced.
    chapter_dividers = puzzle_engine.interior_divider_page_count(data, puzzles)
    raw_count = 4 + detail_page_count(data) + signature_pages_count + chapter_dividers + count + 1 + math.ceil(count / 2) + 2 + (1 if data.get("also_from") else 0)
    # The engine intentionally adds a final blank page when necessary so the
    # exact package count and the KDP cover-spine calculation always agree.
    return raw_count if raw_count % 2 == 0 else raw_count + 1


def content_quality_score(data: dict) -> tuple[int, str, list[str], list[str]]:
    """Fast, buyer-focused score with practical fixes; exact placement is checked separately."""
    puzzles = data.get("puzzles", []) if isinstance(data, dict) else []
    strengths: list[str] = []
    improvements: list[str] = []
    score = 0
    required_puzzles = signature_puzzle_target(data)
    if len(puzzles) >= required_puzzles:
        score += 25; strengths.append(f"Complete collection: {len(puzzles)} puzzles.")
    else:
        score += min(15, len(puzzles) // 3)
        edition_name = "Signature Edition" if required_puzzles == SIGNATURE_PUZZLE_TARGET else "book"
        improvements.append(f"Add puzzles until this {edition_name} reaches {required_puzzles} puzzles (it has {len(puzzles)} now).")
    word_counts = [len(item.get("words", [])) for item in puzzles if isinstance(item, dict)]
    if word_counts and min(word_counts) >= 12:
        score += 15; strengths.append("Every puzzle has a full word list.")
    else:
        improvements.append("Fill every puzzle to at least 12 words before creating the book.")
    cleaned_words = [re.sub(r"[^A-Z]", "", str(word).upper()) for item in puzzles if isinstance(item, dict) for word in item.get("words", [])]
    cleaned_words = [word for word in cleaned_words if word]
    if cleaned_words and len(cleaned_words) == len(set(cleaned_words)):
        score += 20; strengths.append("No repeated words across this book.")
    else:
        repeated = max(0, len(cleaned_words) - len(set(cleaned_words)))
        improvements.append(f"Replace {repeated} repeated word(s) so every puzzle feels fresh.")
    readiness = data.get("production_readiness", {})
    if isinstance(readiness, dict) and readiness.get("production_ready"):
        score += 10; strengths.append("Theme is marked ready for production.")
    elif len(puzzles) >= 48:
        score += 6
    title = str(data.get("title") or "").strip(); subtitle = str(data.get("subtitle") or "").strip()
    if 4 <= len(title) <= 60 and subtitle:
        score += 10; strengths.append("Title and subtitle are ready for a buyer-facing cover.")
    else:
        improvements.append("Use a clear title and a short subtitle that explains the book benefit.")
    if detail_page_count(data):
        score += 10; strengths.append("Includes a collection guide and reader notes page.")
    if is_signature_edition(data):
        score += 5; strengths.append("Signature Edition extras add collector value.")
    if str(data.get("detected_topic") or data.get("series") or "").strip():
        score += 5
    else:
        improvements.append("Set a clear topic or series so the listing and cover can describe the book accurately.")
    direct_fit, direct_rule = direct_topic_fit_report(data)
    if direct_fit is not None:
        if direct_fit >= 70:
            strengths.append(f"Topic-fit check: {direct_fit}% of puzzle words match the {direct_rule.title()} promise.")
        else:
            score = max(0, score - 20)
            improvements.append(f"Topic-fit check is only {direct_fit}% for this {direct_rule.title()} book. Replace off-topic words before publishing.")
    score = min(100, score)
    label = "Excellent buyer-ready foundation" if score >= 90 else ("Strong foundation" if score >= 75 else ("Good start" if score >= 55 else "Needs more content"))
    if not improvements:
        improvements.append("Run the exact Book Quality Check before publishing to verify every word placement and compare the final files in KDP Print Previewer.")
    return score, label, strengths, improvements


def package_data_from_settings(theme_data: dict, settings: dict[str, object]) -> dict:
    """Make every final document describe the exact book just created."""
    data = dict(theme_data)
    for key in ("title", "subtitle", "author", "palette"):
        if settings.get(key) is not None:
            data[key] = settings[key]
    if settings.get("badge") is not None:
        data["cover_badge"] = settings["badge"]
    if settings.get("style") is not None:
        data["cover_style"] = settings["style"]
    prior = data.get("signature_edition") if isinstance(data.get("signature_edition"), dict) else {}
    # Always write the explicit choice, including False, so every generated
    # listing, price, wrap blurb, and page estimate matches the package.
    data["signature_edition"] = {**prior, "enabled": signature_requested(settings)}
    return data


def package_blurb(theme_data: dict, package_data: dict) -> str:
    """Keep a saved custom blurb, but prevent it from carrying an old title."""
    blurb = str(theme_data.get("back_cover_blurb") or "").strip()
    old_title = str(theme_data.get("title") or "").strip()
    new_title = str(package_data.get("title") or "").strip()
    if blurb and old_title and new_title and old_title.casefold() != new_title.casefold():
        blurb = re.sub(re.escape(old_title), new_title, blurb, flags=re.I)
    # A saved template must never carry an obviously unrelated fact onto the
    # next book's back cover.
    topic_key = f"{package_data.get('detected_topic', '')} {package_data.get('series', '')} {package_data.get('title', '')}".casefold()
    for roots in (("ocean", "marine", "coast", "coral", "tide"), ("garden", "herb", "homestead"), ("bible", "faith", "scripture"), ("park", "trail", "outdoor"), ("car", "truck", "vehicle")):
        if any(root in blurb.casefold() for root in roots) and not any(root in topic_key for root in roots):
            blurb = ""
            break
    return blurb or topic_back_cover_copy(len(package_data.get("puzzles", [])), package_data)


def listing_kit_text(data: dict, record: dict[str, object] | None = None) -> str:
    """Create a copy-ready local KDP listing draft for one saved theme."""
    record = record or {}
    title = str(data.get("title") or "Word Search")
    subtitle = str(data.get("subtitle") or "")
    author = str(data.get("author") or "Jordan M. Slade")
    count = len(data.get("puzzles", []))
    pages = estimated_page_count(data)
    signature = is_signature_edition(data)
    price, royalty = recommended_us_paperback_price(pages, signature)
    topic = str(data.get("detected_topic") or data.get("series") or "themed puzzles")
    keywords = kdp_keyword_phrases(data)
    asin = str(record.get("asin") or "")
    kdp_url = str(record.get("kdp_url") or "")
    metadata_notes = kdp_metadata_review_notes(data)
    return f"""KDP LISTING KIT
{'=' * 58}

TITLE
{title}

SUBTITLE
{subtitle}

AUTHOR / PUBLISHER
{author}

SERIES
{data.get('series') or 'Not assigned'}

PUZZLES / FORMAT
{count} puzzles | {book_format_label(data).title()} | {puzzle_difficulty_label(data)} difficulty | estimated {pages} interior pages

BUYER-FACING QUALITY PROMISE
{"No repeated words across the book." if data.get("no_repeat_words") else "Review word variety before publishing."}

DESCRIPTION
{book_description(count, data)}

COPY-READY DESCRIPTION — PASTE DIRECTLY INTO KDP
{kdp_enhanced_description(data)}

KDP COMPLIANCE REVIEW
See KDP_COMPLIANCE_REPORT.txt in a finished package. The description above is plain text and is checked for common prohibited material.

RECOMMENDED US PAPERBACK LIST PRICE
${price:.2f}
{'Signature Edition premium included.' if signature else 'Standard Edition price.'}
This aims for the Amazon.com 60% royalty tier. Use KDP's current pricing calculator for the final printing cost and royalty; do not rely on a pre-upload estimate.

SEVEN KEYWORD BOXES — COPY ONE PHRASE INTO EACH BOX
{chr(10).join(f"{number}. {phrase}" for number, phrase in enumerate(keywords, start=1))}
These are intentionally distinct from the title and subtitle where possible. Before pasting, confirm every phrase is truthful and remove any word that already appears in your chosen categories. Do not use brand names, other authors, subjective claims, time-sensitive wording, or quotation marks.

CATEGORY DIRECTION TO REVIEW IN KDP
1. Start with the current equivalent of Games & Activities → Word & Word Search.
2. Add the most specific current subject category for “{topic}” only if it truthfully matches the actual puzzles.
3. Use a third category only if it is also an exact match; KDP allows up to three categories and paths can change.

METADATA AND RIGHTS CHECK
[ ] Description, title, subtitle, and cover accurately describe the interior
[ ] I have rights to every word list, image, font, and artwork used
[ ] I reviewed every keyword for accuracy and removed restricted brand/IP terms
[ ] {metadata_notes['ai_disclosure']}
[ ] I selected audience, language, reading direction, and publishing rights correctly
[ ] {metadata_notes['title_subtitle']}
[ ] {metadata_notes['format_check']}
[ ] Review KDP_COMPLIANCE_REPORT.txt. Fix every BLOCK item before uploading.

KDP DETAILS
ASIN: {asin or 'Add after KDP creates the paperback listing'}
KDP / Amazon link: {kdp_url or 'Add after creating the listing'}

UPLOAD CHECKLIST
[ ] Confirm title, subtitle, and author match the interior exactly
[ ] Upload interior PDF and KDP full-wrap PDF
[ ] Run KDP Print Previewer and correct every flagged issue
[ ] Confirm price, territories, and publishing rights
[ ] Save ASIN and book link in My Books Dashboard after publishing
"""


def kdp_upload_checklist_text(data: dict, page_count: int) -> str:
    title = str(data.get("title") or "Word Search Book")
    author = str(data.get("author") or "Jordan M. Slade")
    return f"""KDP UPLOAD CHECKLIST
{title}

[ ] Confirm title exactly matches: {title}
[ ] Confirm author exactly matches: {author}
[ ] Upload interior.pdf ({page_count} pages)
[ ] Upload kdp_full_wrap.pdf
[ ] Confirm trim size, bleed, and cover type in KDP match this package
[ ] Run KDP Print Previewer and correct every warning it identifies
[ ] Confirm price, territories, rights, and publishing date
[ ] Use the seven separate keyword phrases in the KDP listing kit; review each for accuracy
[ ] Choose current KDP categories that accurately fit this book
[ ] Select the AI-content disclosure based on the actual text and images used
[ ] Copy the reviewed description into KDP and confirm it matches the cover and interior
[ ] Read KDP_COMPLIANCE_REPORT.txt and correct every item marked BLOCK
[ ] Save the KDP ASIN and Amazon link in My Books Dashboard after publishing

Keep this checklist with the package until the paperback is live.
"""


def kdp_package_score(data: dict, package: Path | None, errors: list[str]) -> tuple[int, str]:
    score = 50 if quick_theme_readiness(data)[0] else 20
    if not errors: score += 20
    if package:
        score += sum(4 for name in ("interior.pdf", "front_cover.png", "kdp_full_wrap.pdf", "KDP_UPLOAD_CHECKLIST.txt", "PACKAGE_SCORECARD.txt", "KDP_LISTING_KIT.txt", "KDP_COMPLIANCE_REPORT.txt", "PUBLISHER_PREFLIGHT.txt", "ORIGINALITY_CHECK.txt", "AUTHOR_CONSISTENCY_REPORT.txt", "PACKAGE_SOURCE_RECORD.json", "FINAL_KDP_UPLOAD_STEPS.txt", "FIX_THIS_FIRST.txt") if package_file(package, name).exists())
        score += 4 if proof_folder(package).joinpath("PROOF_REVIEW.txt").exists() else 0
    score = min(score, 100)
    return score, "Ready for KDP review" if score >= 95 else ("Nearly ready" if score >= 75 else "Needs work")


def _book_word_set(data: dict) -> set[str]:
    return {
        re.sub(r"[^A-Z]", "", str(word).upper())
        for puzzle in data.get("puzzles", []) if isinstance(puzzle, dict)
        for word in puzzle.get("words", [])
        if re.sub(r"[^A-Z]", "", str(word).upper())
    }


def normalized_book_title(data: dict) -> str:
    """Normalize a title for local duplicate protection, not marketplace search."""
    title = str(data.get("title") or "").casefold()
    title = re.sub(r"\bsignature edition\b", "", title)
    return re.sub(r"[^a-z0-9]+", "", title)


def _intentional_signature_pair(left: dict, right: dict) -> bool:
    """A standard book and its named Signature Edition may intentionally share a core."""
    marker = re.compile(r"\s*[—-]\s*Signature Edition\s*$", re.I)
    left_title = marker.sub("", str(left.get("title") or "")).strip().casefold()
    right_title = marker.sub("", str(right.get("title") or "")).strip().casefold()
    left_signature = bool(left.get("signature_edition", {}).get("enabled")) if isinstance(left.get("signature_edition"), dict) else False
    right_signature = bool(right.get("signature_edition", {}).get("enabled")) if isinstance(right.get("signature_edition"), dict) else False
    return bool(left_title and left_title == right_title and left_signature != right_signature)


def cross_book_similarity_report(path: Path, data: dict, minimum: float = 0.45) -> list[dict[str, object]]:
    """Compare a book to every active theme and return the closest matches.

    This is intentionally a book-level originality signal—not a claim about
    copyright or marketplace availability.
    """
    own_words = _book_word_set(data)
    own_title = normalized_book_title(data)
    if not own_words and not own_title:
        return []
    matches: list[dict[str, object]] = []
    for other_path in all_book_theme_files():
        if other_path.resolve() == path.resolve():
            continue
        try:
            other = json.loads(other_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        other_words = _book_word_set(other)
        overlap = len(own_words & other_words) / max(1, len(own_words | other_words))
        same_title = bool(own_title and own_title == normalized_book_title(other))
        if overlap < minimum and not same_title:
            continue
        intentional = _intentional_signature_pair(data, other)
        level = "paired" if intentional else ("block" if same_title or overlap >= .85 else ("strong" if overlap >= .65 else "review"))
        matches.append({"path": other_path, "title": str(other.get("title") or other_path.stem), "overlap": overlap, "level": level, "same_title": same_title})
    return sorted(matches, key=lambda item: float(item["overlap"]), reverse=True)


def differentiation_suggestions(data: dict, matches: list[dict[str, object]]) -> list[str]:
    """Plain-language ways to make a companion book meaningfully different."""
    topic = str(data.get("detected_topic") or data.get("series") or "this topic").casefold()
    directions = [
        "Use a fresh word bank with no words from the closest matching book.",
        "Give the companion a narrower angle, a distinct title, and new puzzle names.",
    ]
    themed = {
        "space": "Try a focused companion such as planets, night sky, or space missions.",
        "vehicle": "Try a focused companion such as road trips, car care, classic cars, or RV life.",
        "bible": "Try a focused companion such as parables, Psalms, or faith-and-encouragement vocabulary.",
        "vocabulary": "Use the next grade level or a separate skills focus with a newly selected word pool.",
        "garden": "Try flowers, vegetables, herbs, or garden wildlife as a clearly separate companion.",
        "park": "Focus each companion on a different region, landscape, or park type.",
    }
    for keyword, suggestion in themed.items():
        if keyword in topic:
            directions.insert(0, suggestion)
            break
    if matches:
        directions.append(f"Closest current match: {matches[0]['title']} ({float(matches[0]['overlap']):.0%} shared vocabulary).")
    return directions


def package_scorecard_text(data: dict, folder: Path, page_count: int, quality_warnings: list[str] | None = None) -> str:
    """A self-contained final production summary saved in every package."""
    quality_warnings = quality_warnings or []
    content_score, content_label, strengths, improvements = content_quality_score(data)
    required = ("interior.pdf", "front_cover.png", "kdp_full_wrap.pdf", "KDP_UPLOAD_CHECKLIST.txt", "KDP_LISTING_KIT.txt", "KDP_COMPLIANCE_REPORT.txt", "PUBLISHER_PREFLIGHT.txt", "proof_review/PROOF_REVIEW.txt", "ORIGINALITY_CHECK.txt", "AUTHOR_CONSISTENCY_REPORT.txt", "PACKAGE_SOURCE_RECORD.json", "FINAL_KDP_UPLOAD_STEPS.txt", "FIX_THIS_FIRST.txt")
    package_errors = [f"Missing {name}" for name in required if not (proof_folder(folder).joinpath("PROOF_REVIEW.txt").exists() if name == "proof_review/PROOF_REVIEW.txt" else package_file(folder, name).exists())]
    package_score, package_label = kdp_package_score(data, folder, package_errors)
    if quality_warnings:
        package_score = max(0, package_score - min(20, 4 * len(quality_warnings)))
        package_label = "Ready for KDP review with notes" if package_score >= 85 else "Review notes before publishing"
    lines = [
        "FINAL PACKAGE SCORECARD", "=" * 58,
        f"Title: {data.get('title') or 'Word Search'}",
        f"Puzzles: {len(data.get('puzzles', []))} | Interior pages: {page_count}",
        f"Content score: {content_score}/100 — {content_label}",
        f"Package score: {package_score}/100 — {package_label}", "",
        "FILES CHECKED",
    ]
    for name in required:
        lines.append(f"{'PASS' if (folder / name).exists() else 'CHECK'} — {name}")
    lines.extend(["", "BUYER-FACING STRENGTHS"] + [f"• {item}" for item in strengths[:5]])
    lines.extend(["", "NEXT STEPS"] + [f"• {item}" for item in improvements[:3]])
    if quality_warnings:
        lines.extend(["", "ORIGINALITY / REVIEW NOTES"] + [f"• {item}" for item in quality_warnings[:5]])
    lines.extend(["", "Before uploading: open both PDFs, then run the current KDP Print Previewer."])
    return "\n".join(lines) + "\n"


def spine_safety_note(page_count: int) -> str:
    return "Spine: omit spine text; this book is likely too thin." if page_count < 101 else "Spine: likely wide enough for short spine text—confirm in KDP Cover Calculator."


def marketing_descriptions(data: dict) -> str:
    title = str(data.get("title") or "Word Search"); count = len(data.get("puzzles", [])); topic = str(data.get("detected_topic") or "your favorite topic")
    return (f"WARM DESCRIPTION\nUnwind with {title}, a {count}-puzzle collection inspired by {topic}. Each satisfying search offers a calm, screen-free break for puzzle lovers.\n\n"
            f"PREMIUM DESCRIPTION\n{title} is a thoughtfully designed {count}-puzzle word-search collection with clear layouts, themed vocabulary, and complete solutions—made for relaxed, focused enjoyment.\n\n"
            f"KEYWORD-FOCUSED DESCRIPTION\nEnjoy {count} themed word search puzzles about {topic}. This adult and teen puzzle book offers relaxing brain games, easy-to-read grids, and solutions at the back.\n\n"
            "SEVEN KDP KEYWORD PHRASES\n" + "\n".join(kdp_keyword_phrases(data)) + "\n")


def kdp_keyword_phrases(data: dict) -> list[str]:
    topic = re.sub(r"[^a-z0-9 ]", "", str(data.get("detected_topic") or data.get("series") or "themed").lower()).strip()
    audience = re.sub(r"[^a-z0-9 ]", "", str(data.get("audience") or "adults and teens").lower()).strip()
    large = book_format_label(data) == "LARGE PRINT PUZZLES"
    title_words = set(re.findall(r"[a-z0-9]+", f"{data.get('title', '')} {data.get('subtitle', '')}".lower()))
    topic_profiles = (
        (("space", "astronomy", "planet"), ["solar system activity", "planets and galaxies", "stargazing puzzle activity", "cosmic science games"]),
        (("american history", "american heritage", "us history"), ["colonial america activity", "presidential history games", "historic landmarks puzzles", "united states history"]),
        (("car", "truck", "vehicle", "automotive", "road trip"), ["classic car enthusiast", "truck lover activity", "scenic road trip games", "automotive history puzzles"]),
        (("bird",), ["birdwatching activity", "songbird puzzle games", "backyard wildlife", "nature lover gift"]),
        (("ocean", "marine", "sea"), ["marine life activity", "sea creature puzzles", "coastal nature games", "ocean lover gift"]),
        (("garden", "herb", "homestead"), ["garden lover activity", "plant and flower puzzles", "homestead hobby games", "nature puzzle gift"]),
        (("christmas", "winter", "holiday"), ["cozy winter activity", "seasonal puzzle games", "holiday family activity", "festive word games"]),
    )
    extras = next((phrases for markers, phrases in topic_profiles if any(marker in topic for marker in markers)), [])
    fallback = [f"{topic} activity", f"{topic} puzzle games", "relaxing brain game", "unplugged puzzle time"]
    choices = extras + fallback + [
        f"relaxing puzzles for {audience}",
        "large print activity" if large else "themed puzzle activity",
        "puzzles with solutions", "gift for puzzle lovers",
    ]
    cleaned: list[str] = []
    for choice in choices:
        phrase = " ".join(choice.split())[:50].strip()
        if not phrase or phrase in cleaned:
            continue
        # Prefer complementary search language; do not simply duplicate the
        # full title, but allow a short accurate subject phrase when needed.
        phrase_words = set(re.findall(r"[a-z0-9]+", phrase.lower()))
        if phrase_words and phrase_words.issubset(title_words):
            continue
        cleaned.append(phrase)
        if len(cleaned) == 7:
            break
    defaults = ["relaxing brain game", "unplugged puzzle time", "puzzles with solutions", "gift for puzzle lovers"]
    for phrase in defaults:
        if phrase not in cleaned and len(cleaned) < 7:
            cleaned.append(phrase)
    return cleaned[:7]


def kdp_enhanced_description(data: dict) -> str:
    """Create lively, direct-paste plain text for the KDP description field.

    KDP accepts basic HTML, but a buyer-facing listing kit should never make
    the publisher copy markup by accident.  Paragraphs and simple hyphen
    bullets paste cleanly into Amazon, Etsy, Payhip, and a direct storefront.
    """
    title = str(data.get("title") or "This Word Search Collection").strip()
    topic = str(data.get("detected_topic") or data.get("series") or "a favorite topic").strip()
    count = len(data.get("puzzles", []))
    format_text = "large-print, easy-to-read" if book_format_label(data) == "LARGE PRINT PUZZLES" else "clear, themed"
    word_count = sum(len(item.get("words", [])) for item in data.get("puzzles", []) if isinstance(item, dict))
    repeat_line = "Every puzzle has a different word list, with no repeated words across the book." if data.get("no_repeat_words") else "Each puzzle is designed as a fresh, focused challenge."
    openings = (
        "Open the book, pick a page, and let a small adventure in words begin.",
        "Give your brain a cheerful change of pace—one satisfying find at a time.",
        "Take a break from scrolling and settle into a puzzle experience made to savor.",
    )
    finishers = (
        "Whether you solve a page at a time or disappear into a longer session, every completed grid brings a little burst of momentum.",
        "It is an easy companion for a quiet morning, a travel bag, a waiting room, or a thoughtful gift for a fellow puzzle lover.",
        "From the first word you spot to the final satisfying circle, this collection makes ordinary spare moments feel more rewarding.",
    )
    choice = sum(ord(ch) for ch in str(data.get("title") or topic)) % len(openings)
    return (
        f"{title} turns a love of {topic} into a rewarding, screen-free puzzle escape. {openings[choice]} "
        f"Explore {count} {format_text} word searches filled with focused vocabulary, inviting challenges, and complete solutions at the back.\n\n"
        f"{repeat_line} {finishers[choice]}\n\n"
        "Inside this collection:\n"
        f"- {count} themed word search puzzles\n"
        f"- {word_count} puzzle words across the book\n"
        f"- {'Large-print grids' if book_format_label(data) == 'LARGE PRINT PUZZLES' else 'Clear, readable grids'}\n"
        "- Complete solutions at the back\n\n"
        "Bring a pencil, follow your curiosity, and enjoy the simple pleasure of finding the next hidden word."
    )


_KDP_METADATA_FORBIDDEN = (
    (r"https?://|www\.", "web address"),
    (r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "email address"),
    (r"\b(?:bestseller|best selling|on sale|available now|kindle unlimited|kdp select|free download|free offer)\b", "promotion, ranking, or Amazon-program claim"),
    (r"\b(?:leave (?:a )?review|write (?:a )?review|review us)\b", "request for reviews"),
)


def kdp_metadata_compliance_report(data: dict, description: str | None = None) -> tuple[list[str], list[str]]:
    """Return KDP-focused metadata blockers and plain-English review notes.

    This validates fields that the program controls.  It deliberately does not
    invent categories, rights, or AI disclosures—those require the publisher's
    real-world knowledge at upload time.
    """
    errors: list[str] = []
    warnings: list[str] = []
    title = str(data.get("title") or "").strip()
    subtitle = str(data.get("subtitle") or "").strip()
    author = str(data.get("author") or "").strip()
    combined = len(title) + len(subtitle)
    if not title:
        errors.append("Title is blank.")
    if not author:
        errors.append("Author / publisher name is blank.")
    if combined >= 200:
        errors.append(f"Title + subtitle total {combined} characters; KDP requires fewer than 200.")
    if len(title) > 60:
        warnings.append(f"Title is {len(title)} characters. KDP notes that long titles are easier for shoppers to skim past; consider a shorter buyer-facing title.")
    for field_name, value in (("Title", title), ("Subtitle", subtitle), ("Author", author)):
        if re.search(r"<[^>]+>", value):
            errors.append(f"{field_name} contains HTML, which KDP does not allow in this field.")
    text = description if description is not None else kdp_enhanced_description(data)
    if len(text) > 4000:
        errors.append(f"Description is {len(text)} characters; KDP allows a maximum of 4,000 including HTML.")
    elif len(re.sub(r"<[^>]+>", "", text).split()) < 70:
        warnings.append("Description is brief. KDP recommends a simple, compelling, professional description of roughly 150 easy-to-scan words.")
    for pattern, label in _KDP_METADATA_FORBIDDEN:
        if re.search(pattern, text, flags=re.I):
            errors.append(f"Description includes a restricted {label}.")
    keywords = kdp_keyword_phrases(data)
    if len(keywords) != 7:
        errors.append("Listing needs exactly seven keyword phrases.")
    if len({phrase.casefold() for phrase in keywords}) != len(keywords):
        errors.append("Keyword phrases contain duplicates.")
    for phrase in keywords:
        if len(phrase) > 50:
            errors.append(f"Keyword phrase is over 50 characters: {phrase}")
        if re.search(r"[\"'<>]|https?://|\b(?:free|best|kindle|kdp)\b", phrase, flags=re.I):
            errors.append(f"Keyword phrase needs review or replacement: {phrase}")
    if not data.get("series"):
        warnings.append("No series is assigned. Leave the KDP series field blank unless this book truly belongs to an established series.")
    return list(dict.fromkeys(errors)), list(dict.fromkeys(warnings))


def kdp_compliance_report_text(data: dict, page_count: int | None = None) -> str:
    """A saved, human-readable KDP checklist based on current official rules."""
    description = kdp_enhanced_description(data)
    errors, warnings = kdp_metadata_compliance_report(data, description)
    pages = page_count if page_count is not None else estimated_page_count(data)
    title = str(data.get("title") or "Word Search")
    lines = ["KDP COMPLIANCE & DISCOVERABILITY REVIEW", "=" * 58, f"Book: {title}", f"Interior pages: {pages}", ""]
    lines += ["AUTOMATIC RESULT", "PASS — no automated metadata blockers found." if not errors else "BLOCK — correct the item(s) below before upload."]
    if errors:
        lines += [f"• {item}" for item in errors]
    lines += ["", "DISCOVERABILITY CHECKS"]
    lines += ["• Use the seven separate keyword phrases in the listing kit. Keep only phrases that accurately describe the puzzles.", "• Choose up to three current KDP categories that are exact matches; do not use broad or unrelated categories.", "• Keep the title, subtitle, author, series, description, cover, and interior consistent.", "• Use the KDP description exactly as generated or re-run this review after editing it."]
    if warnings:
        lines += ["", "REVIEW NOTES"] + [f"• {item}" for item in warnings]
    lines += ["", "UPLOAD SAFETY", "• Confirm every asset has commercial-use rights.", "• Disclose AI-generated text, images, or translations when required by KDP; AI-assisted editing alone is treated differently by KDP.", "• Run KDP Print Previewer and correct every issue it flags before publishing."]
    return "\n".join(lines) + "\n"


def write_kdp_compliance_report(folder: Path, data: dict, page_count: int) -> Path:
    """Save the automatic KDP standards review alongside every package."""
    target = package_file(folder, "KDP_COMPLIANCE_REPORT.txt", for_write=True)
    target.write_text(kdp_compliance_report_text(data, page_count), encoding="utf-8")
    return target


def kdp_metadata_review_notes(data: dict) -> dict[str, str]:
    """Plain-English, current-process reminders placed directly in every kit."""
    title = str(data.get("title") or "")
    subtitle = str(data.get("subtitle") or "")
    limit_note = "Confirm title + subtitle are under KDP's 200-character combined limit."
    if len(title) + len(subtitle) < 200:
        limit_note = f"Title + subtitle total {len(title) + len(subtitle)} characters; still confirm the final KDP fields match the cover exactly."
    return {
        "ai_disclosure": "Disclose AI-generated text, images, or translations when KDP asks. KDP treats content created by an AI tool as AI-generated even if you edit it; AI-assisted editing of content you created yourself is treated differently. Confirm the answer from the actual assets used.",
        "title_subtitle": limit_note,
        "format_check": "Puzzle books are generally not low-content on KDP; use the regular paperback path unless this specific book is genuinely repetitive/low-content. Do not count on Expanded Distribution for word-search books.",
    }


def write_listing_kit(theme_path: Path, data: dict, record: dict[str, object] | None = None) -> Path:
    folder = OUTPUT_DIR / "listing_kits" / WordSearchCreator._safe_filename(str(data.get("title") or theme_path.stem))
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / "kdp_listing_kit.txt"
    target.write_text(listing_kit_text(data, record), encoding="utf-8")
    return target


def find_latest_book_package(title: str) -> Path | None:
    """Return the newest finished package for a title from either production flow."""
    safe_name = re.sub(r"[^A-Za-z0-9]+", "_", title).strip("_").lower()
    if not safe_name or not OUTPUT_DIR.exists():
        return None
    matches = [
        candidate.parent.parent if candidate.parent.name == "01_PRINT_UPLOADS" else candidate.parent
        for candidate in OUTPUT_DIR.rglob("kdp_full_wrap.pdf")
        if (candidate.parent.parent if candidate.parent.name == "01_PRINT_UPLOADS" else candidate.parent).name.lower() == safe_name
        or (candidate.parent.parent if candidate.parent.name == "01_PRINT_UPLOADS" else candidate.parent).name.lower().startswith(f"{safe_name}_")
    ]
    return max(matches, key=lambda candidate: candidate.stat().st_mtime) if matches else None


def audit_theme(path: Path, seed: int) -> tuple[list[str], list[str], list[str]]:
    """Check the exact data and word placement used for an interior PDF."""
    errors: list[str] = []
    warnings: list[str] = []
    notes: list[str] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"Cannot read {path.name}: {exc}"], warnings, notes

    if not isinstance(data, dict):
        return ["The theme file must contain a book setup."], warnings, notes
    puzzles = data.get("puzzles")
    if not isinstance(puzzles, list) or not puzzles:
        return ["This theme does not contain any puzzles."], warnings, notes
    minimum_puzzles = signature_puzzle_target(data)
    if len(puzzles) < minimum_puzzles:
        standard = "Signature Edition standard" if minimum_puzzles == SIGNATURE_PUZZLE_TARGET else "Slade production standard"
        errors.append(f"This book has only {len(puzzles)} puzzles. {standard} is at least {minimum_puzzles} puzzles.")
    if not str(data.get("title", "")).strip():
        warnings.append("The theme has no saved title. The title currently shown in the app will be used.")

    random.seed(seed)
    names_seen: set[str] = set()
    book_word_locations: dict[str, list[str]] = {}
    nonstandard_word_counts: list[int] = []
    for number, puzzle in enumerate(puzzles, start=1):
        if not isinstance(puzzle, dict):
            errors.append(f"Puzzle {number} is not in the expected format.")
            continue
        name = str(puzzle.get("name", "")).strip()
        if not name:
            errors.append(f"Puzzle {number} has no name.")
            name = f"Puzzle {number}"
        name_key = " ".join(name.upper().split())
        if name_key in names_seen:
            errors.append(f"Puzzle {number} repeats the name '{name}'.")
        names_seen.add(name_key)

        source_words = puzzle.get("words")
        if not isinstance(source_words, list) or not source_words:
            errors.append(f"{name}: it has no words.")
            continue
        if len(source_words) < 12:
            errors.append(f"{name}: it has {len(source_words)} words. Slade production standard is at least 12 words per puzzle.")
        if len(source_words) > 25:
            errors.append(f"{name}: it has {len(source_words)} words; the maximum is 25.")

        cleaned = puzzle_engine.clean_words(source_words)
        if len(cleaned) != len(source_words):
            errors.append(f"{name}: one or more words are blank or longer than 21 letters.")
        word_keys: set[str] = set()
        for word in cleaned:
            if word in word_keys:
                errors.append(f"{name}: '{word}' appears more than once.")
            word_keys.add(word)
            book_word_locations.setdefault(word, []).append(name)
        if not cleaned:
            continue

        grid, _placements, placed = puzzle_engine.generate_puzzle(
            cleaned, N=puzzle_engine.grid_size_for(cleaned)
        )
        if len(placed) != len(cleaned):
            errors.append(f"{name}: only {len(placed)} of {len(cleaned)} words could be placed.")
        elif len(cleaned) not in (12, 20):
            nonstandard_word_counts.append(len(cleaned))

    repeats = {word: locations for word, locations in book_word_locations.items() if len(locations) > 1}
    if repeats:
        examples = ", ".join(sorted(repeats)[:6])
        errors.append(f"This book repeats {len(repeats)} word(s) across different puzzles ({examples}). Published books must have no repeated words.")

    ordered_lists = [
        puzzle_engine.clean_words(puzzle.get("words") or [])
        for puzzle in puzzles if isinstance(puzzle, dict)
    ]
    alphabetized = sum(1 for words in ordered_lists if len(words) >= 6 and words == sorted(words))
    if ordered_lists and alphabetized / len(ordered_lists) >= 0.5:
        errors.append(
            f"Production stop: {alphabetized} of {len(ordered_lists)} puzzle word lists are alphabetized. "
            "Rebuild the book through the topic-aware planner so readers receive varied, intentionally mixed lists."
        )

    notes.append(f"Checked {len(puzzles)} puzzle(s) using random seed {seed}.")
    notes.append("Grid sizes are selected automatically from each puzzle's word count.")
    if nonstandard_word_counts:
        counts = ", ".join(str(count) for count in sorted(set(nonstandard_word_counts)))
        warnings.append(
            f"{len(nonstandard_word_counts)} puzzle(s) use {counts}-word lists instead of the usual 12 or 20. "
            "They are supported and will size automatically."
        )
    return errors, warnings, notes


def quality_gate(path: Path, seed: int) -> tuple[list[str], list[str], list[str]]:
    """Broader production check: validity, originality signals, and presentation."""
    errors, warnings, notes = audit_theme(path, seed)
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return errors, warnings, notes
    # Word Intelligence is the source-level content check.  Older builds
    # could show its warning in a separate screen but still let package
    # creation continue.  Keep the final production gate connected to the
    # saved result so a mixed legacy word bank cannot be presented as ready.
    quality_review = data.get("quality_review")
    if isinstance(quality_review, dict) and quality_review.get("production_ready") is False:
        verdict = str(quality_review.get("verdict") or "needs content review")
        errors.append(
            "This theme's verified word-quality review is not production-ready "
            f"({verdict}). Rebuild its word pool from the matching topic before creating a package."
        )
    title = str(data.get("title", ""))
    if len(title) > 60:
        warnings.append("Title is over 60 characters; shorten it for a cleaner Amazon search result and cover.")
    names = [str(p.get("name", "")) for p in data.get("puzzles", [])]
    generic = sum(1 for name in names if re.fullmatch(r"(?:Puzzle|Word Search)\s*\d+", name, re.I))
    if generic:
        warnings.append(f"{generic} puzzle name(s) are generic. Specific names make a Signature Edition feel more premium.")
    matches = cross_book_similarity_report(path, data)
    for match in matches[:3]:
        other_title = str(match["title"])
        overlap = float(match["overlap"])
        level = str(match["level"])
        if level == "paired":
            notes.append(f"Paired standard/Signature Edition detected: shared puzzle core with {other_title} is intentional.")
        elif level == "block":
            errors.append(f"This book is very similar to '{other_title}' ({overlap:.0%} shared vocabulary). Choose a fresh word bank before publishing both.")
        elif level == "strong":
            errors.append(f"Production stop: this book is too similar to '{other_title}' ({overlap:.0%} shared vocabulary). Build a distinct word pool before creating another package.")
        else:
            warnings.append(f"Some shared vocabulary with '{other_title}' ({overlap:.0%}). Review it before publishing both books.")
    safety = publisher_safety_report(data)
    warnings.extend(safety["warnings"])
    notes.extend(safety["notes"])
    expected_topics = safety.get("expected_topics", [])
    recognized_words = int(safety.get("recognized_words", 0))
    unique_words = int(safety.get("unique_words", 0))
    library_fit = safety.get("topic_fit")
    if expected_topics:
        minimum_recognized = min(30, max(12, unique_words // 4))
        if recognized_words < minimum_recognized:
            errors.append("Production stop: too few puzzle words are recognized in the matching topic sources. Rebuild the book from its proven topic pool before creating a package.")
        elif isinstance(library_fit, int) and library_fit < 70:
            errors.append(f"Production stop: only {library_fit}% of recognized words match {', '.join(str(item) for item in expected_topics)}. Rebuild the word pool before creating a package.")
        elif isinstance(library_fit, int) and library_fit < 85:
            warnings.append(f"Clean-library topic check: {library_fit}% of recognized words match the intended topic. Strengthen the word bank before publishing.")
    direct_fit, direct_rule = direct_topic_fit_report(data)
    if direct_fit is not None:
        if direct_fit < 60:
            errors.append(f"Production stop: only {direct_fit}% of puzzle words match this {direct_rule.title()} cover promise. Strengthen the word bank before creating a package.")
        elif direct_fit < 70:
            errors.append(f"Production stop: only {direct_fit}% of puzzle words match this {direct_rule.title()} cover promise. Strengthen the word bank before creating a package.")
        else:
            notes.append(f"Independent topic-fit check: {direct_fit}% matches the {direct_rule.title()} promise.")
    if safety.get("review_words"):
        errors.append("Protected-name safety stop: remove or replace the flagged brand, franchise, or celebrity terms before creating an automatic package.")
    truth = intelligence_production_truth(data)
    if truth is not None:
        errors.extend(f"Production truth: {item}" for item in truth.errors)
        warnings.extend(f"Production truth: {item}" for item in truth.warnings)
        notes.extend(f"Production truth: {item}" for item in truth.notes)
        actual_puzzles = len(data.get("puzzles") or [])
        if truth.recommended_puzzles and truth.recommended_puzzles < actual_puzzles:
            notes.append(
                f"Verified repeat-free capacity currently supports about "
                f"{truth.recommended_puzzles} puzzles with "
                f"{truth.recommended_words_per_puzzle} words each. "
                "Expand the reviewed topic pool before promising more.")
    errors, warnings, notes = (list(dict.fromkeys(errors)),
                               list(dict.fromkeys(warnings)),
                               list(dict.fromkeys(notes)))
    return errors, warnings, notes


_INTELLIGENCE_RUNTIME: tuple[object, object] | None = None
_INTELLIGENCE_RUNTIME_LOCK = threading.Lock()


def intelligence_production_truth(data: dict):
    """Return the shared no-write word-intelligence decision for one book.

    Legacy themes without a recognizable Master Library topic remain usable
    after normal checks; they simply do not receive a made-up coherence grade.
    """
    source = data.get("source_word_bank") if isinstance(data, dict) else {}
    candidates: list[str] = []
    if isinstance(source, dict):
        candidates.extend(str(item) for item in source.get("topics", [])
                          if str(item).strip())
    candidates.extend(str(data.get(key) or "") for key in
                      ("detected_topic", "topic", "series"))
    try:
        from word_intelligence import pipeline
        from word_intelligence.production_gate import evaluate_book
        global _INTELLIGENCE_RUNTIME
        with _INTELLIGENCE_RUNTIME_LOCK:
            if _INTELLIGENCE_RUNTIME is None:
                taxonomy = pipeline.load_taxonomy(APP_DIR)
                loaded = pipeline.load_or_build_store(
                    taxonomy, APP_DIR,
                    state_dir=APP_DIR / "word_banks" / "word_intelligence")
                store = loaded[0] if isinstance(loaded, tuple) else loaded
                _INTELLIGENCE_RUNTIME = (store, taxonomy)
            store, taxonomy = _INTELLIGENCE_RUNTIME
        topic = next((candidate for candidate in candidates
                      if candidate and taxonomy.resolve(candidate)), "")
        if not topic:
            return None
        puzzles = [list(item.get("words") or []) for item in data.get("puzzles", [])
                   if isinstance(item, dict)]
        names = [str(item.get("name") or "") for item in data.get("puzzles", [])
                 if isinstance(item, dict)]
        return evaluate_book(store, taxonomy, topic, puzzles,
                             required_puzzles=len(puzzles), puzzle_names=names)
    except Exception:
        # A missing optional intelligence cache must not make the established
        # PDF generator unusable; the normal checks still protect the package.
        return None


# These are a practical publishing-review signal, not legal advice or a complete
# trademark database.  They keep likely franchise/celebrity terms out of the
# fully automatic path while preserving the user's source word banks unchanged.
REVIEW_REQUIRED_TERMS = {
    "DISNEY", "MARVEL", "STARWARS", "POKEMON", "MINECRAFT", "FORTNITE", "NINTENDO",
    "PLAYSTATION", "XBOX", "SONIC", "MARIO", "HARRY POTTER", "HARRYPOTTER", "BARBIE",
    "TAYLOR SWIFT", "TAYLORSWIFT", "BEYONCE", "BEYONCÉ", "NETFLIX", "LEGO",
}

# A second, deliberately independent topic check.  The Master Library records
# where a word has appeared before; it cannot prove that the word belongs in a
# new book because an old imported theme may itself be off-topic.  These roots
# are used only for clear, high-impact niches where a buyer would reasonably
# expect every puzzle word to match the cover promise.
DIRECT_TOPIC_ROOTS: dict[str, tuple[str, ...]] = {
    "zion": ("ZION", "ANGEL", "NARROW", "CANYON", "SANDSTONE", "VIRGIN", "EMERALD", "WATCHMAN", "MESA", "CLIFF", "SLOT", "COTTONWOOD", "BIGHORN", "REDROCK", "TRAIL", "HIKE", "HIKER", "RANGER", "NATIONALPARK", "WILDERNESS", "WILDLIFE", "CAMPGROUND", "BACKPACK", "DESERT", "SUNRISE", "SUNSET", "VIEWPOINT", "OUTDOOR", "NATURE", "CONSERVATION", "SCENIC", "EXPLORER", "DISCOVER", "PICNIC", "BINOCULAR"),
    "space": ("SPACE", "ASTRO", "PLANET", "STAR", "MOON", "SUN", "SOLAR", "GALAX", "NEBUL", "COMET", "METEOR", "ORBIT", "ROCKET", "LAUNCH", "ASTRONAUT", "COSMIC", "UNIVERSE", "TELESCOPE", "SATELLITE", "ECLIPSE", "LUNAR", "MARS", "MARTIAN", "VENUS", "VENUSIAN", "MERCURY", "JUPITER", "JOVIAN", "SATURN", "SATURNIAN", "URANUS", "NEPTUNE", "NEPTUNIAN", "PLUTO", "APOLLO", "ARTEMIS", "VOYAGER", "HUBBLE", "WEBB", "GRAVITY", "CONSTELLATION", "STARGAZ", "BLACKHOLE", "SUPERNOVA", "EXOPLANET", "LIGHTYEAR", "CELESTIAL", "ALIEN", "ROVER", "LANDER", "PROBE", "MISSION", "PAYLOAD", "BOOSTER", "THRUSTER", "REENTRY", "LIFTOFF", "MOONWALK", "SPACESHUTTLE", "SPACESTATION", "SKY", "NIGHT", "EARTHRISE", "AURORA", "HELI", "QUASAR", "PULSAR", "WORMHOLE", "DARKMATTER", "DARKENERGY", "ZEROGRAVITY", "VACUUM"),
    "christmas": ("CHRISTMAS", "SANTA", "REINDEER", "SNOW", "HOLLY", "ORNAMENT", "CAROL", "GIFT", "PRESENT", "STOCKING", "TREE", "CANDY", "GINGERBREAD", "COOKIE", "CANDLE", "WREATH", "BELL", "ANGEL", "NATIVITY", "MISTLETOE", "SLEIGH", "WINTER", "COZY", "FESTIVE", "HOLIDAY", "NORTHPOLE", "ELF", "YULE", "NOEL", "POINSETTIA", "FIREPLACE", "TINSEL", "BAUBLE", "NUTCRACKER", "FROST", "PINE", "CELEBRATION"),
}


def direct_topic_fit_report(data: dict) -> tuple[int | None, str | None]:
    """Return a conservative independent topic-fit score for focused niches."""
    # A Guided Builder book that records explicit Master Library sources is
    # already checked against those exact topics by publisher_safety_report.
    # Do not override that precise check with a narrow text-root heuristic:
    # terms such as a planet name or a scientific instrument can be perfectly
    # valid Space & Astronomy vocabulary without containing a root like STAR.
    source = data.get("source_word_bank", {})
    if isinstance(source, dict) and isinstance(source.get("topics"), list) and source["topics"]:
        return None, None
    hint = " ".join(str(data.get(key) or "") for key in ("title", "subtitle", "detected_topic", "series")).casefold()
    rule = next((name for name in DIRECT_TOPIC_ROOTS if name in hint), None)
    if not rule:
        return None, None
    words = [re.sub(r"[^A-Z]", "", str(word).upper()) for puzzle in data.get("puzzles", []) if isinstance(puzzle, dict) for word in puzzle.get("words", [])]
    words = [word for word in words if word]
    if not words:
        return 0, rule
    roots = DIRECT_TOPIC_ROOTS[rule]
    on_topic = sum(1 for word in words if any(root in word for root in roots))
    return round(100 * on_topic / len(words)), rule


def _normalized_words(data: dict) -> set[str]:
    return {re.sub(r"[^A-Z0-9 ]", "", str(word).upper()).strip() for puzzle in data.get("puzzles", []) if isinstance(puzzle, dict) for word in puzzle.get("words", []) if str(word).strip()}


def _expected_topics(data: dict, library: dict) -> list[str]:
    """Find the intended Master Library sources for a book.

    A Guided Builder theme records its direct source topics.  Those are more
    reliable than guessing from a buyer-facing title such as “Thanksgiving”,
    which can draw from several clean seasonal source groups.
    """
    topics = library.get("topics", {}) if isinstance(library, dict) else {}
    source = data.get("source_word_bank", {})
    if isinstance(source, dict) and isinstance(source.get("topics"), list):
        explicit = [str(topic) for topic in source["topics"] if str(topic) in topics]
        if explicit:
            return explicit[:8]
    hint = " ".join(str(data.get(key) or "") for key in ("detected_topic", "series", "title")).casefold()
    tokens = {token for token in re.findall(r"[a-z0-9]+", hint) if len(token) > 2}
    ranked: list[tuple[int, str]] = []
    for topic in topics if isinstance(topics, dict) else []:
        topic_tokens = set(re.findall(r"[a-z0-9]+", str(topic).casefold()))
        score = len(tokens & topic_tokens)
        if str(topic).casefold() in hint:
            score += 3
        if score:
            ranked.append((score, str(topic)))
    return [topic for _score, topic in sorted(ranked, reverse=True)[:3]]


def publisher_safety_report(data: dict, library: dict | None = None) -> dict[str, object]:
    """Plain-English publishing checks: promises, topic fit, and review terms."""
    warnings: list[str] = []; notes: list[str] = []
    words = _normalized_words(data)
    library = library if isinstance(library, dict) else load_master_word_bank()
    expected = _expected_topics(data, library)
    profiles = library.get("word_profiles", {}) if isinstance(library, dict) else {}
    matched = 0; on_topic = 0
    for word in words:
        profile = profiles.get(word) if isinstance(profiles, dict) else None
        if not isinstance(profile, dict):
            continue
        matched += 1
        word_topics = {str(item) for item in profile.get("topics", [])}
        if set(expected) & word_topics:
            on_topic += 1
    if expected and matched >= 30:
        fit = round(100 * on_topic / matched)
        if fit < 30:
            warnings.append(f"Topic fit is only {fit}% against the closest Master Library topic(s): {', '.join(expected)}. Review the word bank so the cover promise matches the puzzles.")
        else:
            notes.append(f"Library cross-reference: {fit}% of recognized words have appeared in related saved topics ({', '.join(expected)}).")
    else:
        fit = None
        notes.append("Library cross-reference: not enough recognized words for a reliable comparison; use the independent topic-fit check and reader preview as the deciding checks.")
    review_words = sorted(word for word in words if word in REVIEW_REQUIRED_TERMS)
    if review_words:
        warnings.append("Rights review needed for possible protected names: " + ", ".join(review_words[:8]) + ". Remove them from automatic books unless you have permission. This is a review reminder, not legal advice.")
    promise_text = " ".join(str(data.get(key) or "") for key in ("title", "subtitle", "cover_badge")).upper()
    count = len(data.get("puzzles", []))
    for value in re.findall(r"\b(\d{1,3})\b", promise_text):
        number = int(value)
        if number in range(24, 201) and number != count:
            warnings.append(f"Cover/listing text mentions {number} puzzles, but this theme contains {count}. Update the promise before publishing.")
            break
    if "NO REPEAT" in promise_text and not data.get("no_repeat_words"):
        warnings.append("The cover says no repeated words, but this theme is not marked as repeat-free. Run Check Book before making that claim.")
    if "LARGE PRINT" in promise_text and book_format_label(data) != "LARGE PRINT PUZZLES":
        warnings.append("The cover says large print, but the selected book format is not large print. Make the format and cover promise agree.")
    if not review_words:
        notes.append("Rights screen: no common protected-name review terms were found in this book's word list.")
    return {
        "warnings": warnings, "notes": notes, "topic_fit": fit,
        "expected_topics": expected, "review_words": review_words,
        "recognized_words": matched, "unique_words": len(words),
    }


# A practical, transparent launch order.  This is a production-readiness score,
# not a claim about guaranteed sales.  It rewards the things a buyer can feel:
# a complete book, no repeated words, a topic-matched word bank, and enough
# clean source material to make a fresh book again later.
LAUNCH_DEMAND_HINTS: tuple[tuple[tuple[str, ...], int], ...] = (
    (("space", "astronomy", "vehicle", "automotive"), 10),
    (("garden", "bird", "pet", "nature", "travel", "park"), 7),
    (("faith", "bible", "holiday", "christmas", "vocabulary"), 5),
)


def theme_launch_readiness(data: dict, library: dict | None = None) -> tuple[int, str, list[str]]:
    """Return an honest, plain-English next-book recommendation."""
    library = library if isinstance(library, dict) else load_master_word_bank()
    safety = publisher_safety_report(data, library)
    puzzles = [item for item in data.get("puzzles", []) if isinstance(item, dict)]
    puzzle_count = len(puzzles)
    all_words = [re.sub(r"[^A-Z]", "", str(word).upper()) for puzzle in puzzles for word in puzzle.get("words", [])]
    all_words = [word for word in all_words if word]
    unique_words = set(all_words)
    score = 0
    reasons: list[str] = []
    if puzzle_count >= 48:
        score += 25; reasons.append(f"Complete {puzzle_count}-puzzle book")
    else:
        score += min(18, puzzle_count // 2)
        reasons.append(f"Only {puzzle_count} puzzles; build it to at least 48 first")
    if all_words and len(unique_words) == len(all_words) and data.get("no_repeat_words"):
        score += 20; reasons.append("No repeated words across the book")
    else:
        reasons.append("Repeat-free claim needs a full word check")
    fit = safety.get("topic_fit")
    if isinstance(fit, int):
        if fit >= 85:
            score += 22; reasons.append(f"Strong topic match ({fit}%)")
        elif fit >= 70:
            score += 14; reasons.append(f"Good topic match ({fit}%)")
        else:
            score -= 28; reasons.append(f"Topic match is too low ({fit}%); rebuild this word bank")
    else:
        score -= 8; reasons.append("Topic match needs a clean-source review")
    direct_fit, _rule = direct_topic_fit_report(data)
    if direct_fit is not None and direct_fit < 70:
        score -= 22; reasons.append(f"Independent topic check is only {direct_fit}%")
    if safety.get("review_words"):
        score -= 35; reasons.append("Contains names needing rights review")
    capacities = library.get("topic_capacities", {}) if isinstance(library, dict) else {}
    expected = safety.get("expected_topics", [])
    capacity = max((int(capacities.get(str(topic), {}).get("unique_words", 0)) for topic in expected), default=0)
    needed = len(all_words)
    if needed and capacity >= needed:
        score += 13; reasons.append("Clean library is large enough for this word count")
    elif needed:
        score -= 12; reasons.append(f"Clean source has {capacity} words; this book needs {needed}")
    hint = " ".join(str(data.get(key) or "") for key in ("title", "detected_topic", "series")).casefold()
    for terms, bonus in LAUNCH_DEMAND_HINTS:
        if any(term in hint for term in terms):
            score += bonus; break
    score = max(0, min(100, score))
    label = "MAKE NEXT" if score >= 75 else "PROMISING — REVIEW" if score >= 55 else "REBUILD WORD BANK"
    return score, label, reasons


class QualityReportDialog(tk.Toplevel):
    """Simple, readable display for the pre-generation quality check."""

    def __init__(self, parent: tk.Tk, title: str, errors: list[str], warnings: list[str], notes: list[str]) -> None:
        super().__init__(parent)
        self.title(title)
        self.geometry("690x470")
        self.minsize(620, 400)
        self.transient(parent)
        self.grab_set()
        frame = ttk.Frame(self, padding=18)
        frame.pack(fill="both", expand=True)
        ready = not errors
        ttk.Label(
            frame,
            text="READY TO GENERATE" if ready else "NEEDS ATTENTION",
            font=("Segoe UI", 17, "bold"),
            foreground="#245b2a" if ready else "#a33a1d",
        ).pack(anchor="w")
        summary = "No blocking issues were found." if ready else f"{len(errors)} issue(s) must be fixed before generating."
        if warnings:
            summary += f" There {'is' if len(warnings) == 1 else 'are'} also {len(warnings)} note(s) to review."
        ttk.Label(frame, text=summary, wraplength=630, foreground="#555555").pack(anchor="w", pady=(4, 12))
        report = ScrolledText(frame, wrap="word", height=18, font=("Segoe UI", 10))
        report.pack(fill="both", expand=True)
        for label, items in (("Problems", errors), ("Review notes", warnings), ("Check details", notes)):
            if items:
                report.insert("end", label.upper() + "\n")
                for item in items:
                    report.insert("end", f"• {item}\n")
                report.insert("end", "\n")
        report.configure(state="disabled")
        ttk.Button(frame, text="Close", command=self.destroy).pack(anchor="e", pady=(12, 0))


class SmartContentQualityDialog(tk.Toplevel):
    """Explain a book's buyer-facing content strength without technical jargon."""

    def __init__(self, parent: "WordSearchCreator") -> None:
        super().__init__(parent)
        self.parent = parent
        self.title("Book Quality Score")
        self.geometry("720x520")
        self.minsize(620, 420)
        self.transient(parent)
        self.grab_set()
        frame = ttk.Frame(self, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="BOOK QUALITY SCORE", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        self.summary = ttk.Label(frame, wraplength=660, foreground="#555555")
        self.summary.pack(anchor="w", pady=(5, 12))
        self.report = ScrolledText(frame, wrap="word", height=19, font=("Segoe UI", 10))
        self.report.pack(fill="both", expand=True)
        actions = ttk.Frame(frame); actions.pack(fill="x", pady=(12, 0))
        ttk.Button(actions, text="Series Differentiation", command=parent._open_series_differentiation, style="Action.TButton").pack(side="left")
        ttk.Button(actions, text="Close", command=self.destroy).pack(side="right")
        self._show_score()

    def _show_score(self) -> None:
        if not self.parent.selected_theme:
            self.summary.configure(text="Choose a saved theme first.", foreground="#a33a1d")
            return
        try:
            data = json.loads(self.parent.selected_theme.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            self.summary.configure(text=f"Could not read this saved theme: {exc}", foreground="#a33a1d")
            return
        score, label, strengths, improvements = content_quality_score(data)
        self.summary.configure(text=f"{score}/100 — {label}. This quick score checks the collection itself. The exact Book Quality Check still verifies every puzzle placement before package creation.", foreground="#245b4f" if score >= 75 else "#9a5b00")
        self.report.insert("end", "WHAT IS WORKING WELL\n")
        for item in strengths:
            self.report.insert("end", f"✓ {item}\n")
        self.report.insert("end", "\nWHAT TO DO NEXT\n")
        for item in improvements:
            self.report.insert("end", f"• {item}\n")
        self.report.insert("end", "\nPLAIN-ENGLISH GUIDE\n")
        self.report.insert("end", "This score looks at collection size, complete word lists, repeated words, buyer-facing details, and the automatic value pages. It does not replace a final visual review of the PDF or KDP Print Previewer.\n")
        self.report.configure(state="disabled")


class SeriesDifferentiationDialog(tk.Toplevel):
    """Turn similarity findings into a simple, fresh-companion next step."""

    def __init__(self, parent: "WordSearchCreator") -> None:
        super().__init__(parent)
        self.parent = parent
        self.title("Series Differentiation")
        self.geometry("760x540")
        self.minsize(640, 430)
        self.transient(parent)
        self.grab_set()
        frame = ttk.Frame(self, padding=18); frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="KEEP RELATED BOOKS DISTINCT", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(frame, text="This compares the selected book with your active library and suggests a fresh direction. It never changes any existing book.", foreground="#555555", wraplength=700).pack(anchor="w", pady=(4, 12))
        self.report = ScrolledText(frame, wrap="word", height=19, font=("Segoe UI", 10)); self.report.pack(fill="both", expand=True)
        self._show_plan()
        actions = ttk.Frame(frame); actions.pack(fill="x", pady=(12, 0))
        ttk.Button(actions, text="Create Fresh Series Companion", command=self._open_companion, style="Primary.TButton").pack(side="left")
        ttk.Button(actions, text="Close", command=self.destroy, style="Action.TButton").pack(side="right")

    def _show_plan(self) -> None:
        if not self.parent.selected_theme:
            self.report.insert("end", "Choose a saved theme first."); self.report.configure(state="disabled"); return
        try:
            data = json.loads(self.parent.selected_theme.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            self.report.insert("end", f"Could not read the selected book: {exc}"); self.report.configure(state="disabled"); return
        matches = cross_book_similarity_report(self.parent.selected_theme, data)
        self.report.insert("end", "CLOSEST BOOKS IN YOUR LIBRARY\n")
        if matches:
            for match in matches[:5]:
                status = "Intentional Signature pair" if match["level"] == "paired" else ("Needs a new word bank" if match["level"] == "block" else "Review before publishing both")
                self.report.insert("end", f"• {match['title']} — {float(match['overlap']):.0%} shared vocabulary ({status})\n")
        else:
            self.report.insert("end", "• No closely overlapping active book was found.\n")
        self.report.insert("end", "\nA FRESHER NEXT BOOK\n")
        for suggestion in differentiation_suggestions(data, matches):
            self.report.insert("end", f"• {suggestion}\n")
        self.report.insert("end", "\nUse the button below to open Series Expansion with this book already chosen. Import or select a genuinely fresh word bank before creating the companion.")
        self.report.configure(state="disabled")

    def _open_companion(self) -> None:
        self.destroy()
        SeriesExpansionDialog(self.parent, initial_source=self.parent.selected_theme)


class CoverPhotoPickerDialog(tk.Toplevel):
    """A simple, visual choice between the best topic-matched photo covers."""

    def __init__(self, parent: "WordSearchCreator", data: dict) -> None:
        super().__init__(parent)
        self.parent = parent
        self.data = data
        self.title("Choose a Cover Background")
        self.geometry("980x610")
        self.minsize(760, 520)
        self.transient(parent)
        self.grab_set()
        self.images: list[ImageTk.PhotoImage] = []
        self._build()

    def _build(self) -> None:
        outer = ttk.Frame(self, padding=18)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="CHOOSE A COVER BACKGROUND", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(outer, text="These are the best matches for this book. Pick one, or keep the automatic choice. The faded word-search grid is added when you create the cover.", foreground="#555555", wraplength=880).pack(anchor="w", pady=(4, 14))
        choices = background_photo_choices(self.data)
        if not choices:
            ttk.Label(outer, text="No matching photo backgrounds are saved for this topic yet. You can still choose a picture from your computer or use free CC0 artwork.", wraplength=820).pack(anchor="w", pady=20)
            ttk.Button(outer, text="Close", command=self.destroy, style="Action.TButton").pack(anchor="e", pady=(20, 0))
            return
        cards = ttk.Frame(outer)
        cards.pack(fill="both", expand=True)
        for index, choice in enumerate(choices[:3]):
            card = ttk.Labelframe(cards, text=f"Option {index + 1}", padding=10)
            card.grid(row=0, column=index, sticky="nsew", padx=(0 if index == 0 else 8, 0))
            cards.columnconfigure(index, weight=1)
            path = APP_DIR / str(choice["file"])
            try:
                image = Image.open(path); image.thumbnail((250, 350), Image.LANCZOS)
                photo = ImageTk.PhotoImage(image); self.images.append(photo)
                ttk.Label(card, image=photo).pack(pady=(0, 8))
            except OSError:
                ttk.Label(card, text="Preview unavailable", width=28).pack(pady=100)
            palette = photo_choice_palette(choice)
            ttk.Label(card, text=f"{choice.get('name', path.stem)}\nBest colors: {palette.replace('-', ' ').title()}", wraplength=240, justify="center").pack(pady=(0, 8))
            ttk.Button(card, text="Use This Background", command=lambda item=choice: self._choose(item), style="Primary.TButton").pack(fill="x")
        actions = ttk.Frame(outer); actions.pack(fill="x", pady=(14, 0))
        ttk.Button(actions, text="Keep Automatic Choice", command=self.destroy, style="Action.TButton").pack(side="right")

    def _choose(self, choice: dict[str, object]) -> None:
        self.parent._use_photo_choice(choice)
        self.destroy()


class BuyerPreviewDialog(tk.Toplevel):
    """The last, simple buyer-view checkpoint before a complete package is made."""

    def __init__(self, parent: "WordSearchCreator", settings: dict[str, str], seed: int) -> None:
        super().__init__(parent)
        self.parent = parent
        self.settings = settings
        self.seed = seed
        self.archive_choice = tk.BooleanVar(value=bool(settings.get("archive_after_package")))
        self.signature_choice = tk.BooleanVar(value=signature_requested(settings))
        self.title("Final Book Review")
        self.geometry("980x680")
        self.minsize(760, 560)
        self.transient(parent)
        self.grab_set()
        self.preview_image: ImageTk.PhotoImage | None = None
        self._build()
        self.after(80, self._render_preview)

    def _build(self) -> None:
        outer = ttk.Frame(self, padding=18)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=3); outer.columnconfigure(1, weight=2)
        outer.rowconfigure(1, weight=1)
        ttk.Label(outer, text="FINAL BOOK REVIEW", font=("Segoe UI", 19, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")
        left = ttk.Frame(outer); left.grid(row=1, column=0, sticky="nsew", padx=(0, 18), pady=(12, 0))
        right = ttk.Labelframe(outer, text="BUYER COVER PREVIEW", padding=10); right.grid(row=1, column=1, sticky="nsew", pady=(12, 0))
        ttk.Label(right, text="Creating your cover preview…", foreground="#555555").pack(anchor="center", pady=15)
        self.cover_holder = ttk.Label(right)
        self.cover_holder.pack(fill="both", expand=True)
        try:
            data = json.loads(Path(self.settings["theme"]).read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            data = {}
        package_data = package_data_from_settings(data, self.settings)
        score, label, strengths, improvements = content_quality_score(package_data)
        pages = estimated_page_count(package_data)
        price, _ = recommended_us_paperback_price(pages, signature_requested(self.settings))
        difficulty = puzzle_difficulty_label(data)
        topic = str(data.get("detected_topic") or data.get("series") or "Themed collection")
        word_count = sum(len(puzzle.get("words", [])) for puzzle in data.get("puzzles", []) if isinstance(puzzle, dict))
        picture = Path(self.settings.get("art") or "").name or "No picture selected"
        listing_note = "KDP listing copy, keywords, suggested price, and upload checklist will be included in the finished package."
        summary = (
            f"TITLE\n{self.settings['title']}\n\n"
            f"SUBTITLE\n{self.settings['subtitle'] or 'Word Search Collection'}\n\n"
            f"Difficulty: {difficulty}   •   Puzzles: {len(data.get('puzzles', []))}   •   Words: {word_count}\n"
            f"Interior: about {pages} pages   •   Suggested US price: ${price:.2f}\n"
            f"Cover: {self.settings['palette'].replace('-', ' ').title()} colors, {self.settings['style'].replace('-', ' ').title()} layout\n"
            f"Background: {picture}\n"
            f"Package folder: Word Search Creator\\out\\{WordSearchCreator._safe_filename(self.settings['title'])}_date-time\n\n"
            f"LISTING SNAPSHOT\n{listing_note}\n\n"
            f"BUYER-READY SCORE: {score}/100 — {label}\n\n"
            "Strong points:\n" + "\n".join(f"• {item}" for item in strengths[:4]) +
            "\n\nBefore publishing:\n" + "\n".join(f"• {item}" for item in improvements[:2])
        )
        ttk.Label(left, text=summary, justify="left", wraplength=500, font=("Segoe UI", 10)).pack(anchor="nw", fill="both", expand=True)
        publishing = ttk.Labelframe(outer, text="PUBLISHING CHOICES", padding=(10, 7)); publishing.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        ttk.Checkbutton(publishing, text="Make this a 100-puzzle Signature Edition (adds the Passport and achievement pages)", variable=self.signature_choice).pack(anchor="w")
        ttk.Checkbutton(publishing, text="After a successful package, move this theme to Used Themes", variable=self.archive_choice).pack(anchor="w", pady=(4, 0))
        actions = ttk.Frame(outer); actions.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(16, 0)); actions.columnconfigure(0, weight=1); actions.columnconfigure(1, weight=1); actions.columnconfigure(2, weight=1)
        ttk.Button(actions, text="Book Quality Score", command=lambda: SmartContentQualityDialog(self.parent), style="Action.TButton").grid(row=0, column=0, sticky="ew", padx=(0, 5))
        ttk.Button(actions, text="Back to Edit", command=self.destroy, style="Action.TButton").grid(row=0, column=1, sticky="ew", padx=5)
        ttk.Button(actions, text="Approve & Create Complete Package", command=self._create, style="Primary.TButton").grid(row=0, column=2, sticky="ew", padx=(5, 0))

    def _render_preview(self) -> None:
        # Preview images are temporary. Only completed packages belong in out.
        output_dir = Path(tempfile.gettempdir()) / "Word Search Creator" / "buyer_previews"; output_dir.mkdir(parents=True, exist_ok=True)
        output = output_dir / f"{WordSearchCreator._safe_filename(self.settings['title'])}_buyer_preview.png"
        threading.Thread(target=self._run_preview, args=(output,), daemon=True).start()

    def _run_preview(self, output: Path) -> None:
        python = WINDOWS_VENV_PYTHON if WINDOWS_VENV_PYTHON.exists() else Path(sys.executable)
        command = [str(python), str(COVER_ENGINE), "--title", self.settings["title"], "--subtitle", self.settings["subtitle"], "--author", self.settings["author"], "--badge", self.settings["badge"], "--puzzle-count", str(self.settings.get("puzzle_count", 0)), "--difficulty", self.settings["difficulty"], "--format-label", self.settings.get("format_label", "WORD SEARCH"), "--palette", self.settings["palette"], "--style", self.settings["style"], "--theme-file", self.settings["theme"], "--out", str(output), "--preview"]
        if self.settings.get("art"):
            command.extend(["--art", self.settings["art"], "--art-focus", self.settings.get("art_focus", "center")])
        try:
            result = subprocess.run(command, cwd=APP_DIR, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode:
                raise RuntimeError(result.stderr.strip() or result.stdout.strip())
            self.after(0, self._show_preview, output)
        except Exception as exc:
            self.after(0, lambda: self.cover_holder.configure(text=f"Cover preview could not be shown.\n{exc}", foreground="#a33a1d", wraplength=280))

    def _show_preview(self, output: Path) -> None:
        try:
            image = Image.open(output); image.thumbnail((300, 390), Image.LANCZOS)
            self.preview_image = ImageTk.PhotoImage(image)
            self.cover_holder.configure(image=self.preview_image, text="")
        except OSError as exc:
            self.cover_holder.configure(text=f"Cover preview could not be shown.\n{exc}", foreground="#a33a1d")

    def _create(self) -> None:
        self.settings["archive_after_package"] = self.archive_choice.get()
        self.settings["signature_edition"] = self.signature_choice.get()
        self.destroy()
        self.parent._generate_studio_package(skip_buyer_preview=True, prepared_settings=self.settings, prepared_seed=self.seed)


def publish_ready_preflight(path: Path, seed: int, title: str, subtitle: str, author: str,
                            palette: str, style_label: str, badge: str, art_path: str) -> tuple[list[str], list[str], list[tuple[str, bool, str]]]:
    """Run the complete, no-write readiness check used by the Publish Ready dashboard."""
    errors, warnings, _notes = quality_gate(path, seed)
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return errors, warnings, []
    package_data = package_data_from_settings(data, {"title": title, "subtitle": subtitle, "author": author, "palette": palette, "style": PublishReadyDialog.STYLE_MAP.get(style_label, style_label), "badge": badge})
    warnings.extend(publisher_safety_report(package_data)["warnings"])
    contributor_errors = contributor_safety_notes(author)
    errors.extend(contributor_errors)

    checks: list[tuple[str, bool, str]] = []
    checks.append(("Puzzle placement and unique words", not errors,
                   "Every word was placed and no word repeats across the book." if not errors else "Fix the blocking book-quality issue(s) below."))
    contributor_ok = bool(title.strip() and author.strip()) and not contributor_errors
    checks.append(("Book details and contributor", contributor_ok,
                   "Title is present and the contributor is a person/pen name, not the Slade Puzzles brand." if contributor_ok else "Add a title and a real contributor or pen name. Keep Slade Puzzles as the brand, not the author."))
    if len(title.strip()) > 60:
        warnings.append("Cover/listing title is over 60 characters. Shorten it for stronger thumbnail and search-result readability.")
    if len(subtitle.strip()) > 120:
        warnings.append("Subtitle is over 120 characters. Shorten it so the cover stays easy to read.")

    difficulty = puzzle_difficulty_label(data)
    badge_ok = "NO REPEATED" in badge.upper()
    checks.append(("Cover promise and difficulty", badge_ok,
                   f"Difficulty marker: {difficulty}. No-repeat badge is ready." if badge_ok else f"Difficulty marker: {difficulty}. Set the cover badge to ‘NO REPEATED WORDS’."))

    style_value = PublishReadyDialog.STYLE_MAP.get(style_label, "")
    cover_ok = palette in CoverCreatorDialog.PALETTES and bool(style_value)
    photo_note = ""
    if style_value == "photo" and (not art_path.strip() or not Path(art_path).exists()):
        # The Studio will automatically choose a matching local background, or
        # safely switch to an illustrated cover when no match exists.
        photo_note = " Photo Hero will choose a matching local image automatically."
    checks.append(("Cover setup", cover_ok,
                   ("Palette and layout are ready for cover generation." + photo_note) if cover_ok else "Choose a valid palette and layout."))

    listing = listing_kit_text(package_data)
    listing_ok = "No repeated words across the book." in listing and difficulty in listing
    checks.append(("KDP listing kit", listing_ok,
                   "Includes puzzle count, difficulty, price estimate, and the no-repeat promise." if listing_ok else "Regenerate the listing kit after fixing its book details."))

    pages = estimated_page_count(data)
    checks.append(("KDP wrap preparation", pages >= 24,
                   f"Estimated {pages} interior pages. {spine_safety_note(pages)}" if pages >= 24 else "Book is below the minimum expected paperback page count."))
    checks.append(("Final KDP review", True,
                   "The package will still remind you to run KDP Print Previewer before upload."))
    return errors, warnings, checks


class PublishReadyDashboard(tk.Toplevel):
    """One plain-English, automatic preflight screen before package creation."""

    def __init__(self, parent: "WordSearchCreator") -> None:
        super().__init__(parent)
        self.parent = parent
        self.title("Publish Ready Check")
        self.geometry("760x600")
        self.minsize(650, 500)
        self.transient(parent)
        self.grab_set()
        frame = ttk.Frame(self, padding=18)
        frame.pack(fill="both", expand=True)
        self.heading = ttk.Label(frame, text="PUBLISH READY CHECK", font=("Segoe UI", 18, "bold"))
        self.heading.pack(anchor="w")
        self.summary = ttk.Label(frame, text="Checking your book automatically…", foreground="#555555", wraplength=700)
        self.summary.pack(anchor="w", pady=(4, 12))
        self.report = ScrolledText(frame, wrap="word", height=21, font=("Segoe UI", 10))
        self.report.pack(fill="both", expand=True)
        actions = ttk.Frame(frame); actions.pack(fill="x", pady=(12, 0))
        self.recheck = ttk.Button(actions, text="Run Check Again", command=self.run_check, style="Action.TButton")
        self.recheck.pack(side="left")
        self.package = ttk.Button(actions, text="Create Complete Package", command=self.create_package, state="disabled", style="Primary.TButton")
        self.package.pack(side="right")
        self.after(50, self.run_check)

    def run_check(self) -> None:
        if not self.parent.selected_theme:
            self.summary.configure(text="Choose a theme in Book Studio first.", foreground="#a33a1d")
            return
        try:
            seed = int(self.parent.seed.get())
        except ValueError:
            self.summary.configure(text="Grid seed must be a whole number.", foreground="#a33a1d")
            return
        self.recheck.configure(state="disabled"); self.package.configure(state="disabled")
        self.summary.configure(text="Checking every puzzle, the cover setup, KDP listing details, and package preparation…", foreground="#555555")
        settings = (self.parent.selected_theme, seed, self.parent.book_title.get(), self.parent.subtitle.get(), self.parent.author.get(), self.parent.cover_palette.get(), self.parent.cover_style.get(), self.parent.cover_badge.get(), self.parent.cover_art.get())
        threading.Thread(target=self._run_check, args=settings, daemon=True).start()

    def _run_check(self, path: Path, seed: int, title: str, subtitle: str, author: str, palette: str, style: str, badge: str, art: str) -> None:
        errors, warnings, checks = publish_ready_preflight(path, seed, title, subtitle, author, palette, style, badge, art)
        self.after(0, self._show_result, errors, warnings, checks)

    def _show_result(self, errors: list[str], warnings: list[str], checks: list[tuple[str, bool, str]]) -> None:
        self.recheck.configure(state="normal")
        ready = not errors and all(ok for _label, ok, _detail in checks)
        self.heading.configure(text="PUBLISH READY" if ready else "NEEDS ATTENTION", foreground="#245b2a" if ready else "#a33a1d")
        self.summary.configure(text="Everything required for package creation is ready." if ready else "Fix the red items below, then run this check again.", foreground="#245b2a" if ready else "#a33a1d")
        self.report.configure(state="normal"); self.report.delete("1.0", "end")
        for label, ok, detail in checks:
            self.report.insert("end", f"{'✓' if ok else '✗'}  {label}\n    {detail}\n\n")
        if errors:
            self.report.insert("end", "BLOCKING FIXES\n")
            for error in errors: self.report.insert("end", f"• {error}\n")
            self.report.insert("end", "\n")
        if warnings:
            self.report.insert("end", "REVIEW NOTES\n")
            for warning in warnings: self.report.insert("end", f"• {warning}\n")
        self.report.configure(state="disabled")
        if ready:
            self.package.configure(state="normal")

    def create_package(self) -> None:
        self.destroy()
        self.parent._generate_studio_package()


class WordIntelligenceCenterDialog(tk.Toplevel):
    """Plain-English control room for the word→topic intelligence layer.

    Every long job (classification, theme audits, report writing) runs in a
    daemon thread and posts back through ``self.after`` so the interface
    never freezes. Views are read-only except for two explicitly confirmed
    actions: running the classifier (which only proposes links for review)
    and writing the curated approved-links source consumed by the bank
    builder (snapshotted and validated by the apply engine).
    """

    def __init__(self, parent: "WordSearchCreator") -> None:
        super().__init__(parent)
        self.title("Word Intelligence Center")
        self.geometry("860x640")
        self.minsize(700, 500)
        self.transient(parent)
        self.parent = parent
        self._busy = False
        frame = ttk.Frame(self, padding=18); frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="WORD INTELLIGENCE CENTER", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(
            frame,
            text="See how well every word is matched to its topic, review suggested matches, "
                 "and check theme quality. Suggestions never change your books until a human approves them.",
            foreground="#555555", wraplength=780).pack(anchor="w", pady=(3, 12))
        self.report = ScrolledText(frame, wrap="word", height=24, font=("Segoe UI", 10))
        self.report.pack(fill="both", expand=True)
        actions = ttk.Frame(frame); actions.pack(fill="x", pady=(12, 0))
        left = ttk.Frame(actions); left.pack(side="left")
        ttk.Button(left, text="Refresh Overview", command=self._show_overview, style="Primary.TButton").pack(side="left")
        ttk.Button(left, text="Run Classifier", command=self._run_classifier, style="Action.TButton").pack(side="left", padx=8)
        add_hover_help(self._button(left, "Topic Health", self._show_topic_health),
                       "Grades every topic by how many trustworthy words it can draw on, so you can spot thin topics before planning a book.")
        self._button(left, "Review Queue", self._show_review_queue).pack(side="left", padx=(8, 0))
        add_hover_help(self._button(left, "Unclassified", self._show_unclassified),
                       "Words with no topic yet - the frontier for future books and packs.")
        right = ttk.Frame(actions); right.pack(side="right")
        ttk.Button(right, text="Theme Quality Audit", command=self._run_theme_audit, style="Action.TButton").pack(side="left")
        ttk.Button(right, text="Write Curated Links…", command=self._apply_links, style="Action.TButton").pack(side="left", padx=8)
        add_hover_help(right.winfo_children()[-1],
                       "Saves the matches you approved into the word bank's curated source file. A backup snapshot is taken first.")
        # PART P clipboard usability: reports should leave this window the
        # normal way (a button), not via terminal-style Ctrl+C habits.
        # Clipboard calls always run here on the Tk/UI thread.
        self._button(right, "Copy Report", self._copy_report).pack(side="left", padx=(8, 0))
        add_hover_help(right.winfo_children()[-1],
                       "Copies everything shown above so you can paste it into email, a checklist, or a spreadsheet.")
        self.after(50, self._show_overview)

    def _copy_report(self) -> None:
        """Copy the visible report to the clipboard (UI thread only)."""
        try:
            text = self.report.get("1.0", "end-1c")
            self.clipboard_clear()
            self.clipboard_append(text)
            self.update_idletasks()
            self.parent.status.set("Report copied to clipboard")
        except tk.TclError as exc:
            self.parent.status.set(f"Copy failed: {exc}")

    # ------------------------------------------------------------------
    # Plumbing
    # ------------------------------------------------------------------

    def _button(self, parent, text, command) -> ttk.Button:
        button = ttk.Button(parent, text=text, command=command, style="Action.TButton")
        button.pack(side="left")
        return button

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        for child in self.winfo_children():
            if isinstance(child, ttk.Frame):
                for button in child.winfo_children():
                    if isinstance(button, ttk.Frame):
                        for sub in button.winfo_children():
                            if isinstance(sub, ttk.Button):
                                sub.configure(state=state)

    def _write(self, text: str) -> None:
        self.report.configure(state="normal")
        self.report.delete("1.0", "end")
        self.report.insert("1.0", text)
        self.report.configure(state="disabled")

    def _dispatch(self, label: str, worker, done) -> None:
        """Run a job off the UI thread; results return via self.after."""
        if getattr(self, "_busy", False):
            return
        self._set_busy(True)
        self.parent.status.set(f"{label}…")

        def runner() -> None:
            try:
                payload = worker()
                ok, error = True, ""
            except Exception as exc:  # surface any failure in the report pane
                payload, ok, error = None, False, f"{type(exc).__name__}: {exc}"
            self.after(0, lambda: done(ok, payload, error))

        threading.Thread(target=runner, daemon=True).start()

    def _finish(self, label: str, ok: bool, error: str) -> None:
        if not self.winfo_exists():
            return
        self._set_busy(False)
        self.parent.status.set(label if ok else f"{label} failed: {error}")

    @staticmethod
    def _load_intelligence():
        from word_intelligence import pipeline
        root = Path(__file__).resolve().parent
        taxonomy = pipeline.load_taxonomy(root)
        store, _ = pipeline.load_or_build_store(root, taxonomy=taxonomy)
        return taxonomy, store

    # ------------------------------------------------------------------
    # Views
    # ------------------------------------------------------------------

    def _show_overview(self) -> None:
        def worker():
            _, store = self._load_intelligence()
            from word_intelligence.analysis import coverage_summary
            return coverage_summary(store)

        def done(ok, coverage, error):
            if not self.winfo_exists():
                return
            if ok:
                lines = [
                    "WORD LIBRARY AT A GLANCE",
                    "=" * 46,
                    f"Words tracked:            {coverage['total_records']:,}",
                    f"Confirmed topic matches:  {coverage['confirmed_records']:,}",
                    f"Waiting for your review:  {coverage['open_proposals']:,}",
                    f"No topic decided yet:     {coverage['unclassified_records']:,}",
                    f"Trademark watch list:     {coverage['trademark_review']:,}",
                    "",
                    "SUGGESTIONS BY CONFIDENCE",
                    *[f"  {band:<10} {count:,}" for band, count in coverage["proposal_bands"].items()],
                    "",
                    "Suggestions are ideas, not decisions. Open Review Queue to accept or reject them.",
                ]
                self._write("\n".join(lines))
            else:
                self._write(f"Could not load the word library.\n\n{error}")
            self._finish("Word library overview ready", ok, error)

        self._dispatch("Loading word library overview", worker, done)

    def _run_classifier(self) -> None:
        def worker():
            taxonomy, store = self._load_intelligence()
            from word_intelligence import pipeline
            catalog = pipeline.load_candidate_catalog(Path(__file__).resolve().parent)
            classifier, stats, summary = pipeline.run_classification(
                store, taxonomy, catalog=catalog, scope="proven")
            pipeline.save_store_quietly(store, Path(__file__).resolve().parent)
            return stats.to_dict()

        def done(ok, stats, error):
            if not self.winfo_exists():
                return
            if ok:
                lines = [
                    "CLASSIFIER RUN COMPLETE",
                    "=" * 46,
                    f"Words examined:      {stats.get('words_seen', 0):,}",
                    f"Words classified:    {stats.get('words_classified', 0):,}",
                    f"Suggestions filed:   {stats.get('proposals', 0):,}",
                    f"  very high:         {stats.get('very_high', 0):,}",
                    f"  high:              {stats.get('high', 0):,}",
                    f"  medium:            {stats.get('medium', 0):,}",
                    f"Ambiguity flags:     {stats.get('ambiguous_words', 0):,}",
                    "", "Open Topic Health or Review Queue to see what changed.",
                ]
                self._write("\n".join(lines))
            else:
                self._write(f"The classifier could not finish.\n\n{error}")
            self._finish("Classifier finished - suggestions are ready for review", ok, error)

        self._dispatch("Running the topic classifier", worker, done)

    def _show_topic_health(self) -> None:
        def worker():
            taxonomy, store = self._load_intelligence()
            from word_intelligence.analysis import topic_health
            return topic_health(store, taxonomy)[:40]

        def done(ok, rows, error):
            if not self.winfo_exists():
                return
            if ok:
                lines = ["TOPIC HEALTH (weakest first, top 40 shown)", "=" * 46,
                         f"{'GRADE':<6}{'WORDS':>7}  {'TOPIC':<34}FAMILY",
                         "-" * 78]
                for row in rows:
                    lines.append(f"{row['grade']:<6}{row['usable_words']:>7}  "
                                 f"{row['display_name']:<34}{row['family']}")
                lines += ["", "Grade A topics are book-ready. D and F need vocabulary growth first."]
                self._write("\n".join(lines))
            else:
                self._write(f"Could not grade the topics.\n\n{error}")
            self._finish("Topic health report ready", ok, error)

        self._dispatch("Grading topic health", worker, done)

    def _show_review_queue(self) -> None:
        def worker():
            _, store = self._load_intelligence()
            from word_intelligence.review import seed_review_queue
            queue = seed_review_queue(store)
            items = queue.open_items()
            state_dir = Path(__file__).resolve().parent / "word_banks" / "word_intelligence"
            queue.save(state_dir)
            return [(i.word, i.topic_id, i.confidence, i.reason) for i in items]

        def done(ok, items, error):
            if not self.winfo_exists():
                return
            if ok:
                lines = [f"REVIEW QUEUE ({len(items)} suggestion(s))", "=" * 46]
                for word, topic_id, confidence, reason in items[:250]:
                    lines.append(f"  {word:<18} -> {topic_id:<28} {confidence:>5.1f}  {reason[:44]}")
                if len(items) > 250:
                    lines.append(f"  … and {len(items) - 250} more (full list saved to review_queue.json)")
                self._write("\n".join(lines))
            else:
                self._write(f"Could not build the review queue.\n\n{error}")
            self._finish("Review queue ready", ok, error)

        self._dispatch("Collecting review suggestions", worker, done)

    def _show_unclassified(self) -> None:
        def worker():
            _, store = self._load_intelligence()
            from word_intelligence.reports import unclassified_preview
            return unclassified_preview(store, limit=300)

        def done(ok, words, error):
            if not self.winfo_exists():
                return
            if ok:
                lines = [f"UNCLASSIFIED WORDS ({len(words)} shown)", "=" * 46]
                lines += [f"  {word}" for word in words]
                self._write("\n".join(lines))
            else:
                self._write(f"Could not list unclassified words.\n\n{error}")
            self._finish("Unclassified preview ready", ok, error)

        self._dispatch("Listing unclassified words", worker, done)

    def _run_theme_audit(self) -> None:
        def worker():
            taxonomy, store = self._load_intelligence()
            from word_intelligence.theme_audit import audit_all_themes
            themes_dir = Path(__file__).resolve().parent / "themes"
            return audit_all_themes(str(themes_dir), store, taxonomy), None

        def done(ok, payload, error):
            if not self.winfo_exists():
                return
            if ok:
                summary, _ = payload
                d = summary["verdict_counts"]
                lines = [
                    "THEME QUALITY AUDIT",
                    "=" * 46,
                    f"Themes checked: {summary['audited']} of {summary['themes_scanned']}",
                    f"  PASS:             {d.get('PASS', 0)}",
                    f"  PASS with notes:  {d.get('PASS_WITH_NOTES', 0)}",
                    f"  FAIL (review):    {d.get('FAIL', 0)}",
                    "", "Worst offenders:",
                ]
                fails = [r for r in summary["reports"] if r.verdict == "FAIL"]
                fails.sort(key=lambda r: -(r.to_dict()["counts"].get("off_topic", 0)
                                           + r.to_dict()["counts"].get("flagged", 0)))
                for report in fails[:12]:
                    counts = report.to_dict()["counts"]
                    name = Path(report.theme_file).name
                    lines.append(f"  {name}: {counts.get('off_topic', 0)} off-topic, "
                                 f"{counts.get('flagged', 0)} flagged")
                full = sorted((Path(__file__).resolve().parent / "out").glob(
                    "*theme_quality*.json"))
                if full:
                    lines += ["", f"Full details: {full[-1].name}"]
                self._write("\n".join(lines))
            else:
                self._write(f"The theme audit could not finish.\n\n{error}")
            self._finish("Theme quality audit finished", ok, error)

        self._dispatch("Auditing every theme (this can take about a minute)", worker, done)

    def _apply_links(self) -> None:
        plan_ok = messagebox.askyesno(
            "Write Curated Links",
            "This saves your approved word-topic matches into the word bank's\n"
            "curated source file (approved_topic_links.json).\n\n"
            "A timestamped backup snapshot is created first, and bank rebuilds\n"
            "re-use these decisions automatically.\n\nContinue?",
            parent=self)
        if not plan_ok:
            return

        def worker():
            taxonomy, store = self._load_intelligence()
            from word_intelligence.apply_engine import apply_approved_links
            result = apply_approved_links(store, project_root=Path(__file__).resolve().parent,
                                          dry_run=False, taxonomy=taxonomy)
            return result

        def done(ok, result, error):
            if not self.winfo_exists():
                return
            if ok and result.validated:
                self._write(
                    "CURATED LINKS SAVED\n" + "=" * 46 +
                    f"\nApproved pairs written: {result.approved_words}"
                    f"\nBackup snapshot: {result.snapshot_dir}"
                    "\n\nBank rebuilds will now re-apply these decisions automatically.")
            else:
                message = error or "; ".join(result.errors)
                self._write(f"Could not save curated links.\n\n{message}")
            self._finish("Curated links saved", ok and result.validated,
                         error or "; ".join(result.errors))

        self._dispatch("Saving curated links", worker, done)


class WordBankHealthDialog(tk.Toplevel):
    """One plain-English home for library capacity, review items, and provenance."""

    def __init__(self, parent: "WordSearchCreator") -> None:
        super().__init__(parent)
        self.title("Library & Quality Center")
        self.geometry("790x610")
        self.minsize(620, 460)
        self.transient(parent)
        frame = ttk.Frame(self, padding=18); frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="LIBRARY & QUALITY CENTER", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(frame, text="One plain-English home for book capacity, topic fit, dictionary checks, and review reminders. Refreshing reports never edits a theme or creates a book.", foreground="#555555", wraplength=720).pack(anchor="w", pady=(3, 12))
        self.report = ScrolledText(frame, wrap="word", height=23, font=("Segoe UI", 10)); self.report.pack(fill="both", expand=True)
        self._build_report(parent)
        actions = ttk.Frame(frame); actions.pack(fill="x", pady=(12, 0))
        ttk.Button(actions, text="Refresh Library Intelligence", command=self._refresh_intelligence, style="Primary.TButton").pack(side="left")
        ttk.Button(actions, text="Run Quick Audit", command=self._run_audit, style="Action.TButton").pack(side="left", padx=8)
        ttk.Button(actions, text="Open Review Queue", command=self._open_review_queue, style="Action.TButton").pack(side="left")
        ttk.Button(actions, text="Close", command=self.destroy, style="Action.TButton").pack(side="right")

    def _build_report(self, parent: "WordSearchCreator") -> None:
        try:
            master = json.loads((WORD_BANKS_DIR / "Guided_Builder_Master_Word_Bank.json").read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            self.report.insert("end", "The Master Library could not be read. Use Refresh Smart Theme Scan, then try again.")
            self.report.configure(state="disabled"); return
        topics = master.get("topics", {}) if isinstance(master, dict) else {}
        used_by_topic: dict[str, set[str]] = {}
        for path in all_book_theme_files():
            try:
                data = json.loads(path.read_text(encoding="utf-8-sig"))
                topic = str(data.get("detected_topic") or "General Interest")
                words = {re.sub(r"[^A-Z]", "", str(word).upper()) for puzzle in data.get("puzzles", []) if isinstance(puzzle, dict) for word in puzzle.get("words", [])}
                used_by_topic.setdefault(topic, set()).update(word for word in words if word)
            except (OSError, json.JSONDecodeError):
                continue
        sources = master.get("source_records", {}) if isinstance(master, dict) else {}
        intelligence = library_intelligence_summary()
        self.report.insert("end", "WHAT THIS CHECKS\n• Capacity is based on clean unique words, so no-repeat promises remain honest.\n• Dictionary matches confirm spelling; they do not automatically prove a word belongs in a topic.\n• Review items are reminders, not automatic deletions.\n• Topic links help discovery; only focused packs should build a book.\n\n")
        self.report.insert("end", "CURRENT LIBRARY STATUS\n"
                           f"• {intelligence['ready_48']} topics are ready for a repeat-free 48-puzzle standard book.\n"
                           f"• {intelligence['ready_100']} topics are ready for a 100-puzzle Signature Edition.\n"
                           f"• {intelligence['needs_expansion']} topics are safely held for expansion instead of being padded with unrelated words.\n"
                           f"• {intelligence['dictionary_confirmed']:,} direct entries passed the local dictionary screen; {intelligence['review_terms']:,} specialist or compound terms remain visible for review.\n\n")
        if isinstance(sources, dict):
            self.report.insert("end", f"LIBRARY SOURCES\n• {len(sources)} recorded source groups. General dictionaries are spelling references only; they are never poured into a niche book automatically.\n\n")
        self.report.insert("end", "TOPIC CAPACITY\n\n")
        for topic, values in sorted(topics.items(), key=lambda item: str(item[0]).casefold()):
            available = {re.sub(r"[^A-Z]", "", str(word).upper()) for word in values if re.sub(r"[^A-Z]", "", str(word).upper())}
            used = used_by_topic.get(str(topic), set())
            remaining = len(available - used)
            twelve = remaining // 12; twenty = remaining // 20
            state = "HEALTHY" if remaining >= 240 else ("WATCH" if remaining >= 80 else "LOW")
            self.report.insert("end", f"{state:7}  {topic}\n  {remaining} fresh words estimated • about {twelve} 12-word puzzles or {twenty} 20-word puzzles remaining\n\n")
        selected_topic = ""
        if parent.selected_theme:
            try:
                selected_topic = str(json.loads(parent.selected_theme.read_text(encoding="utf-8-sig")).get("detected_topic") or "")
            except (OSError, json.JSONDecodeError):
                pass
        if selected_topic:
            self.report.insert("1.0", f"CURRENT BOOK TOPIC: {selected_topic}\n\n")
        self.report.configure(state="disabled")

    def _run_audit(self) -> None:
        snapshot, queue = run_library_audit()
        self.report.configure(state="normal")
        self.report.insert("1.0", "LATEST AUTOMATIC AUDIT\n"
                           f"• {snapshot['unique_words']} clean words across {snapshot['topic_count']} topics\n"
                           f"• {snapshot['topics_ready_for_48']} topics can make a 48-puzzle, 12-word no-repeat book\n"
                           f"• {snapshot['topics_ready_for_100']} topics can make a 100-puzzle, 12-word Signature book\n"
                           f"• {len(queue)} item(s) placed in the review queue\n\n")
        self.report.configure(state="disabled")
        self.parent.status.set("Library audit finished. It saved a dated health record and a review queue without changing any themes.")

    def _refresh_intelligence(self) -> None:
        self.report.configure(state="normal")
        self.report.insert("1.0", "Refreshing the Master Library and its safety reports…\n\n")
        self.report.configure(state="disabled")
        def worker() -> None:
            ok, message = refresh_library_intelligence()
            self.after(0, lambda: self._refresh_finished(ok, message))
        threading.Thread(target=worker, daemon=True).start()

    def _refresh_finished(self, ok: bool, message: str) -> None:
        if not self.winfo_exists():
            return
        if not ok:
            log_plain_error("Refresh Library Intelligence", "", message, "Open the Error Log, then run the project check before trying again.")
            messagebox.showerror("Library refresh could not finish", message, parent=self)
            return
        self.report.configure(state="normal"); self.report.delete("1.0", "end")
        self._build_report(self.parent)
        self.parent._refresh_library_summary()
        self.parent.status.set(message)

    def _open_review_queue(self) -> None:
        _snapshot, queue = run_library_audit()
        lines = ["WORD REVIEW QUEUE", "", "These are reminders for future library work. Nothing was removed automatically.", ""]
        if queue:
            lines.extend(f"• {item['topic']}: {item['reason']} {item['examples']}" for item in queue)
        else:
            lines.append("No review items were found.")
        dialog = tk.Toplevel(self); dialog.title("Word Review Queue"); dialog.geometry("760x520"); dialog.transient(self)
        report = ScrolledText(dialog, wrap="word", font=("Segoe UI", 10), padx=16, pady=16); report.pack(fill="both", expand=True)
        report.insert("1.0", "\n".join(lines)); report.configure(state="disabled")


class ThemeBuilderDialog(tk.Toplevel):
    """Create and edit the JSON theme files that power wordsearch.py."""

    def __init__(self, parent: "WordSearchCreator") -> None:
        super().__init__(parent)
        self.parent = parent
        self.title("Theme Builder")
        self.geometry("820x680")
        self.minsize(720, 560)
        self.transient(parent)
        self.grab_set()

        self.theme_title = tk.StringVar(value=parent.book_title.get())
        self.theme_subtitle = tk.StringVar(value=parent.subtitle.get())
        self.theme_author = tk.StringVar(value=parent.author.get())
        self.save_status = tk.StringVar(value="One line = one puzzle. Aim for 12 words per puzzle.")
        self._build()
        if parent.selected_theme:
            self.load_theme(parent.selected_theme)

    def _build(self) -> None:
        frame = scrollable_dialog_page(self, padding=18)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(5, weight=1)

        ttk.Label(frame, text="THEME BUILDER", font=("Segoe UI", 18, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w"
        )
        ttk.Label(
            frame,
            text="Create a reusable theme file. The Book Creator can generate a PDF from it immediately.",
            foreground="#555555",
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 15))

        self._field(frame, 2, "Book title", self.theme_title)
        self._field(frame, 3, "Subtitle", self.theme_subtitle)
        self._field(frame, 4, "Author", self.theme_author)

        ttk.Label(frame, text="Puzzles and words").grid(row=5, column=0, sticky="nw", pady=(12, 0))
        self.puzzles = ScrolledText(frame, wrap="word", font=("Consolas", 10), height=20)
        self.puzzles.grid(row=5, column=1, columnspan=2, sticky="nsew", padx=(12, 0), pady=(12, 0))

        help_text = (
            "Use one line for each puzzle:\n"
            "Puzzle Name | WORD ONE, WORD TWO, WORD THREE\n\n"
            "Words may include spaces or hyphens. Each word must have 21 letters or fewer."
        )
        ttk.Label(frame, text=help_text, foreground="#666666", justify="left", wraplength=180).grid(
            row=6, column=0, sticky="nw", pady=(8, 0)
        )

        buttons = ttk.Frame(frame)
        buttons.grid(row=6, column=1, columnspan=2, sticky="ew", pady=(8, 0))
        buttons.columnconfigure(4, weight=1)
        ttk.Button(buttons, text="Load Theme…", command=self.choose_theme).grid(row=0, column=0, padx=(0, 7))
        ttk.Button(buttons, text="Mix Themes…", command=self.open_mixer).grid(row=0, column=1, padx=(0, 7))
        ttk.Button(buttons, text="Start 48-Puzzle Book", command=self.make_outline).grid(row=0, column=2, padx=(0, 7))
        ttk.Button(buttons, text="Check Theme", command=self.check_theme).grid(row=0, column=3, padx=(0, 7))
        ttk.Button(buttons, text="Save Theme…", command=self.save_theme).grid(row=0, column=4)
        ttk.Label(frame, textvariable=self.save_status, foreground="#245b2a", wraplength=580).grid(
            row=7, column=1, columnspan=2, sticky="w", pady=(12, 0)
        )

    @staticmethod
    def _field(parent: ttk.Frame, row: int, label: str, variable: tk.StringVar) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, columnspan=2, sticky="ew", padx=(12, 0), pady=4)

    def choose_theme(self) -> None:
        filename = filedialog.askopenfilename(
            title="Load a theme to edit", initialdir=THEMES_DIR, filetypes=[("JSON theme files", "*.json")]
        )
        if filename:
            self.load_theme(Path(filename))

    def load_theme(self, path: Path) -> None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            rows = []
            for puzzle in data["puzzles"]:
                rows.append(f"{puzzle['name']} | {', '.join(puzzle['words'])}")
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
            messagebox.showerror("Cannot load theme", f"This is not a usable theme file.\n\n{exc}", parent=self)
            return
        self.theme_title.set(data.get("title", "Word Search"))
        self.theme_subtitle.set(data.get("subtitle", ""))
        self.theme_author.set(data.get("author", ""))
        self.puzzles.delete("1.0", "end")
        self.puzzles.insert("1.0", "\n".join(rows))
        self.save_status.set(f"Loaded {len(rows)} puzzles from {path.name}.")

    def make_outline(self) -> None:
        if self.puzzles.get("1.0", "end-1c").strip() and not messagebox.askyesno(
            "Replace current list?", "Replace the current puzzle list with 48 blank puzzles?", parent=self
        ):
            return
        self.puzzles.delete("1.0", "end")
        self.puzzles.insert("1.0", "\n".join(f"Puzzle {number} | " for number in range(1, 49)))
        self.save_status.set("Created a 48-puzzle outline. Replace each name and add its words.")

    def open_mixer(self) -> None:
        ThemeMixerDialog(self)

    def _theme_data(self) -> dict:
        title = self.theme_title.get().strip()
        if not title:
            raise ValueError("Add a book title.")
        puzzles = []
        names = set()
        for number, raw_line in enumerate(self.puzzles.get("1.0", "end-1c").splitlines(), start=1):
            line = raw_line.strip()
            if not line:
                continue
            if "|" not in line:
                raise ValueError(f"Line {number} needs a vertical bar (|) between the puzzle name and words.")
            name, words_text = (part.strip() for part in line.split("|", 1))
            words = [word.strip() for word in words_text.split(",") if word.strip()]
            if not name:
                raise ValueError(f"Line {number} needs a puzzle name.")
            if name.casefold() in names:
                raise ValueError(f"Puzzle names must be unique: '{name}'.")
            names.add(name.casefold())
            if not words:
                raise ValueError(f"'{name}' needs at least one word.")
            for word in words:
                letters = "".join(char for char in word if char.isalpha())
                if not letters:
                    raise ValueError(f"'{word}' in '{name}' has no letters.")
                if len(letters) > 21:
                    raise ValueError(f"'{word}' in '{name}' is longer than the maximum 21-letter grid.")
            puzzles.append({"name": name, "words": words})
        if not puzzles:
            raise ValueError("Add at least one puzzle.")
        recommendation = recommend_theme_from_words(puzzles)
        return {
            "title": title,
            "subtitle": self.theme_subtitle.get().strip(),
            "author": self.theme_author.get().strip(),
            "palette": recommendation["palette"],
            "cover_style": recommendation["style"],
            "detected_topic": recommendation["topic"],
            "difficulty_label": puzzle_difficulty_label({"puzzles": puzzles}),
            "puzzles": puzzles,
        }

    def check_theme(self) -> None:
        try:
            data = self._theme_data()
        except ValueError as exc:
            self.save_status.set("Please correct the theme before saving.")
            messagebox.showwarning("Theme needs attention", str(exc), parent=self)
            return
        not_twelve = [item["name"] for item in data["puzzles"] if len(item["words"]) != 12]
        warning = "" if not not_twelve else f" {len(not_twelve)} puzzle(s) do not have 12 words."
        recommendation = recommend_theme_from_words(data["puzzles"])
        self.save_status.set(f"Looks good: {len(data['puzzles'])} puzzles. Detected topic: {recommendation['topic']}. Suggested cover: {recommendation['palette']} / {recommendation['style']}.{warning}")
        messagebox.showinfo("Theme check", self.save_status.get(), parent=self)

    def save_theme(self) -> None:
        try:
            data = self._theme_data()
        except ValueError as exc:
            messagebox.showwarning("Theme needs attention", str(exc), parent=self)
            return
        default_name = WordSearchCreator._safe_filename(data["title"]).lower() + ".json"
        filename = filedialog.asksaveasfilename(
            title="Save your theme", initialdir=THEMES_DIR, initialfile=default_name,
            defaultextension=".json", filetypes=[("JSON theme files", "*.json")],
        )
        if not filename:
            return
        try:
            automatic_theme_backup("saving a theme in Theme Builder")
            Path(filename).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Could not save theme", str(exc), parent=self)
            return
        self.parent._set_theme(Path(filename))
        self.save_status.set(f"Saved {len(data['puzzles'])} puzzles to {Path(filename).name}.")
        messagebox.showinfo("Theme saved", "Your theme is saved and ready to generate.", parent=self)


class ThemeMixerDialog(tk.Toplevel):
    """Combine puzzles from multiple saved theme files into a new theme."""

    def __init__(self, builder: ThemeBuilderDialog) -> None:
        super().__init__(builder)
        self.builder = builder
        self.title("Mix Themes")
        self.geometry("650x540")
        self.minsize(580, 460)
        self.transient(builder)
        self.grab_set()

        self.title_text = tk.StringVar(value="Mixed Theme Word Search")
        self.subtitle_text = tk.StringVar(value="A mixed-theme word search collection")
        self.author_text = tk.StringVar(value=builder.theme_author.get())
        self.limit_text = tk.StringVar(value="All puzzles")
        self.status = tk.StringVar(value="Select two or more themes. Use Ctrl-click to select more than one.")
        self.paths = saved_theme_files()
        self._build()

    def _build(self) -> None:
        frame = ttk.Frame(self, padding=18)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(5, weight=1)

        ttk.Label(frame, text="MIX THEMES", font=("Segoe UI", 18, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w"
        )
        ttk.Label(
            frame,
            text="Create a new theme from several saved themes. Your originals are never changed.",
            foreground="#555555",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 14))
        self._field(frame, 2, "New book title", self.title_text)
        self._field(frame, 3, "Subtitle", self.subtitle_text)
        self._field(frame, 4, "Author", self.author_text)

        ttk.Label(frame, text="Themes to combine").grid(row=5, column=0, sticky="nw", pady=(12, 0))
        right = ttk.Frame(frame)
        right.grid(row=5, column=1, sticky="nsew", padx=(12, 0), pady=(12, 0))
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)
        self.theme_list = tk.Listbox(right, selectmode="extended", exportselection=False, height=13)
        self.theme_list.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(right, orient="vertical", command=self.theme_list.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.theme_list.configure(yscrollcommand=scrollbar.set)
        for path in self.paths:
            self.theme_list.insert("end", path.stem.replace("_", " ").title())
        self.theme_list.bind("<<ListboxSelect>>", self._selection_changed)

        ttk.Label(frame, text="Puzzles from each theme").grid(row=6, column=0, sticky="w", pady=(12, 0))
        ttk.Combobox(
            frame, textvariable=self.limit_text, state="readonly", values=("All puzzles", "12 puzzles", "16 puzzles", "24 puzzles")
        ).grid(row=6, column=1, sticky="w", padx=(12, 0), pady=(12, 0))
        ttk.Label(frame, textvariable=self.status, foreground="#245b2a", wraplength=480).grid(
            row=7, column=1, sticky="w", padx=(12, 0), pady=(10, 0)
        )
        ttk.Button(frame, text="Create Mixed Theme…", command=self.create_theme).grid(
            row=8, column=0, columnspan=2, sticky="ew", pady=(15, 0)
        )

    @staticmethod
    def _field(parent: ttk.Frame, row: int, label: str, variable: tk.StringVar) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=(12, 0), pady=4)

    def _selection_changed(self, _event: object = None) -> None:
        count = len(self.theme_list.curselection())
        self.status.set(f"{count} theme{'s' if count != 1 else ''} selected.")

    def create_theme(self) -> None:
        selected = self.theme_list.curselection()
        if len(selected) < 2:
            messagebox.showwarning("Select themes", "Select at least two themes to mix.", parent=self)
            return
        title = self.title_text.get().strip()
        if not title:
            messagebox.showwarning("Add a title", "Give the mixed book a title.", parent=self)
            return
        limit = 0 if self.limit_text.get() == "All puzzles" else int(self.limit_text.get().split()[0])
        puzzles = []
        used_names = set()
        try:
            for index in selected:
                path = self.paths[index]
                data = json.loads(path.read_text(encoding="utf-8"))
                source_label = path.stem.replace("_", " ").title()
                source_puzzles = data["puzzles"][:limit] if limit else data["puzzles"]
                for puzzle in source_puzzles:
                    name = puzzle["name"].strip()
                    unique_name = name
                    if unique_name.casefold() in used_names:
                        unique_name = f"{name} ({source_label})"
                    suffix = 2
                    while unique_name.casefold() in used_names:
                        unique_name = f"{name} ({source_label} {suffix})"
                        suffix += 1
                    used_names.add(unique_name.casefold())
                    puzzles.append({"name": unique_name, "words": puzzle["words"]})
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
            messagebox.showerror("Cannot mix themes", f"One selected theme could not be read.\n\n{exc}", parent=self)
            return
        mixed = {
            "title": title,
            "subtitle": self.subtitle_text.get().strip(),
            "author": self.author_text.get().strip(),
            "palette": "nature",
            "difficulty_label": puzzle_difficulty_label({"puzzles": puzzles}),
            "puzzles": puzzles,
        }
        default_name = WordSearchCreator._safe_filename(title).lower() + ".json"
        filename = filedialog.asksaveasfilename(
            title="Save your mixed theme", initialdir=THEMES_DIR, initialfile=default_name,
            defaultextension=".json", filetypes=[("JSON theme files", "*.json")], parent=self,
        )
        if not filename:
            return
        try:
            Path(filename).write_text(json.dumps(mixed, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Could not save theme", str(exc), parent=self)
            return
        self.builder.load_theme(Path(filename))
        self.builder.parent._set_theme(Path(filename))
        self.builder.save_status.set(f"Mixed {len(selected)} themes into {len(puzzles)} puzzles. Review or save it from Theme Builder.")
        self.destroy()


class BookBlueprintDialog(tk.Toplevel):
    """Guided creator for brand-new book themes without touching existing JSON."""

    MOODS = {
        "Cozy and warm": ("autumn-harvest", "gallery"),
        "Bold and energetic": ("tropical-pop", "bold"),
        "Playful and colorful": ("candy-pop", "playful"),
        "Premium and classic": ("midnight-gold", "classic"),
        "Seasonal celebration": ("holly-jolly", "playful"),
        "Calm and natural": ("nature", "halo"),
    }

    def __init__(self, parent: "WordSearchCreator") -> None:
        super().__init__(parent)
        self.parent = parent
        self.title("Book Blueprint Wizard")
        self.geometry("800x740")
        self.minsize(700, 650)
        self.transient(parent)
        self.grab_set()
        self.topic = tk.StringVar()
        self.book_title = tk.StringVar()
        self.cover_title_feedback = tk.StringVar()
        self.subtitle = tk.StringVar()
        self.subtitle_feedback = tk.StringVar()
        self.book_specs = tk.StringVar(value="Estimated interior: choose a theme")
        self.series = tk.StringVar()
        self.audience = tk.StringVar(value="Adults & Teens")
        self.puzzle_count = tk.StringVar(value="48")
        self.words_per_puzzle = tk.StringVar(value="12")
        self.mood = tk.StringVar(value="Calm and natural")
        self.signature = tk.BooleanVar(value=False)
        self.count_recommendation = tk.StringVar(value="Word-bank recommendation appears as you add words.")
        self.status = tk.StringVar(value="Add your niche and a starter word bank. Your current themes will not be changed.")
        self.signature.trace_add("write", lambda *_args: self._signature_changed())
        self._build()

    def _signature_changed(self) -> None:
        if self.signature.get():
            self.puzzle_count.set(str(SIGNATURE_PUZZLE_TARGET))
        self._update_count_recommendation()

    def _field(self, parent: ttk.Frame, row: int, label: str, variable: tk.StringVar) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=5)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=(12, 0), pady=5)

    def _build(self) -> None:
        frame = scrollable_dialog_page(self, padding=18)
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text="BOOK BLUEPRINT WIZARD", font=("Segoe UI", 18, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(frame, text="Creates a brand-new JSON theme from your ideas and words. Existing themes are never changed.", foreground="#555555", wraplength=720).grid(row=1, column=0, columnspan=2, sticky="w", pady=(3, 14))
        self._field(frame, 2, "Topic or niche", self.topic)
        self._field(frame, 3, "Book title (optional)", self.book_title)
        self._field(frame, 4, "Subtitle (optional)", self.subtitle)
        self._field(frame, 5, "Series name (optional)", self.series)
        ttk.Label(frame, text="Audience").grid(row=6, column=0, sticky="w", pady=5)
        ttk.Combobox(frame, textvariable=self.audience, values=("Adults", "Teens", "Adults & Teens"), state="readonly").grid(row=6, column=1, sticky="ew", padx=(12, 0), pady=5)
        ttk.Label(frame, text="Puzzles / words each").grid(row=7, column=0, sticky="w", pady=5)
        settings = ttk.Frame(frame)
        settings.grid(row=7, column=1, sticky="ew", padx=(12, 0), pady=5)
        ttk.Combobox(settings, textvariable=self.puzzle_count, values=("48", "60", "100"), state="readonly", width=10).pack(side="left")
        ttk.Label(settings, text="puzzles with").pack(side="left", padx=8)
        ttk.Combobox(settings, textvariable=self.words_per_puzzle, values=("12", "20"), state="readonly", width=8).pack(side="left")
        ttk.Label(settings, text="words each").pack(side="left", padx=8)
        ttk.Label(frame, textvariable=self.count_recommendation, foreground="#245b4f", wraplength=520).grid(row=8, column=1, sticky="w", padx=(12, 0))
        ttk.Label(frame, text="Cover mood").grid(row=9, column=0, sticky="w", pady=5)
        ttk.Combobox(frame, textvariable=self.mood, values=tuple(self.MOODS), state="readonly").grid(row=9, column=1, sticky="ew", padx=(12, 0), pady=5)
        ttk.Checkbutton(frame, text="Make this a 100-puzzle Signature Edition (Passport, achievement page, and extra page)", variable=self.signature).grid(row=10, column=0, columnspan=2, sticky="w", pady=(6, 8))
        ttk.Label(frame, text="Starter word bank").grid(row=11, column=0, sticky="nw", pady=(7, 0))
        words_frame = ttk.Frame(frame)
        words_frame.grid(row=11, column=1, sticky="nsew", padx=(12, 0), pady=(7, 0))
        words_frame.columnconfigure(0, weight=1)
        self.words = ScrolledText(words_frame, height=10, wrap="word", font=("Segoe UI", 10))
        self.words.grid(row=0, column=0, sticky="nsew")
        self.words.bind("<KeyRelease>", lambda _event: self._update_count_recommendation())
        ttk.Label(words_frame, text="Use one word or phrase per line, or separate entries with commas. For a strong varied book, use at least three times the selected words-per-puzzle (36 words for 12-word books, 60 for 20-word books).", foreground="#666666", wraplength=535).grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Button(words_frame, text="Import Word Bank File…", command=self.import_word_bank, style="Action.TButton").grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Label(frame, text="The wizard rotates your supplied word bank into distinct puzzle lists. You can still open the new theme in Theme Builder afterward.", foreground="#555555", wraplength=720).grid(row=12, column=0, columnspan=2, sticky="w", pady=(12, 0))
        actions = ttk.Frame(frame)
        actions.grid(row=13, column=0, columnspan=2, sticky="ew", pady=(16, 0))
        actions.columnconfigure(0, weight=1)
        actions.columnconfigure(1, weight=1)
        ttk.Button(actions, text="Create Blueprint", command=self.create, style="Primary.TButton").grid(row=0, column=0, sticky="ew", padx=(0, 5))
        ttk.Button(actions, text="Cancel", command=self.destroy, style="Action.TButton").grid(row=0, column=1, sticky="ew", padx=(5, 0))
        ttk.Label(frame, textvariable=self.status, foreground="#245b2a", wraplength=720).grid(row=14, column=0, columnspan=2, sticky="w", pady=(12, 0))

    @staticmethod
    def _clean_source(text: str) -> list[str]:
        # Commas and lines preserve useful phrases such as "Blue Jay".  If a
        # source really is a simple space-only list, treat each token as a word.
        raw = re.split(r"[,\n\r;\t]+", text)
        if len(raw) == 1 and len(text.split()) > 1:
            raw = text.split()
        return BookBlueprintDialog._clean_items(raw)

    @staticmethod
    def _clean_items(items: list[str]) -> list[str]:
        cleaned = puzzle_engine.clean_words(items)
        unique: list[str] = []
        for word in cleaned:
            if word not in unique:
                unique.append(word)
        return unique

    def _update_count_recommendation(self) -> None:
        words = self._clean_source(self.words.get("1.0", "end-1c"))
        try: words_each = int(self.words_per_puzzle.get())
        except ValueError: words_each = 12
        target = SIGNATURE_PUZZLE_TARGET if self.signature.get() else 48
        needed = target * words_each
        if len(words) >= needed:
            suggestion = f"enough for a repeat-free {target}-puzzle book"
        else:
            suggestion = f"add {needed - len(words)} more words for a repeat-free {target}-puzzle book"
        self.count_recommendation.set(f"{len(words)} clean unique words → recommended: {suggestion}.")

    def import_word_bank(self) -> None:
        """Load ordinary TXT files or any compatible existing theme JSON."""
        filename = filedialog.askopenfilename(
            title="Choose a word bank or existing theme",
            initialdir=THEMES_DIR,
            filetypes=[("Word bank or theme", "*.txt *.json"), ("Text files", "*.txt"), ("JSON theme files", "*.json"), ("All files", "*.*")],
            parent=self,
        )
        if not filename:
            return
        path = Path(filename)
        try:
            raw_words: list[str]
            if path.suffix.lower() == ".json":
                data = json.loads(path.read_text(encoding="utf-8-sig"))
                if isinstance(data, dict) and isinstance(data.get("puzzles"), list):
                    raw_words = [str(word) for puzzle in data["puzzles"] if isinstance(puzzle, dict) for word in puzzle.get("words", [])]
                    if not self.topic.get().strip() and data.get("detected_topic"):
                        self.topic.set(str(data["detected_topic"]))
                    if not self.book_title.get().strip() and data.get("title"):
                        self.book_title.set(str(data["title"]))
                elif isinstance(data, dict) and isinstance(data.get("words"), list):
                    raw_words = [str(word) for word in data["words"]]
                elif isinstance(data, list):
                    raw_words = [str(word) for word in data]
                else:
                    raise ValueError("This JSON file does not contain a word list or puzzles.")
                words = self._clean_items(raw_words)
            else:
                words = self._clean_source(path.read_text(encoding="utf-8-sig"))
            if not words:
                raise ValueError("No usable words were found. Choose a TXT list or a theme JSON with puzzle words.")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            messagebox.showerror("Could not import word bank", str(exc), parent=self)
            return
        self.words.delete("1.0", "end")
        self.words.insert("1.0", ", ".join(words))
        self._update_count_recommendation()
        self.status.set(f"Imported and cleaned {len(words)} unique words from {path.name}. Choose your book settings, then create the blueprint.")

    def create(self) -> None:
        topic = self.topic.get().strip()
        if not topic:
            messagebox.showwarning("Add a topic", "Start with a topic or niche, such as Backyard Birds or Christmas Traditions.", parent=self)
            return
        try:
            count = int(self.puzzle_count.get())
            words_per_puzzle = int(self.words_per_puzzle.get())
        except ValueError:
            messagebox.showwarning("Book setup", "Choose a puzzle count and words-per-puzzle option.", parent=self)
            return
        if self.signature.get() and count != SIGNATURE_PUZZLE_TARGET:
            messagebox.showwarning("Signature Edition size", f"Signature Editions are always {SIGNATURE_PUZZLE_TARGET} puzzles. The puzzle count was reset for you.", parent=self)
            self.puzzle_count.set(str(SIGNATURE_PUZZLE_TARGET))
            return
        words = self._clean_source(self.words.get("1.0", "end-1c"))
        minimum = count * words_per_puzzle
        if len(words) < minimum:
            messagebox.showwarning("More unique words needed", f"This book needs {minimum} unique words for {count} puzzles with {words_per_puzzle} words each. You currently have {len(words)}. No word will be repeated in a new book.", parent=self)
            return
        recommendation = recommend_theme_from_words([{"words": words}])
        mood_palette, mood_style = self.MOODS[self.mood.get()]
        title = self.book_title.get().strip() or f"{topic} Word Search"
        subtitle = self.subtitle.get().strip() or f"{count} themed word search puzzles for {self.audience.get().lower()}"
        label = re.sub(r"\s+", " ", topic).strip()
        puzzles: list[dict[str, object]] = []
        shuffled_words = words[:]
        random.Random(f"{title}|no-repeat").shuffle(shuffled_words)
        for number in range(1, count + 1):
            start = (number - 1) * words_per_puzzle
            selected = shuffled_words[start:start + words_per_puzzle]
            puzzles.append({"name": f"{label} Puzzle {number:03d}", "words": selected})
        data: dict[str, object] = {
            "title": title,
            "subtitle": subtitle,
            "author": "Jordan M. Slade",
            "audience": self.audience.get(),
            "palette": mood_palette or recommendation["palette"],
            "cover_style": mood_style or recommendation["style"],
            "detected_topic": recommendation["topic"],
            "recommended_palette": recommendation["palette"],
            "recommended_cover_style": recommendation["style"],
            "difficulty_label": puzzle_difficulty_label({"puzzles": puzzles}),
            "clipart_search_terms": f"{topic} illustration clipart transparent background",
            "no_repeat_words": True,
            "cover_badge": "NO REPEATED WORDS",
            "puzzles": puzzles,
        }
        if self.series.get().strip():
            data["series"] = self.series.get().strip()
        if self.signature.get():
            data["signature_edition"] = {
                "enabled": True,
                "puzzle_target": SIGNATURE_PUZZLE_TARGET,
                "passport_title": f"{label} Passport",
                "achievement_title": "Signature Edition",
                "achievement_message": "A calm challenge, one puzzle at a time.",
                "facts_title": "ABOUT THIS COLLECTION",
                "fact_cards": [
                    f"This Signature Edition is built around {topic}.",
                    "Use the Puzzle Passport to celebrate each completed challenge.",
                    "Return to a favorite puzzle whenever you want a calm screen-free break.",
                ],
            }
        filename = WordSearchCreator._safe_filename(title).lower() + ".json"
        path = THEMES_DIR / filename
        suffix = 2
        while path.exists():
            path = THEMES_DIR / f"{WordSearchCreator._safe_filename(title).lower()}_{suffix}.json"
            suffix += 1
        try:
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Could not create blueprint", str(exc), parent=self)
            return
        self.parent._load_theme_list()
        self.parent._set_theme(path)
        self.parent.status.set(f"Created new {'Signature ' if self.signature.get() else ''}Edition blueprint: {path.name}")
        messagebox.showinfo("Blueprint created", "Your new theme has been added to the Theme Library and loaded into Book Studio. Run Check Book before generating, then create your package when you are ready.", parent=self)
        self.destroy()


class CoverCreatorDialog(tk.Toplevel):
    """Make a matching front cover and optional KDP full-wrap PDF."""

    PALETTES = ("nature", "nostalgia", "sunset", "ocean-breeze", "lavender-pop", "candy-pop", "neon-arcade", "midnight-gold", "berry-blush", "forest-cabin", "desert-sun", "coastal-blue", "autumn-harvest", "winter-frost", "spring-meadow", "royal-plum", "espresso-cream", "tropical-pop", "holly-jolly", "spooky-night", "valentine-rose", "easter-pastel", "patriotic", "scholarly-blue", "notebook-mint", "library-burgundy", "starlight-indigo", "citrus-study", "graphite-copper", "pixel-neon", "cinema-red", "christmas", "beach-vacation", "summer-vacation", "food", "animals", "birds", "gardening", "sports", "ocean-life", "retro-travel-and-landmarks", "usa", "kids", "bible")

    def __init__(self, parent: "WordSearchCreator") -> None:
        super().__init__(parent)
        self.parent = parent
        self.title("Cover Creator")
        self.geometry("760x720")
        self.minsize(650, 620)
        self.transient(parent)
        self.grab_set()
        theme_data = self._current_theme_data()
        count = len(theme_data.get("puzzles", []))
        self.book_title = tk.StringVar(value=parent.book_title.get())
        self.subtitle = tk.StringVar(value=parent.subtitle.get())
        self.author = tk.StringVar(value=parent.author.get())
        self.palette = tk.StringVar(value=theme_data.get("palette", "nature"))
        self.cover_style = tk.StringVar(value="Classic")
        self.art_path = tk.StringVar()
        self.art_focus = tk.StringVar(value="center")
        self.badge = tk.StringVar(value=f"INCLUDES {count} PUZZLES" if count else "WORD SEARCH PUZZLES")
        self.difficulty = puzzle_difficulty_label(theme_data)
        self.interior_pdf = tk.StringVar(value=str(parent.last_output) if parent.last_output else "")
        self.imprint = tk.StringVar(value="Your Puzzle Press")
        self.filename = tk.StringVar(value=WordSearchCreator._safe_filename(parent.book_title.get()).lower())
        self.status = tk.StringVar(value="Create a front cover, or choose an interior PDF to create the full KDP wrap.")
        self.front_file: Path | None = None
        self.wrap_file: Path | None = None
        self.preview_file: Path | None = None
        self._build(count)

    def _current_theme_data(self) -> dict:
        if not self.parent.selected_theme:
            return {}
        try:
            return json.loads(self.parent.selected_theme.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _build(self, puzzle_count: int) -> None:
        frame = ttk.Frame(self, padding=18)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(9, weight=1)
        ttk.Label(frame, text="COVER CREATOR", font=("Segoe UI", 18, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(frame, text="Front cover: 8.5 × 11 inches at 300 DPI. Full wrap: KDP bleed and spine are calculated from the interior PDF.", foreground="#555555", wraplength=690).grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 14))
        self._field(frame, 2, "Book title", self.book_title)
        self._field(frame, 3, "Subtitle", self.subtitle)
        self._field(frame, 4, "Author / pen name", self.author)
        ttk.Label(frame, text="Color and layout").grid(row=5, column=0, sticky="w", pady=5)
        ttk.Combobox(frame, textvariable=self.palette, state="readonly", values=self.PALETTES).grid(row=5, column=1, sticky="ew", padx=(12, 6), pady=5)
        ttk.Combobox(frame, textvariable=self.cover_style, state="readonly", values=("Photo Hero", "Playful Illustrated", "Sunburst Poster", "Classic", "Bold Spotlight", "Retro Pop", "Minimal", "Gallery Frame", "Color Block")).grid(row=5, column=2, sticky="ew", pady=5)
        self._field(frame, 6, "Cover badge", self.badge)
        self._field(frame, 7, "Output name", self.filename)
        ttk.Label(frame, text="Interior PDF (for full wrap)").grid(row=8, column=0, sticky="w", pady=5)
        ttk.Entry(frame, textvariable=self.interior_pdf).grid(row=8, column=1, sticky="ew", padx=(12, 8), pady=5)
        ttk.Button(frame, text="Choose…", command=self.choose_interior).grid(row=8, column=2, pady=5)
        self._field(frame, 9, "Back-cover imprint", self.imprint)
        ttk.Label(frame, text="Back-cover description").grid(row=10, column=0, sticky="nw", pady=(8, 0))
        self.blurb = ScrolledText(frame, height=8, wrap="word", font=("Segoe UI", 10))
        self.blurb.grid(row=10, column=1, columnspan=2, sticky="nsew", padx=(12, 0), pady=(8, 0))
        self.blurb.insert("1.0", self._default_blurb(puzzle_count, book_format_label(theme_data)))
        actions = ttk.Frame(frame)
        actions.grid(row=11, column=0, columnspan=3, sticky="ew", pady=(14, 0))
        actions.columnconfigure(0, weight=1)
        actions.columnconfigure(1, weight=1)
        ttk.Button(actions, text="Create Front Cover", command=lambda: self.generate(False)).grid(row=0, column=0, sticky="ew", padx=(0, 5))
        ttk.Button(actions, text="Create KDP Full Wrap", command=lambda: self.generate(True)).grid(row=0, column=1, sticky="ew", padx=(5, 0))
        self.art_button = ttk.Menubutton(frame, text="Cover picture ▾")
        art_menu = tk.Menu(self.art_button, tearoff=False)
        art_menu.add_command(label="Choose saved image…", command=self.choose_art)
        art_menu.add_command(label="Browse CC0 OpenClipart…", command=self.browse_openclipart)
        self.art_button.configure(menu=art_menu)
        self.art_button.grid(row=12, column=0, sticky="ew", pady=(8, 0))
        self.open_button = ttk.Button(frame, text="Open Latest Cover", command=self.open_latest, state="disabled")
        self.open_button.grid(row=12, column=1, sticky="ew", padx=(8, 0), pady=(8, 0))
        self.preview_button = ttk.Button(frame, text="Buyer-Size Preview", command=self.open_preview, state="disabled")
        self.preview_button.grid(row=12, column=2, sticky="ew", padx=(8, 0), pady=(8, 0))
        ttk.Label(frame, textvariable=self.status, foreground="#245b2a", wraplength=690).grid(row=13, column=0, columnspan=3, sticky="w", pady=(12, 0))

    @staticmethod
    def _field(parent: ttk.Frame, row: int, label: str, variable: tk.StringVar) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=5)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, columnspan=2, sticky="ew", padx=(12, 0), pady=5)

    @staticmethod
    def _default_blurb(count: int, format_label: str) -> str:
        lead = "large print word search" if format_label == "LARGE PRINT PUZZLES" else "themed word search"
        detail = "Big, easy-to-read letters and roomy grids" if format_label == "LARGE PRINT PUZZLES" else "Clear grids and easy-to-follow word lists"
        return (f"Relax with {count or 'a collection of'} {lead} puzzles in a theme you'll love.\n\n"
                "Every puzzle is cleanly designed with generous spacing—one per page, easy to enjoy.\n\n"
                "Inside this book:\n"
                f"• {count or 'A collection of'} word search puzzles\n"
                f"• {detail}\n"
                "• Complete solutions at the back\n"
                "• A calm, screen-free way to relax and keep your mind active")

    def choose_interior(self) -> None:
        path = filedialog.askopenfilename(title="Choose the finished interior PDF", initialdir=OUTPUT_DIR, filetypes=[("PDF files", "*.pdf")])
        if path:
            self.interior_pdf.set(path)

    def choose_art(self) -> None:
        path = filedialog.askopenfilename(
            title="Choose licensed hero artwork", filetypes=[("Image files", "*.png;*.jpg;*.jpeg;*.webp"), ("All files", "*.*")]
        )
        if path:
            self.art_path.set(path)
            focus, _note = suggest_art_plan(Path(path))
            self.art_focus.set(focus)
            self.status.set(f"Cover picture selected: {Path(path).name} • suggested placement: {focus} focus")

    def browse_openclipart(self) -> None:
        data = self._current_theme_data()
        query = openclipart_query(data) if data else (self.book_title.get().strip() or "word search")
        OpenClipartPickerDialog(self.parent, query, self._apply_openclipart)

    def _apply_openclipart(self, path: Path, record: dict[str, object]) -> None:
        focus, _note = suggest_art_plan(path)
        self.art_path.set(str(path)); self.art_focus.set(focus); self.cover_style.set("Photo Hero")
        self.status.set(f"OpenClipart image selected: {record.get('title', path.name)} • {focus} focus")

    def generate(self, include_wrap: bool) -> None:
        if not self.book_title.get().strip():
            messagebox.showwarning("Add a title", "Give the book a title before making a cover.", parent=self)
            return
        interior = Path(self.interior_pdf.get()) if self.interior_pdf.get().strip() else None
        art = Path(self.art_path.get()) if self.art_path.get().strip() else None
        if include_wrap and (not interior or not interior.exists()):
            messagebox.showwarning("Choose the interior PDF", "Choose the finished book PDF before creating a KDP full wrap.", parent=self)
            return
        if self.cover_style.get() == "Photo Hero" and (not art or not art.exists()):
            messagebox.showwarning("Choose hero artwork", "Choose a licensed image before using the Photo Hero layout.", parent=self)
            return
        base = WordSearchCreator._safe_filename(self.filename.get()).lower()
        self.front_file = OUTPUT_DIR / f"{base}_cover.png"
        self.wrap_file = OUTPUT_DIR / f"{base}_wrap.pdf"
        self.preview_file = OUTPUT_DIR / f"{base}_cover_thumbnail.png"
        theme_data: dict = {}
        if self.parent.selected_theme:
            try:
                theme_data = json.loads(self.parent.selected_theme.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError):
                theme_data = {}
        settings = {
            "title": self.book_title.get().strip(), "subtitle": self.subtitle.get().strip(),
            "author": self.author.get().strip(), "badge": self.badge.get().strip(),
            "puzzle_count": len(theme_data.get("puzzles", [])),
            "format_label": "LARGE PRINT" if book_format_label(theme_data) == "LARGE PRINT PUZZLES" else "WORD SEARCH",
            "palette": self.palette.get(), "imprint": self.imprint.get().strip(),
            "blurb": self.blurb.get("1.0", "end-1c").strip(),
            "style": {"Photo Hero": "photo", "Playful Illustrated": "playful", "Sunburst Poster": "sunburst", "Classic": "classic", "Bold Spotlight": "bold", "Retro Pop": "retro", "Minimal": "minimal", "Gallery Frame": "gallery", "Color Block": "colorblock"}[self.cover_style.get()],
            "theme_file": str(self.parent.selected_theme) if self.parent.selected_theme else "",
            "art": str(art) if art else "",
            "art_focus": self.art_focus.get(),
        }
        self.status.set("Creating your cover…")
        threading.Thread(target=self._run, args=(include_wrap, interior, settings), daemon=True).start()

    def _run(self, include_wrap: bool, interior: Path | None, settings: dict[str, str]) -> None:
        python = WINDOWS_VENV_PYTHON if WINDOWS_VENV_PYTHON.exists() else Path(sys.executable)
        common = ["--title", settings["title"], "--subtitle", settings["subtitle"], "--author", settings["author"], "--badge", settings["badge"], "--puzzle-count", str(settings.get("puzzle_count", 0)), "--difficulty", self.difficulty, "--format-label", settings.get("format_label", "WORD SEARCH"), "--palette", settings["palette"], "--style", settings["style"]]
        if settings["theme_file"]:
            common.extend(["--theme-file", settings["theme_file"]])
        if settings["art"]:
            common.extend(["--art", settings["art"], "--art-focus", settings.get("art_focus", "center")])
        try:
            front = subprocess.run([str(python), str(COVER_ENGINE), *common, "--out", str(self.front_file)], cwd=APP_DIR, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            if front.returncode:
                raise RuntimeError(front.stderr.strip() or front.stdout.strip())
            if include_wrap and interior:
                from pypdf import PdfReader
                pages = len(PdfReader(str(interior)).pages)
                wrap = subprocess.run([str(python), str(WRAP_ENGINE), "--front", str(self.front_file), "--pages", str(pages), "--palette", settings["palette"], "--title", settings["title"], "--author", settings["author"], "--back", settings["blurb"], "--out", str(self.wrap_file)], cwd=APP_DIR, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
                if wrap.returncode:
                    raise RuntimeError(wrap.stderr.strip() or wrap.stdout.strip())
            self.after(0, self.finished, True, include_wrap)
        except Exception as exc:
            self.after(0, self.finished, False, str(exc))

    def finished(self, success: bool, result: object) -> None:
        if success:
            self.open_button.configure(state="normal")
            self.preview_button.configure(state="normal")
            self.status.set("Done! Your front cover and KDP-ready full wrap are in the out folder." if result else "Done! Your front cover is in the out folder.")
        else:
            self.status.set("The cover could not be created.")
            messagebox.showerror("Cover generation problem", str(result), parent=self)

    def open_latest(self) -> None:
        target = self.wrap_file if self.wrap_file and self.wrap_file.exists() else self.front_file
        if target and target.exists():
            os.startfile(target)

    def open_preview(self) -> None:
        if self.preview_file and self.preview_file.exists():
            os.startfile(self.preview_file)


class PublishReadyDialog(tk.Toplevel):
    """One guided action that produces an interior, cover package, and report."""

    STYLE_MAP = {"Playful Illustrated": "playful", "Sunburst Poster": "sunburst", "Classic": "classic", "Bold Spotlight": "bold", "Retro Pop": "retro", "Minimal": "minimal", "Gallery Frame": "gallery", "Color Block": "colorblock", "Ticket Stub": "ticket", "Halo Spotlight": "halo", "Diagonal Stripe": "stripe", "Photo Hero": "photo"}
    PALETTES = CoverCreatorDialog.PALETTES

    def __init__(self, parent: "WordSearchCreator") -> None:
        super().__init__(parent)
        self.parent = parent
        self.title("Publish-Ready Book")
        self.geometry("690x560")
        self.minsize(610, 500)
        self.transient(parent)
        self.grab_set()
        data = self._theme_data()
        count = len(data.get("puzzles", []))
        self.book_title = tk.StringVar(value=parent.book_title.get())
        self.subtitle = tk.StringVar(value=parent.subtitle.get())
        self.author = tk.StringVar(value=parent.author.get())
        self.palette = tk.StringVar(value=data.get("palette", "nature"))
        self.style = tk.StringVar(value="Playful Illustrated")
        self.imprint = tk.StringVar(value="Your Puzzle Press")
        self.folder_name = tk.StringVar(value=WordSearchCreator._safe_filename(parent.book_title.get()).lower())
        self.seed = tk.StringVar(value=parent.seed.get())
        self.puzzle_count = count
        self.status = tk.StringVar(value=f"This book will include {count} puzzles and a matching KDP cover package.")
        self._build()

    def _theme_data(self) -> dict:
        try:
            return json.loads(self.parent.selected_theme.read_text(encoding="utf-8")) if self.parent.selected_theme else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _build(self) -> None:
        frame = ttk.Frame(self, padding=18)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text="PUBLISH-READY BOOK", font=("Segoe UI", 18, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(frame, text="Creates a new folder with the interior, front cover, KDP full wrap, buyer thumbnail, and quality report.", foreground="#555555", wraplength=640).grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 16))
        self._field(frame, 2, "Book title", self.book_title)
        self._field(frame, 3, "Subtitle", self.subtitle)
        self._field(frame, 4, "Author / pen name", self.author)
        self._field(frame, 5, "Output folder name", self.folder_name)
        self._field(frame, 6, "Random seed", self.seed)
        ttk.Label(frame, text="Color and layout").grid(row=7, column=0, sticky="w", pady=5)
        ttk.Combobox(frame, textvariable=self.palette, state="readonly", values=self.PALETTES).grid(row=7, column=1, sticky="ew", padx=(12, 6), pady=5)
        ttk.Combobox(frame, textvariable=self.style, state="readonly", values=tuple(self.STYLE_MAP)).grid(row=7, column=2, sticky="ew", pady=5)
        self._field(frame, 8, "Back-cover imprint", self.imprint)
        self.publish_button = ttk.Button(frame, text="Create Publish-Ready Book", command=self.publish)
        self.publish_button.grid(row=9, column=0, columnspan=3, sticky="ew", pady=(18, 0))
        self.open_button = ttk.Button(frame, text="Open Book Folder", command=self.open_folder, state="disabled")
        self.open_button.grid(row=10, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        ttk.Label(frame, textvariable=self.status, foreground="#245b2a", wraplength=640).grid(row=11, column=0, columnspan=3, sticky="w", pady=(14, 0))
        self.output_folder: Path | None = None

    @staticmethod
    def _field(parent: ttk.Frame, row: int, label: str, variable: tk.StringVar) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=5)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, columnspan=2, sticky="ew", padx=(12, 0), pady=5)

    def publish(self) -> None:
        if not self.parent.selected_theme:
            messagebox.showwarning("Choose a theme", "Choose a theme before creating the book package.", parent=self)
            return
        if not self.book_title.get().strip() or not self.author.get().strip():
            messagebox.showwarning("Book details", "Add both a book title and an author / pen name.", parent=self)
            return
        try:
            seed = int(self.seed.get())
        except ValueError:
            messagebox.showwarning("Random seed", "Random seed must be a whole number.", parent=self)
            return
        folder = WordSearchCreator._safe_filename(self.folder_name.get()).lower()
        output_folder = OUTPUT_DIR / folder
        if output_folder.exists():
            messagebox.showwarning("Choose a new folder name", f"'{folder}' already exists. Use a different output folder name so nothing is overwritten.", parent=self)
            return
        theme_data = self._theme_data()
        style = self.STYLE_MAP[self.style.get()]
        art = None
        art_focus = "center"
        if style == "photo":
            choice = recommend_background_photo(theme_data)
            candidate = APP_DIR / str(choice.get("file") or "") if choice else None
            if candidate and candidate.is_file() and BackgroundAssetIndex().ledger_details(candidate):
                art = candidate
                art_focus = str(choice.get("focus") or "center")
            else:
                messagebox.showwarning("Cover Art Required", "No approved topic-matched background is available. Choose Approved Asset, Generate Background, or review pending artwork before production.", parent=self)
                return
        if not art:
            choice = recommend_background_photo(theme_data)
            candidate = APP_DIR / str(choice.get("file") or "") if choice else None
            if candidate and candidate.is_file() and BackgroundAssetIndex().ledger_details(candidate):
                art = candidate; art_focus = str(choice.get("focus") or "center")
            else:
                messagebox.showwarning("Cover Art Required", "This production cover needs an explicitly approved background. No approved match is available yet.", parent=self)
                return
        settings = {"title": self.book_title.get().strip(), "subtitle": self.subtitle.get().strip(), "author": self.author.get().strip(), "palette": self.palette.get(), "style": style, "imprint": self.imprint.get().strip(), "seed": seed, "folder": output_folder, "theme": self.parent.selected_theme, "puzzles": self.puzzle_count, "art": str(art) if art else "", "art_focus": art_focus}
        self.publish_button.configure(state="disabled")
        self.status.set("Creating interior, cover package, and quality report. This may take a minute…")
        threading.Thread(target=self._run, args=(settings,), daemon=True).start()

    @staticmethod
    def _run_command(command: list[str]) -> None:
        result = subprocess.run(command, cwd=APP_DIR, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "A generator stopped unexpectedly.")

    def _run(self, settings: dict) -> None:
        try:
            from pypdf import PdfReader
            from PIL import Image
            folder: Path = settings["folder"]
            folder.mkdir(parents=True)
            python = WINDOWS_VENV_PYTHON if WINDOWS_VENV_PYTHON.exists() else Path(sys.executable)
            interior = package_file(folder, "interior.pdf", for_write=True)
            front = package_file(folder, "front_cover.png", for_write=True)
            wrap = package_file(folder, "kdp_full_wrap.pdf", for_write=True)
            self._run_command([str(python), str(ENGINE), "--themes", str(settings["theme"]), "--out", str(interior), "--title", settings["title"], "--subtitle", settings["subtitle"], "--author", settings["author"], "--seed", str(settings["seed"])])
            pages = len(PdfReader(str(interior)).pages)
            theme_data = json.loads(Path(settings["theme"]).read_text(encoding="utf-8-sig"))
            package_data = package_data_from_settings(theme_data, settings)
            badge = str(theme_data.get("cover_badge") or ("NO REPEATED WORDS" if theme_data.get("no_repeat_words") else f"INCLUDES {settings['puzzles']} PUZZLES"))
            difficulty = puzzle_difficulty_label(theme_data)
            cover_command = [str(python), str(COVER_ENGINE), "--title", settings["title"], "--subtitle", settings["subtitle"], "--author", settings["author"], "--badge", badge, "--puzzle-count", str(settings["puzzles"]), "--difficulty", difficulty, "--format-label", "LARGE PRINT" if book_format_label(theme_data) == "LARGE PRINT PUZZLES" else "WORD SEARCH", "--palette", settings["palette"], "--style", settings["style"], "--theme-file", str(settings["theme"]), "--out", str(front)]
            if settings.get("art"):
                cover_command.extend(["--art", str(settings["art"]), "--art-focus", str(settings.get("art_focus") or "center")])
            self._run_command(cover_command)
            blurb = package_blurb(theme_data, package_data)
            self._run_command([str(python), str(WRAP_ENGINE), "--front", str(front), "--pages", str(pages), "--palette", settings["palette"], "--title", settings["title"], "--author", settings["author"], "--back", blurb, "--out", str(wrap)])
            package_file(folder, "KDP_UPLOAD_CHECKLIST.txt", for_write=True).write_text(kdp_upload_checklist_text(package_data, pages), encoding="utf-8")
            package_file(folder, "KDP_LISTING_KIT.txt", for_write=True).write_text(listing_kit_text(package_data), encoding="utf-8")
            write_kdp_compliance_report(folder, package_data, pages)
            preflight_ok, preflight_lines = preflight(folder)
            (folder / "PUBLISHER_PREFLIGHT.txt").write_text(package_preflight_text(folder), encoding="utf-8")
            image_ok = Image.open(front).size == (2550, 3300)
            reader = PdfReader(str(interior))
            page = reader.pages[0].mediabox
            letter_ok = round(float(page.width)) == 612 and round(float(page.height)) == 792
            checks = [
                ("Interior PDF created", interior.exists()), ("Interior uses 8.5 × 11 inch pages", letter_ok),
                ("Front cover is 2550 × 3300 pixels (300 DPI for 8.5 × 11)", image_ok),
                ("KDP full-wrap PDF created", wrap.exists()), ("Buyer thumbnail created", (folder / "front_cover_thumbnail.png").exists()),
            ]
            passed = all(ok for _, ok in checks) and preflight_ok
            report = ["BOOK QUALITY REPORT", "=" * 55, f"Title: {settings['title']}", f"Puzzles: {settings['puzzles']}", f"Interior pages: {pages}", ""]
            report.extend(f"{'PASS' if ok else 'CHECK'} — {label}" for label, ok in checks)
            report.extend(["", "Publisher preflight:"] + [f"• {line}" for line in preflight_lines])
            report.extend(["", "Manual final checks:", "• Open front_cover_thumbnail.png: title and Large Print should be clear at a small size.", "• Open kdp_full_wrap.pdf: verify the back-cover wording and overall visual balance.", "• Use Amazon KDP Print Previewer before publishing."])
            (folder / "quality_report.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
            _errors, quality_warnings, _notes = quality_gate(Path(settings["theme"]), int(settings["seed"]))
            quality_warnings = list(quality_warnings) + list(publisher_safety_report(package_data)["warnings"])
            (folder / "PACKAGE_SCORECARD.txt").write_text(package_scorecard_text(package_data, folder, pages, quality_warnings), encoding="utf-8")
            write_release_safety_files(folder, Path(settings["theme"]), theme_data, settings, pages)
            if settings.get("art"):
                record_cover_art_use(Path(settings["art"]), settings["title"], str(settings["theme"]))
            record_package_created(Path(settings["theme"]), settings["title"], folder, pages)
            self.after(0, self.finished, passed, folder)
        except Exception as exc:
            self.after(0, self.finished, False, str(exc))

    def finished(self, success: bool, result: object) -> None:
        self.publish_button.configure(state="normal")
        if success:
            self.output_folder = result  # type: ignore[assignment]
            self.open_button.configure(state="normal")
            self.status.set("Done! Your publish-ready package and quality report are ready.")
            messagebox.showinfo("Book package created", f"Your complete book package is ready.\n\n{result}", parent=self)
        else:
            self.status.set("The package could not be created.")
            messagebox.showerror("Book package problem", str(result), parent=self)

    def open_folder(self) -> None:
        if self.output_folder and self.output_folder.exists():
            os.startfile(self.output_folder)


class WordBankImportDialog(tk.Toplevel):
    """Turn a plain-text word-bank document into a saved JSON theme."""

    def __init__(self, parent: "WordSearchCreator") -> None:
        super().__init__(parent)
        self.parent = parent
        self.title("Import Word Bank")
        self.geometry("780x650")
        self.minsize(680, 540)
        self.transient(parent)
        self.grab_set()
        self.source: Path | None = None
        self.book_title = tk.StringVar()
        self.subtitle = tk.StringVar()
        self.author = tk.StringVar(value=parent.author.get())
        self.status = tk.StringVar(value="Choose a .txt word-bank file to begin.")
        self.imported_puzzles: list[dict] = []
        self.recommendation: dict[str, object] = {"palette": "nature", "style": "classic", "topic": "General Interest", "notes": []}
        self._build()

    def _build(self) -> None:
        frame = ttk.Frame(self, padding=18)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(6, weight=1)
        ttk.Label(frame, text="IMPORT WORD BANK", font=("Segoe UI", 18, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(frame, text="Imports blank-line-separated word-bank sections. In each section, the first line is the puzzle name and the remaining lines are words.", foreground="#555555", wraplength=700).grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 15))
        ttk.Button(frame, text="Choose Text File…", command=self.choose_file).grid(row=2, column=0, columnspan=3, sticky="ew")
        self._field(frame, 3, "Book title", self.book_title)
        self._field(frame, 4, "Subtitle", self.subtitle)
        self._field(frame, 5, "Author", self.author)
        ttk.Label(frame, text="Import preview").grid(row=6, column=0, sticky="nw", pady=(12, 0))
        self.preview = ScrolledText(frame, height=17, wrap="word", font=("Consolas", 9), state="disabled")
        self.preview.grid(row=6, column=1, columnspan=2, sticky="nsew", padx=(12, 0), pady=(12, 0))
        actions = ttk.Frame(frame); actions.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(14, 0)); actions.columnconfigure(0, weight=1); actions.columnconfigure(1, weight=1)
        ttk.Button(actions, text="Smart Recommend", command=self.smart_recommend).grid(row=0, column=0, sticky="ew", padx=(0, 5))
        ttk.Button(actions, text="Save Imported Theme…", command=self.save_theme).grid(row=0, column=1, sticky="ew", padx=(5, 0))
        ttk.Label(frame, textvariable=self.status, foreground="#245b2a", wraplength=680).grid(row=8, column=0, columnspan=3, sticky="w", pady=(10, 0))

    @staticmethod
    def _field(parent: ttk.Frame, row: int, label: str, variable: tk.StringVar) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=5)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, columnspan=2, sticky="ew", padx=(12, 0), pady=5)

    def choose_file(self) -> None:
        selected = filedialog.askopenfilename(title="Choose a word-bank text file", filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if not selected:
            return
        try:
            text = Path(selected).read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            text = Path(selected).read_text(encoding="cp1252")
        except OSError as exc:
            messagebox.showerror("Cannot read file", str(exc), parent=self)
            return
        puzzles = self._parse(text)
        if not puzzles:
            messagebox.showwarning("No word banks found", "Use a blank line between sections. Each section needs a puzzle name followed by at least one word.", parent=self)
            return
        self.source, self.imported_puzzles = Path(selected), puzzles
        pretty = self.source.stem.replace("_", " ").replace("-", " ").title()
        self.book_title.set(pretty if not self.book_title.get() else self.book_title.get())
        self.subtitle.set(f"{len(puzzles)} Word Search Puzzles" if not self.subtitle.get() else self.subtitle.get())
        self._show_preview()
        self.smart_recommend(silent=True)

    @staticmethod
    def _clean_line(line: str) -> str:
        return re.sub(r"^\s*(?:[-•*]|\d+[.)])\s*", "", line).strip()

    def _parse(self, text: str) -> list[dict]:
        sections = re.split(r"\n\s*\n+", text.replace("\r\n", "\n"))
        puzzles = []
        for section in sections:
            lines = [self._clean_line(line) for line in section.splitlines() if self._clean_line(line)]
            if not lines:
                continue
            if len(lines) == 1 and "|" in lines[0]:
                name, words_text = (part.strip() for part in lines[0].split("|", 1))
                words = [word.strip() for word in words_text.split(",") if word.strip()]
            else:
                name = lines[0].rstrip(":")
                words = []
                for line in lines[1:]:
                    words.extend(word.strip() for word in line.split(",") if word.strip())
            if name and words:
                puzzles.append({"name": name, "words": words})
        return puzzles

    def _show_preview(self) -> None:
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        for number, puzzle in enumerate(self.imported_puzzles, start=1):
            self.preview.insert("end", f"{number}. {puzzle['name']} ({len(puzzle['words'])} words)\n")
            self.preview.insert("end", "   " + ", ".join(puzzle["words"]) + "\n\n")
        self.preview.configure(state="disabled")

    def smart_recommend(self, silent: bool = False) -> None:
        if not self.imported_puzzles:
            if not silent:
                messagebox.showwarning("Choose a file", "Choose a word-bank text file first.", parent=self)
            return
        self.recommendation = recommend_theme_from_words(self.imported_puzzles)
        topic = str(self.recommendation["topic"])
        notes = list(self.recommendation["notes"])
        summary = (f"Detected: {topic}. Suggested cover: {self.recommendation['palette']} / {self.recommendation['style']}. "
                   f"Average: {self.recommendation['average_words']:.1f} words per puzzle.")
        if notes:
            summary += " " + " ".join(notes)
        self.status.set(summary)
        if not silent:
            messagebox.showinfo("Smart theme recommendation", summary + "\n\nThe suggested palette and layout will be saved with this theme.", parent=self)

    def save_theme(self) -> None:
        if not self.imported_puzzles:
            messagebox.showwarning("Choose a file", "Choose a word-bank text file first.", parent=self)
            return
        title = self.book_title.get().strip()
        if not title:
            messagebox.showwarning("Add a title", "Add a book title before saving.", parent=self)
            return
        for puzzle in self.imported_puzzles:
            for word in puzzle["words"]:
                if len("".join(char for char in word if char.isalpha())) > 21:
                    messagebox.showwarning("Word is too long", f"'{word}' in '{puzzle['name']}' is longer than the maximum 21-letter grid.", parent=self)
                    return
        data = {"title": title, "subtitle": self.subtitle.get().strip(), "author": self.author.get().strip(), "palette": self.recommendation["palette"], "cover_style": self.recommendation["style"], "detected_topic": self.recommendation["topic"], "puzzles": self.imported_puzzles}
        data["clipart_search_terms"] = clipart_search_terms(data)
        filename = filedialog.asksaveasfilename(title="Save imported theme", initialdir=THEMES_DIR, initialfile=WordSearchCreator._safe_filename(title).lower() + ".json", defaultextension=".json", filetypes=[("JSON theme files", "*.json")])
        if not filename:
            return
        try:
            Path(filename).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Could not save theme", str(exc), parent=self)
            return
        path = Path(filename)
        self.parent._load_theme_list()
        self.parent._set_theme(path)
        messagebox.showinfo("Theme imported", f"Saved {len(self.imported_puzzles)} puzzles and selected the new theme in Book Creator.", parent=self)
        self.destroy()


class BatchGenerationDialog(tk.Toplevel):
    """Generate several checked interiors without risking existing output files."""

    def __init__(self, parent: "WordSearchCreator") -> None:
        super().__init__(parent)
        self.parent = parent
        self.title("Batch Interior PDFs")
        self.geometry("700x560")
        self.minsize(650, 500)
        self.transient(parent)
        self.grab_set()
        self.seed = tk.StringVar(value=parent.seed.get())
        self.status = tk.StringVar(value="Select the themes you want to turn into interior PDFs.")
        self.cancel_requested = threading.Event()
        self.started_at: float | None = None
        self.paths = saved_theme_files()
        self._build()

    def _build(self) -> None:
        frame = ttk.Frame(self, padding=18)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)
        ttk.Label(frame, text="Batch Interior PDFs", font=("Segoe UI", 17, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(
            frame,
            text="Each selected theme is checked first, then saved in a new dated batch folder. Existing PDFs are never overwritten.",
            foreground="#555555", wraplength=640,
        ).grid(row=1, column=0, sticky="w", pady=(4, 12))
        list_frame = ttk.Frame(frame)
        list_frame.grid(row=2, column=0, sticky="nsew")
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        self.theme_list = tk.Listbox(list_frame, selectmode="extended", exportselection=False, height=16)
        self.theme_list.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.theme_list.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.theme_list.configure(yscrollcommand=scroll.set)
        for path in self.paths:
            self.theme_list.insert("end", path.stem.replace("_", " ").title())
        if self.parent.selected_theme in self.paths:
            self.theme_list.selection_set(self.paths.index(self.parent.selected_theme))
        controls = ttk.Frame(frame)
        controls.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        ttk.Button(controls, text="Select All", command=lambda: self.theme_list.selection_set(0, "end")).pack(side="left")
        ttk.Button(controls, text="Clear Selection", command=lambda: self.theme_list.selection_clear(0, "end")).pack(side="left", padx=(8, 0))
        ttk.Label(controls, text="Random seed").pack(side="left", padx=(22, 6))
        ttk.Entry(controls, textvariable=self.seed, width=10).pack(side="left")
        self.run_button = ttk.Button(frame, text="Check and Generate Selected Books", command=self.start)
        self.run_button.grid(row=4, column=0, sticky="ew", pady=(14, 0))
        self.cancel_button = ttk.Button(frame, text="Stop After Current Book", command=self.cancel, state="disabled")
        self.cancel_button.grid(row=5, column=0, sticky="e", pady=(8, 0))
        self.progress = ttk.Progressbar(frame, mode="determinate")
        self.progress.grid(row=6, column=0, sticky="ew", pady=(5, 0))
        ttk.Label(frame, textvariable=self.status, foreground="#245b2a", wraplength=640).grid(row=7, column=0, sticky="w", pady=(10, 0))

    def start(self) -> None:
        selections = self.theme_list.curselection()
        if not selections:
            messagebox.showwarning("Select themes", "Select at least one theme for the batch.", parent=self)
            return
        try:
            seed = int(self.seed.get())
        except ValueError:
            messagebox.showwarning("Random seed", "Random seed must be a whole number.", parent=self)
            return
        selected = [self.paths[index] for index in selections]
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        folder = OUTPUT_DIR / f"batch_{stamp}"
        suffix = 2
        while folder.exists():
            folder = OUTPUT_DIR / f"batch_{stamp}_{suffix}"
            suffix += 1
        try:
            folder.mkdir(parents=True)
        except OSError as exc:
            messagebox.showerror("Cannot create batch folder", str(exc), parent=self)
            return
        self.run_button.configure(state="disabled")
        self.cancel_requested.clear()
        self.started_at = time.monotonic()
        self.progress.configure(maximum=len(selected), value=0)
        self.cancel_button.configure(state="normal")
        self.status.set(f"Checking {len(selected)} selected theme(s)…")
        default_author = self.parent.author.get().strip()
        threading.Thread(target=self._run_batch, args=(selected, seed, folder, default_author), daemon=True).start()

    def _run_batch(self, paths: list[Path], seed: int, folder: Path, default_author: str) -> None:
        successes: list[str] = []
        failures: list[str] = []
        used_output_names: set[str] = set()
        python = WINDOWS_VENV_PYTHON if WINDOWS_VENV_PYTHON.exists() else Path(sys.executable)
        cancelled = False
        for position, path in enumerate(paths, start=1):
            if self.cancel_requested.is_set():
                cancelled = True
                break
            errors, _warnings, _notes = quality_gate(path, seed)
            if errors:
                failures.append(f"{path.stem}: quality check failed ({len(errors)} issue(s)).")
                self.after(0, self._update_progress, position, len(paths))
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8-sig"))
                title = str(data.get("title") or path.stem.replace("_", " "))
                subtitle = str(data.get("subtitle") or "")
                author = str(data.get("author") or default_author)
                base_name = WordSearchCreator._safe_filename(title)
                output = folder / f"{base_name}.pdf"
                suffix = 2
                while output.name.lower() in used_output_names or output.exists():
                    output = folder / f"{base_name}_{suffix}.pdf"
                    suffix += 1
                used_output_names.add(output.name.lower())
                result = subprocess.run(
                    [str(python), str(ENGINE), "--themes", str(path), "--out", str(output),
                     "--title", title, "--subtitle", subtitle, "--author", author, "--seed", str(seed)],
                    cwd=APP_DIR, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW,
                )
                if result.returncode:
                    raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "The generator stopped unexpectedly.")
                successes.append(output.name)
            except Exception as exc:
                failures.append(f"{path.stem}: {exc}")
            self.after(0, self._update_progress, position, len(paths))
        self.after(0, self._finished, folder, successes, failures, cancelled)

    def _update_progress(self, position: int, total: int) -> None:
        self.progress.configure(value=position)
        elapsed = int(time.monotonic() - self.started_at) if self.started_at else 0
        self.status.set(f"Processed {position} of {total} selected theme(s) — {elapsed // 60}m {elapsed % 60:02d}s elapsed.")

    def cancel(self) -> None:
        self.cancel_requested.set()
        self.cancel_button.configure(state="disabled")
        self.status.set("Stopping after the current book is safely finished…")

    def _finished(self, folder: Path, successes: list[str], failures: list[str], cancelled: bool = False) -> None:
        self.run_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")
        if successes:
            os.startfile(folder)
        result = "Stopped" if cancelled else "Finished"
        self.status.set(f"{result}: {len(successes)} created, {len(failures)} needing attention.")
        message = f"Created {len(successes)} interior PDF(s).\n\nBatch folder:\n{folder}"
        if cancelled:
            message = f"Stopped after the current book. Created {len(successes)} interior PDF(s).\n\nBatch folder:\n{folder}"
        if failures:
            message += "\n\nThese were not generated:\n" + "\n".join(f"• {item}" for item in failures[:12])
            if len(failures) > 12:
                message += f"\n• …and {len(failures) - 12} more."
        messagebox.showinfo("Batch generation finished", message, parent=self)


class ProductionQueueDialog(tk.Toplevel):
    """Make complete KDP-ready packages from selected themes and a saved preset."""

    STYLE_LABELS = {"classic": "Classic", "playful": "Playful Illustrated", "retro": "Retro Pop", "sunburst": "Sunburst Poster", "minimal": "Minimal", "gallery": "Gallery Frame", "colorblock": "Color Block"}

    def __init__(self, parent: "WordSearchCreator", initial_paths: list[Path] | None = None) -> None:
        super().__init__(parent)
        self.parent = parent
        self.title("Production Queue")
        self.geometry("710x610")
        self.transient(parent)
        self.grab_set()
        self.paths = saved_theme_files()
        self.initial_paths = set(initial_paths or [])
        self.presets = load_production_presets()
        self.preset_name = tk.StringVar(value=self.presets[0]["name"] if self.presets else "")
        self.palette = tk.StringVar(value="nature")
        self.style = tk.StringVar(value="classic")
        self.imprint = tk.StringVar(value="Slade Puzzles")
        self.author = tk.StringVar(value="Jordan M. Slade")
        self.seed = tk.StringVar(value=parent.seed.get())
        self.status = tk.StringVar(value="Select themes, choose a preset, then create complete book packages.")
        self.archive_after_package = tk.BooleanVar(value=False)
        self.cancel_requested = threading.Event()
        self.started_at: float | None = None
        self._build()
        self._apply_preset()

    def _build(self) -> None:
        frame = ttk.Frame(self, padding=18); frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1); frame.rowconfigure(3, weight=1)
        ttk.Label(frame, text="PRODUCTION QUEUE", font=("Segoe UI", 18, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(frame, text="Each package includes a checked interior PDF, front cover, KDP full wrap, buyer thumbnail, and listing notes.", foreground="#555555", wraplength=650).grid(row=1, column=0, sticky="w", pady=(3, 10))
        settings = ttk.Frame(frame); settings.grid(row=2, column=0, sticky="ew"); settings.columnconfigure(1, weight=1)
        ttk.Label(settings, text="Saved preset").grid(row=0, column=0, sticky="w")
        self.preset_picker = ttk.Combobox(settings, textvariable=self.preset_name, state="readonly", values=[p["name"] for p in self.presets])
        self.preset_picker.grid(row=0, column=1, sticky="ew", padx=(12, 8)); self.preset_picker.bind("<<ComboboxSelected>>", lambda _e: self._apply_preset())
        ttk.Button(settings, text="Save These Settings as Preset…", command=self._save_preset).grid(row=0, column=2)
        ttk.Label(settings, text="Author").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(settings, textvariable=self.author).grid(row=1, column=1, sticky="ew", padx=(12, 8), pady=(8, 0))
        ttk.Label(settings, text="Seed").grid(row=1, column=2, sticky="w", pady=(8, 0))
        ttk.Entry(settings, textvariable=self.seed, width=9).grid(row=1, column=3, pady=(8, 0))
        ttk.Checkbutton(settings, text="Move each successful theme to Used Themes", variable=self.archive_after_package).grid(row=2, column=0, columnspan=4, sticky="w", pady=(8, 0))
        list_frame = ttk.Frame(frame); list_frame.grid(row=3, column=0, sticky="nsew", pady=(12, 0)); list_frame.columnconfigure(0, weight=1); list_frame.rowconfigure(0, weight=1)
        self.theme_list = tk.Listbox(list_frame, selectmode="extended", exportselection=False, height=16); self.theme_list.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.theme_list.yview); scroll.grid(row=0, column=1, sticky="ns"); self.theme_list.configure(yscrollcommand=scroll.set)
        for index, path in enumerate(self.paths):
            self.theme_list.insert("end", path.stem.replace("_", " ").title())
            if path in self.initial_paths:
                self.theme_list.selection_set(index)
        if self.initial_paths:
            self.status.set(f"{len(self.initial_paths)} series book(s) are already selected. Review the preset, then create the packages.")
        controls = ttk.Frame(frame); controls.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(controls, text="Select All", command=lambda: self.theme_list.selection_set(0, "end")).pack(side="left")
        ttk.Button(controls, text="Clear", command=lambda: self.theme_list.selection_clear(0, "end")).pack(side="left", padx=8)
        self.run_button = ttk.Button(frame, text="Create Complete Book Packages", command=self.start); self.run_button.grid(row=5, column=0, sticky="ew", pady=(12, 0))
        self.cancel_button = ttk.Button(frame, text="Stop After Current Book", command=self.cancel, state="disabled"); self.cancel_button.grid(row=6, column=0, sticky="e", pady=(8, 0))
        self.progress = ttk.Progressbar(frame, mode="determinate"); self.progress.grid(row=7, column=0, sticky="ew", pady=(5, 0))
        ttk.Label(frame, textvariable=self.status, foreground="#245b2a", wraplength=650).grid(row=8, column=0, sticky="w", pady=(10, 0))

    def _apply_preset(self) -> None:
        preset = next((p for p in self.presets if p["name"] == self.preset_name.get()), None)
        if preset:
            self.palette.set(preset.get("palette", "nature")); self.style.set(preset.get("style", "classic")); self.imprint.set(preset.get("imprint", "Slade Puzzles"))

    def _save_preset(self) -> None:
        name = simpledialog.askstring("Save production preset", "Name this preset:", parent=self)
        if not name or not name.strip(): return
        try:
            save_production_preset({"name": name.strip(), "palette": self.palette.get(), "style": self.style.get(), "imprint": self.imprint.get()})
        except OSError as exc:
            messagebox.showerror("Could not save preset", str(exc), parent=self); return
        self.presets = load_production_presets(); self.preset_picker["values"] = [p["name"] for p in self.presets]; self.preset_name.set(name.strip()); self.status.set(f"Saved preset: {name.strip()}")

    def start(self) -> None:
        selected = self.theme_list.curselection()
        if not selected: messagebox.showwarning("Select themes", "Select at least one theme.", parent=self); return
        try: seed = int(self.seed.get())
        except ValueError: messagebox.showwarning("Random seed", "Random seed must be a whole number.", parent=self); return
        paths = [self.paths[i] for i in selected]
        settings = {"seed": seed, "author": self.author.get().strip() or "Jordan M. Slade", "palette": self.palette.get(), "style": self.style.get(), "imprint": self.imprint.get(), "preset": self.preset_name.get(), "archive_after_package": self.archive_after_package.get()}
        self.run_button.configure(state="disabled"); self.cancel_requested.clear(); self.started_at=time.monotonic(); self.progress.configure(maximum=len(paths), value=0); self.cancel_button.configure(state="normal"); self.status.set("Protecting the current production inputs, then the queue will begin…")
        threading.Thread(target=self._prepare_run, args=(paths, settings), daemon=True).start()

    def _prepare_run(self, paths: list[Path], settings: dict) -> None:
        try:
            snapshot = automatic_production_snapshot()
        except OSError as exc:
            self.after(0, self._snapshot_failed, str(exc))
            return
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S"); folder = OUTPUT_DIR / f"production_{stamp}"; suffix = 2
        while folder.exists(): folder = OUTPUT_DIR / f"production_{stamp}_{suffix}"; suffix += 1
        try: folder.mkdir(parents=True)
        except OSError as exc: self.after(0, self._snapshot_failed, str(exc)); return
        settings.update({"folder": folder, "snapshot": str(snapshot)})
        self.after(0, self.status.set, f"Safety snapshot saved. Starting {len(paths)} complete book package(s)…")
        self._run(paths, settings)

    def _snapshot_failed(self, detail: str) -> None:
        self.run_button.configure(state="normal"); self.cancel_button.configure(state="disabled")
        self.status.set("The queue did not start because its safety copy could not be created.")
        messagebox.showerror("Could not protect production inputs", f"The production snapshot could not be created, so the queue was not started.\n\n{detail}", parent=self)

    def _run(self, paths: list[Path], settings: dict) -> None:
        from pypdf import PdfReader
        python = WINDOWS_VENV_PYTHON if WINDOWS_VENV_PYTHON.exists() else Path(sys.executable); made=[]; failed=[]; archived=[]; cancelled=False
        for index, path in enumerate(paths, 1):
            if self.cancel_requested.is_set(): cancelled=True; break
            errors, warnings, notes = quality_gate(path, settings["seed"])
            if errors:
                failed.append(f"{path.stem}: quality check failed ({len(errors)} issue(s))")
                self.after(0, self._update_progress, index, len(paths))
                continue
            try:
                data=json.loads(path.read_text(encoding="utf-8-sig")); title=str(data.get("title") or path.stem.replace("_", " ")); subtitle=str(data.get("subtitle") or ""); author=str(data.get("author") or settings["author"]); count=len(data["puzzles"]); palette=str(data.get("palette") or settings["palette"]); style=str(data.get("cover_style") or settings["style"])
                art = Path(str(data.get("cover_art_path") or "")) if str(data.get("cover_art_path") or "").strip() else None
                art_focus = str(data.get("cover_art_focus") or "center")
                preferences = load_cover_preferences(path)
                preferred_art = Path(str(preferences.get("art") or "")) if str(preferences.get("art") or "").strip() else None
                if preferred_art and preferred_art.exists() and BackgroundAssetIndex().ledger_details(preferred_art):
                    art = preferred_art
                    art_focus = str(preferences.get("art_focus") or art_focus)
                if not art or not art.exists() or not BackgroundAssetIndex().ledger_details(art):
                    choice = recommend_background_photo(data)
                    suggested_art = APP_DIR / str(choice.get("file") or "") if choice else None
                    if suggested_art and suggested_art.exists() and BackgroundAssetIndex().ledger_details(suggested_art):
                        art = suggested_art
                        art_focus = str(choice.get("focus") or "center")
                        palette = photo_choice_palette(choice, palette)
                    else:
                        raise RuntimeError(
                            "COVER ART REQUIRED - no approved topic-matched background is available. "
                            "Approve a suitable asset before starting this book."
                        )
                book_folder=settings["folder"] / WordSearchCreator._safe_filename(title); book_folder.mkdir()
                interior=book_folder / "interior.pdf"; front=book_folder / "front_cover.png"; wrap=book_folder / "kdp_full_wrap.pdf"; badge=str(data.get("cover_badge") or ("NO REPEATED WORDS" if data.get("no_repeat_words") else f"INCLUDES {count} PUZZLES")); difficulty=puzzle_difficulty_label(data)
                cover_command=[str(python),str(COVER_ENGINE),"--title",title,"--subtitle",subtitle,"--author",author,"--badge",badge,"--puzzle-count",str(count),"--difficulty",difficulty,"--format-label","LARGE PRINT" if book_format_label(data) == "LARGE PRINT PUZZLES" else "WORD SEARCH","--palette",palette,"--style",style,"--theme-file",str(path),"--out",str(front)]
                cover_command.extend(["--art", str(art), "--art-focus", art_focus])
                for command in ([str(python),str(ENGINE),"--themes",str(path),"--out",str(interior),"--title",title,"--subtitle",subtitle,"--author",author,"--seed",str(settings["seed"])],cover_command):
                    result=subprocess.run(command,cwd=APP_DIR,capture_output=True,text=True,creationflags=subprocess.CREATE_NO_WINDOW)
                    if result.returncode: raise RuntimeError(result.stderr.strip() or result.stdout.strip())
                package_data=package_data_from_settings(data,{"title":title,"subtitle":subtitle,"author":author,"palette":palette,"style":style,"badge":badge,"art":str(art) if art else "","art_focus":art_focus})
                pages=len(PdfReader(str(interior)).pages); blurb=package_blurb(data, package_data)
                preview=book_folder / "kdp_full_wrap_preview.png"
                result=subprocess.run([str(python),str(WRAP_ENGINE),"--front",str(front),"--pages",str(pages),"--palette",palette,"--title",title,"--author",author,"--back",blurb,"--out",str(wrap),"--preview-out",str(preview)],cwd=APP_DIR,capture_output=True,text=True,creationflags=subprocess.CREATE_NO_WINDOW)
                if result.returncode: raise RuntimeError(result.stderr.strip() or result.stdout.strip())
                preflight_ok, preflight_lines=preflight(book_folder)
                (book_folder / "PUBLISHER_PREFLIGHT.txt").write_text(package_preflight_text(book_folder), encoding="utf-8")
                if not preflight_ok: raise RuntimeError("Print preflight needs attention: " + " | ".join(preflight_lines))
                package_warnings=list(warnings)+list(publisher_safety_report(package_data)["warnings"])
                (book_folder / "listing_notes.txt").write_text(listing_kit_text(package_data) + f"\nPRODUCTION PRESET\n{settings['preset']}\n", encoding="utf-8")
                (book_folder / "KDP_LISTING_KIT.txt").write_text(listing_kit_text(package_data), encoding="utf-8")
                (book_folder / "KDP_UPLOAD_CHECKLIST.txt").write_text(kdp_upload_checklist_text(package_data, pages), encoding="utf-8")
                write_kdp_compliance_report(book_folder, package_data, pages)
                (book_folder / "PACKAGE_SCORECARD.txt").write_text(package_scorecard_text(package_data, book_folder, pages, package_warnings), encoding="utf-8")
                (book_folder / "quality_report.txt").write_text("READY TO GENERATE\n\n" + "\n".join(notes + package_warnings + preflight_lines),encoding="utf-8"); record_package_created(path, title, book_folder, pages); made.append(title)
                if settings.get("archive_after_package"):
                    try:
                        archive_used_theme(path); archived.append(title)
                    except OSError as exc:
                        failed.append(f"{path.stem}: package created, but the theme was not moved ({exc})")
            except Exception as exc: failed.append(f"{path.stem}: {exc}")
            self.after(0,self._update_progress,index,len(paths))
        self.after(0,self._finished,settings["folder"],made,failed,archived,cancelled)

    def _update_progress(self, position: int, total: int) -> None:
        self.progress.configure(value=position)
        elapsed=int(time.monotonic()-self.started_at) if self.started_at else 0
        self.status.set(f"Processed {position} of {total} book(s) — {elapsed // 60}m {elapsed % 60:02d}s elapsed.")

    def cancel(self) -> None:
        self.cancel_requested.set(); self.cancel_button.configure(state="disabled")
        self.status.set("Stopping after the current book package is safely finished…")

    def _finished(self, folder: Path, made: list[str], failed: list[str], archived: list[str], cancelled: bool = False) -> None:
        self.run_button.configure(state="normal"); self.cancel_button.configure(state="disabled"); self.status.set(f"{'Stopped' if cancelled else 'Finished'}: {len(made)} package(s) created, {len(failed)} needing attention.")
        if made: os.startfile(folder)
        message=(f"Stopped after the current book. Created {len(made)} complete package(s)." if cancelled else f"Created {len(made)} complete package(s).") + f"\n\n{folder}" + ("\n\nNot created:\n" + "\n".join(f"• {x}" for x in failed[:10]) if failed else "")
        if archived:
            self.parent._load_theme_list()
            message += f"\n\nMoved {len(archived)} completed theme(s) to Themes\\Used Themes."
        messagebox.showinfo("Production queue finished",message,parent=self)


class CoverVariantGallery(tk.Toplevel):
    OPTIONS = [("Gallery Frame","midnight-gold"),("Color Block","tropical-pop"),("Halo Spotlight","royal-plum"),("Ticket Stub","autumn-harvest"),("Diagonal Stripe","coastal-blue"),("Retro Pop","berry-blush")]
    def __init__(self,parent):
        super().__init__(parent); self.parent=parent; self.title("Cover Gallery"); self.geometry("900x700"); self.transient(parent); self.status=tk.StringVar(value="Creating six distinct cover ideas…"); self.images=[]; self.refresh_offset=0
        self.settings = parent._studio_cover_settings()
        ttk.Label(self,text="COVER VARIATIONS",font=("Segoe UI",18,"bold")).pack(anchor="w",padx=18,pady=(18,2)); ttk.Label(self,text="Compare strong cover directions at Amazon-style thumbnail size. If you selected a picture, Photo Hero is included too. Click one to apply it in Book Studio.").pack(anchor="w",padx=18)
        self.grid_frame=ttk.Frame(self,padding=18); self.grid_frame.pack(fill="both",expand=True); footer=ttk.Frame(self); footer.pack(fill="x",padx=18,pady=(0,14)); ttk.Label(footer,textvariable=self.status).pack(side="left",fill="x",expand=True); ttk.Button(footer,text="Refresh Cover Ideas",command=self.refresh).pack(side="right"); threading.Thread(target=self._make,daemon=True).start()
    def _make(self):
        settings=self.settings
        if not settings: self.after(0,self.destroy); return
        folder=OUTPUT_DIR/"cover_ideas"; folder.mkdir(exist_ok=True); python=WINDOWS_VENV_PYTHON if WINDOWS_VENV_PYTHON.exists() else Path(sys.executable)
        made=[]; theme_data={}
        try: theme_data=json.loads(Path(settings["theme"]).read_text(encoding="utf-8-sig"))
        except (OSError,json.JSONDecodeError): pass
        request=CoverRequest(route="Word Search Cover Gallery",title=settings["title"],subtitle=settings["subtitle"],puzzle_type="Word Search",topic=str(theme_data.get("detected_topic") or theme_data.get("theme") or settings["title"]),audience=str(theme_data.get("audience") or "general"),series=str(theme_data.get("series") or ""),palette=settings.get("palette",""))
        gallery=select_cover_gallery(request,slots=6,refresh_offset=self.refresh_offset)
        labels={"photo":"Photo Hero","gallery":"Gallery Frame","bold":"Bold Spotlight","minimal":"Minimal","colorblock":"Color Block","retro":"Retro Pop"}
        for i,concept in enumerate(gallery.concepts):
            style=concept.cover_template_id; label=labels.get(style,"Photo Hero"); palette=concept.palette; art=str(APP_DIR/str(concept.asset.get("path") or "")); out=folder/f"idea_{i}.png"; command=[str(python),str(COVER_ENGINE),"--title",settings["title"],"--subtitle",settings["subtitle"],"--author",settings["author"],"--badge",settings["badge"],"--puzzle-count",str(settings.get("puzzle_count", 0)),"--difficulty",settings["difficulty"],"--format-label",settings.get("format_label","WORD SEARCH"),"--palette",palette,"--style",style,"--theme-file",settings["theme"],"--out",str(out),"--preview","--art",art,"--art-focus",str(concept.asset.get("focus") or "center")]
            result=subprocess.run(command,cwd=APP_DIR,capture_output=True,text=True,creationflags=subprocess.CREATE_NO_WINDOW)
            if not result.returncode: made.append((label,palette,art,str(concept.asset.get("focus") or "center"),out))
        self.after(0,self._show,made,gallery.metrics)
    def _show(self,made,metrics=None):
        for child in self.grid_frame.winfo_children(): child.destroy()
        self.images.clear()
        for i,(label,palette,art,focus,path) in enumerate(made):
            image=Image.open(path); image.thumbnail((210,275),Image.LANCZOS); photo=ImageTk.PhotoImage(image); self.images.append(photo)
            button=tk.Button(self.grid_frame,image=photo,text=f"{label}\n{palette}",compound="top",command=lambda l=label,p=palette,a=art,f=focus:self.choose(l,p,a,f)); button.grid(row=i//3,column=i%3,padx=10,pady=8)
        metrics=metrics or {}; note=f" Diversity limited: {metrics.get('eligible_visual_family_count',0)} suitable families." if metrics.get("diversity_limited") else ""
        self.status.set(f"{len(made)} concepts using {metrics.get('distinct_visual_families_shown',0)} unique artwork families are ready.{note}")
    def choose(self,label,palette,art,focus):
        self.parent.cover_style.set(label); self.parent.cover_palette.set(palette); self.parent.cover_art.set(art); self.parent.cover_art_focus.set(focus); self.parent.status.set(f"Applied cover concept: {label} / {palette}."); self.destroy()
    def refresh(self):
        self.refresh_offset += 1; self.status.set("Reranking approved existing artwork…"); threading.Thread(target=self._make,daemon=True).start()


class SafeCoverPreview(tk.Toplevel):
    """A buyer-size preview with a conservative text-safe guide."""

    def __init__(self, parent: tk.Widget, path: Path) -> None:
        super().__init__(parent)
        self.title("Cover Preview + Safe Guide")
        self.transient(parent)
        image = Image.open(path).convert("RGB")
        image.thumbnail((510, 660), Image.LANCZOS)
        self.photo = ImageTk.PhotoImage(image)
        canvas = tk.Canvas(self, width=510, height=660, highlightthickness=0)
        canvas.pack(padx=18, pady=(18, 8))
        canvas.create_image(0, 0, anchor="nw", image=self.photo)
        # A deliberately conservative inner margin: keep key text and badges inside it.
        canvas.create_rectangle(18, 18, 492, 642, outline="#e23d4e", width=2, dash=(5, 3))
        canvas.create_text(255, 31, text="KEEP IMPORTANT TEXT INSIDE THIS GUIDE", fill="#e23d4e", font=("Segoe UI", 8, "bold"))
        ttk.Label(self, text="Preview only: the dashed line is a conservative safe-text guide. Always use KDP Print Previewer for the final approval.", wraplength=500, justify="center").pack(padx=18, pady=(0, 16))


class OpenClipartPickerDialog(tk.Toplevel):
    """Search only the CC0 OpenClipart dataset and cache an explicit choice."""

    def __init__(self, parent: "WordSearchCreator", query: str, on_selected) -> None:
        super().__init__(parent)
        self.parent = parent
        self.on_selected = on_selected
        self.title("OpenClipart Cover Art")
        self.geometry("920x700")
        self.minsize(720, 520)
        self.transient(parent)
        self.query = tk.StringVar(value=query)
        self.status = tk.StringVar(value="Search CC0 OpenClipart by your book’s suggested keywords.")
        self.images: list[ImageTk.PhotoImage] = []
        self.results: list[dict[str, object]] = []
        self.thumbnail_labels: dict[int, ttk.Label] = {}
        self.collections = {
            "Suggested for this book": query, "Animals & pets": "friendly animal", "National parks": "mountain forest",
            "Space": "planet rocket", "Cars & trucks": "car truck", "Gardening": "garden flower",
            "Christmas": "christmas holiday", "Halloween": "halloween pumpkin", "Travel": "travel map",
        }
        self.collection = tk.StringVar(value="Suggested for this book")
        frame = ttk.Frame(self, padding=18); frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1); frame.rowconfigure(3, weight=1)
        ttk.Label(frame, text="OPENCLIPART COVER ART", font=("Segoe UI", 17, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(frame, text="CC0 source • commercial use allowed • only the image you choose is saved. Items marked for review are hidden automatically.", wraplength=850).grid(row=1, column=0, sticky="w", pady=(2, 12))
        search = ttk.Frame(frame); search.grid(row=2, column=0, sticky="ew", pady=(0, 10)); search.columnconfigure(1, weight=1)
        ttk.Combobox(search, textvariable=self.collection, values=tuple(self.collections), state="readonly", width=22).grid(row=0, column=0, padx=(0, 8))
        self.collection.trace_add("write", self._collection_changed)
        ttk.Entry(search, textvariable=self.query).grid(row=0, column=1, sticky="ew")
        ttk.Button(search, text="Search", command=self.search, style="Primary.TButton").grid(row=0, column=2, padx=(8, 0))
        ttk.Button(search, text="Use best match", command=self.use_best, style="Action.TButton").grid(row=0, column=3, padx=(8, 0))
        self.canvas = tk.Canvas(frame, highlightthickness=0); self.canvas.grid(row=3, column=0, sticky="nsew")
        bar = ttk.Scrollbar(frame, orient="vertical", command=self.canvas.yview); bar.grid(row=3, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=bar.set)
        self.grid_frame = ttk.Frame(self.canvas); self.grid_window = self.canvas.create_window((0, 0), window=self.grid_frame, anchor="nw")
        self.grid_frame.bind("<Configure>", lambda _event: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda event: self.canvas.itemconfigure(self.grid_window, width=event.width))
        footer = ttk.Frame(frame); footer.grid(row=4, column=0, sticky="ew", pady=(10, 0)); footer.columnconfigure(0, weight=1)
        ttk.Label(footer, textvariable=self.status, wraplength=680).grid(row=0, column=0, sticky="w")
        ttk.Button(footer, text="My saved pictures", command=self.show_saved).grid(row=0, column=1, padx=(8, 0))
        ttk.Button(footer, text="Open website", command=self.open_website).grid(row=0, column=2, padx=(8, 0))
        self.search()

    def _collection_changed(self, *_args: object) -> None:
        value = self.collections.get(self.collection.get())
        if value:
            self.query.set(value)

    def use_best(self) -> None:
        if self.results:
            self.use(self.results[0])
        else:
            self.status.set("Search first, then I can choose the strongest safe match.")

    def search(self) -> None:
        query = self.query.get().strip()
        if not query:
            return
        self.status.set("Searching OpenClipart in the background…")
        for child in self.grid_frame.winfo_children(): child.destroy()
        threading.Thread(target=self._search_worker, args=(query,), daemon=True).start()

    def _search_worker(self, query: str) -> None:
        try:
            choices = search_openclipart(query)
            self.after(0, self._show_results, choices)
        except Exception as exc:
            self.after(0, self._search_failed, str(exc))

    def _search_failed(self, detail: str) -> None:
        self.status.set("OpenClipart search is unavailable right now. You can open the website, download an image, and use Choose downloaded image instead.")
        ttk.Label(self.grid_frame, text="No results loaded. The online fallback is available below.", padding=20).grid(row=0, column=0, sticky="w")
        log_plain_error("OpenClipart search", self.parent.book_title.get(), detail, "Try the OpenClipart website, then choose a downloaded image. Your existing cover workflow still works.")

    def _show_results(self, choices: list[dict[str, object]]) -> None:
        self.results = choices; self.images.clear()
        self.thumbnail_labels.clear()
        if not choices:
            self.status.set("No review-safe matches found. Try one simple word, such as garden, dog, telescope, or camper.")
            return
        for index, choice in enumerate(choices):
            card = ttk.Frame(self.grid_frame, padding=8, relief="solid"); card.grid(row=index // 3, column=index % 3, sticky="nsew", padx=6, pady=6)
            image_label = ttk.Label(card, text="Loading preview…", width=24, anchor="center"); image_label.pack(pady=(35, 35))
            self.thumbnail_labels[index] = image_label
            title = str(choice.get("title") or "Untitled clipart")[:58]
            ttk.Label(card, text=title, wraplength=200, justify="center", font=("Segoe UI", 9, "bold")).pack()
            ttk.Label(card, text=f"by {str(choice.get('artist_name') or 'OpenClipart contributor')[:32]} • CC0 • review-safe", wraplength=200, justify="center").pack(pady=(2, 6))
            ttk.Button(card, text="Use this image", command=lambda item=choice: self.use(item), style="Action.TButton").pack(fill="x")
        self.status.set(f"Showing {len(choices)} CC0 choices. Select one to download it and apply the best cover placement.")
        threading.Thread(target=self._load_thumbnails, args=(choices[:12],), daemon=True).start()

    def _load_thumbnails(self, choices: list[dict[str, object]]) -> None:
        for index, choice in enumerate(choices):
            try:
                image_bytes = fetch_thumbnail(str(choice["thumbnail_url"]))
                self.after(0, self._show_thumbnail, index, image_bytes)
            except Exception:
                self.after(0, self._show_thumbnail, index, None)

    def _show_thumbnail(self, index: int, image_bytes: bytes | None) -> None:
        label = self.thumbnail_labels.get(index)
        if not label or not label.winfo_exists():
            return
        if image_bytes:
            try:
                image = Image.open(BytesIO(image_bytes)).convert("RGB"); image.thumbnail((190, 145), Image.LANCZOS)
                photo = ImageTk.PhotoImage(image); self.images.append(photo)
                label.configure(image=photo, text=""); label.image = photo
                return
            except (OSError, ValueError):
                pass
        label.configure(text="Preview unavailable\nUse the source page to inspect it.")

    def use(self, choice: dict[str, object]) -> None:
        self.status.set("Saving your selected OpenClipart image and its license record…")
        threading.Thread(target=self._download_worker, args=(choice,), daemon=True).start()

    def _download_worker(self, choice: dict[str, object]) -> None:
        try:
            path, record = download_openclipart(choice, COVER_ASSETS_DIR)
            self.after(0, self._finish_use, path, record)
        except Exception as exc:
            self.after(0, self._search_failed, str(exc))

    def _finish_use(self, path: Path, record: dict[str, object]) -> None:
        save_art_favorite(record)
        self.on_selected(path, record)
        self.destroy()

    def show_saved(self) -> None:
        records = _read_art_records(COVER_ASSETS_DIR / "openclipart" / "selected_assets.json")
        records = [record for record in records if Path(str(record.get("local_file", ""))).exists()]
        for child in self.grid_frame.winfo_children(): child.destroy()
        if not records:
            self.status.set("No saved pictures yet. Choose one from a search and it will appear here for future books.")
            return
        for index, record in enumerate(records):
            card = ttk.Frame(self.grid_frame, padding=8, relief="solid"); card.grid(row=index // 3, column=index % 3, sticky="nsew", padx=6, pady=6)
            title = str(record.get("title") or Path(str(record.get("local_file"))).stem)[:58]
            ttk.Label(card, text="Saved picture", font=("Segoe UI", 9, "bold")).pack(pady=(12, 4))
            ttk.Label(card, text=title, wraplength=200, justify="center").pack()
            ttk.Button(card, text="Use this picture", command=lambda item=record: self.use_saved(item), style="Action.TButton").pack(fill="x", pady=(8, 0))
        self.status.set(f"Showing {len(records)} saved CC0 picture(s). These are reusable and keep their license record.")

    def use_saved(self, record: dict[str, object]) -> None:
        path = Path(str(record.get("local_file", "")))
        if path.exists():
            self.on_selected(path, record); self.destroy()

    def open_website(self) -> None:
        webbrowser.open(f"https://openclipart.org/search/?query={quote_plus(self.query.get().strip())}")


class ReleaseManagerDialog(tk.Toplevel):
    """My Books Dashboard with a local KDP companion and report import."""

    STAGES = ("Draft", "Tested", "Ready", "Published", "Paused")

    def __init__(self, parent: "WordSearchCreator") -> None:
        super().__init__(parent)
        self.parent = parent
        self.title("My Books Dashboard")
        self.geometry("1120x700")
        self.minsize(880, 520)
        self.transient(parent)
        self.catalog = load_release_catalog()
        self.rows: dict[str, tuple[Path, dict]] = {}
        self.stage = tk.StringVar(value="Draft")
        self.details = tk.StringVar(value="Select a book to see its KDP and package details.")
        self.status = tk.StringVar(value="Manage your books, create listing kits, and import KDP reports here.")
        self._build()
        self.refresh()

    def _build(self) -> None:
        frame = ttk.Frame(self, padding=18)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)
        ttk.Label(frame, text="MY BOOKS DASHBOARD", font=("Segoe UI", 18, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(frame, text="Your local publishing control center. Create listing kits, track KDP details, open packages, and import the report you download from KDP.", foreground="#555555", wraplength=1010).grid(row=1, column=0, sticky="w", pady=(3, 12))
        columns = ("title", "stage", "location", "puzzles", "price", "kdp", "orders", "royalties")
        self.tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse")
        headings = {"title": "Book", "stage": "Stage", "location": "Theme location", "puzzles": "Puzzles", "price": "Suggested price", "kdp": "KDP", "orders": "Orders", "royalties": "Royalties"}
        widths = {"title": 270, "stage": 92, "location": 105, "puzzles": 65, "price": 105, "kdp": 75, "orders": 65, "royalties": 90}
        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(column, width=widths[column], anchor="w" if column in ("title", "location") else "center")
        self.tree.grid(row=2, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        scroll.grid(row=2, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<<TreeviewSelect>>", self._selected)
        controls = ttk.Frame(frame)
        controls.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        ttk.Button(controls, text="Open for Revision", command=self.use_in_studio).pack(side="left")
        ttk.Button(controls, text="Create Listing Kit", command=self.create_listing_kit).pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="Open Package", command=self.open_package).pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="Run Release Audit", command=self.run_release_audit).pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="KDP / ASIN Details…", command=self.edit_kdp_details).pack(side="left", padx=(8, 0))
        ttk.Label(controls, text="Set selected book to").pack(side="left", padx=(18, 6))
        ttk.Combobox(controls, textvariable=self.stage, values=self.STAGES, state="readonly", width=12).pack(side="left")
        ttk.Button(controls, text="Save Stage", command=self.save_stage).pack(side="left", padx=8)
        tools = ttk.Frame(frame)
        tools.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(tools, text="Open KDP Bookshelf", command=self.open_kdp).pack(side="left")
        ttk.Button(tools, text="Open Amazon Page", command=self.open_amazon).pack(side="left", padx=8)
        ttk.Button(tools, text="Preview Cover", command=self.preview_cover).pack(side="left")
        ttk.Button(tools, text="Import KDP CSV…", command=self.import_kdp_report).pack(side="right")
        ttk.Button(tools, text="Refresh", command=self.refresh).pack(side="right", padx=8)
        ttk.Label(frame, textvariable=self.details, foreground="#555555", wraplength=1010).grid(row=5, column=0, sticky="w", pady=(12, 0))
        ttk.Label(frame, textvariable=self.status, foreground="#245b2a", wraplength=1010).grid(row=6, column=0, sticky="w", pady=(8, 0))

    @staticmethod
    def _clean_title(value: object) -> str:
        return re.sub(r"[^a-z0-9]", "", str(value).lower())

    def refresh(self) -> None:
        self.catalog = load_release_catalog()
        self.rows.clear()
        self.tree.delete(*self.tree.get_children())
        for index, path in enumerate(all_book_theme_files()):
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            key = path.name
            record = self.catalog.get(key, {})
            title = str(data.get("title") or path.stem.replace("_", " "))
            location = "Used Themes" if USED_THEMES_DIR in path.parents else "Active Themes"
            default_stage = "Ready" if location == "Used Themes" else "Draft"
            stage = str(record.get("stage") or default_stage)
            orders = int(record.get("orders") or 0)
            royalties = float(record.get("royalties") or 0)
            price, _royalty = recommended_us_paperback_price(estimated_page_count(data), is_signature_edition(data))
            linked = "Linked" if record.get("asin") or record.get("kdp_url") else "Not linked"
            iid = f"book_{index}"
            self.rows[iid] = (path, data)
            self.tree.insert("", "end", iid=iid, values=(title, stage, location, len(data.get("puzzles", [])), f"${price:.2f}", linked, orders or "—", f"${royalties:.2f}" if royalties else "—"))
        self.status.set(f"Tracking {len(self.rows)} book theme(s).")

    def _selected(self, _event: object = None) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        path, data = self.rows[selected[0]]
        record = self.catalog.get(path.name, {})
        self.stage.set(str(record.get("stage") or ("Ready" if USED_THEMES_DIR in path.parents else "Draft")))
        package = self._package_folder(path, data)
        page_count = estimated_page_count(data)
        self.details.set(
            f"{len(data.get('puzzles', []))} puzzles • about {page_count} interior pages • "
            f"ASIN: {record.get('asin') or 'not saved'} • "
            f"Package: {package if package else 'not created yet'}"
        )

    def save_stage(self) -> None:
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Choose a book", "Select a book first.", parent=self)
            return
        path, _data = self.rows[selected[0]]
        record = self.catalog.setdefault(path.name, {})
        record["stage"] = self.stage.get()
        record["updated"] = datetime.now().isoformat(timespec="seconds")
        save_release_catalog(self.catalog)
        self.refresh()
        self.status.set(f"Saved {self.stage.get()} status for {path.name}.")

    def _current_book(self) -> tuple[Path, dict] | None:
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Choose a book", "Select a book first.", parent=self)
            return None
        return self.rows[selected[0]]

    def _package_folder(self, path: Path, data: dict) -> Path | None:
        """Find the most recent complete package for this book, if one exists."""
        recorded_value = str(self.catalog.get(path.name, {}).get("package") or "").strip()
        recorded = Path(recorded_value) if recorded_value else None
        if recorded and recorded.is_dir():
            return recorded
        return find_latest_book_package(str(data.get("title") or path.stem))

    def use_in_studio(self) -> None:
        current = self._current_book()
        if not current:
            return
        path, _data = current
        self.parent._set_theme(path)
        self.parent.deiconify()
        self.parent.lift()
        self.status.set("Loaded the selected book for revision. Update only what needs fixing, then create a new complete package; your original package stays untouched.")

    def run_release_audit(self) -> None:
        """Re-open the plain-English final report without changing a completed book."""
        current = self._current_book()
        if not current:
            return
        path, data = current
        folder = self._package_folder(path, data)
        if not folder:
            messagebox.showinfo("No package yet", "Create a Complete Book Package first. The release audit is saved with the finished package.", parent=self)
            return
        report = folder / "FIX_THIS_FIRST.txt"
        if not report.exists():
            messagebox.showinfo("Older package", "This package was made before the release audit. Open it for revision and create a fresh package to add the current publishing safety reports.", parent=self)
            return
        os.startfile(report)
        self.status.set("Opened the package’s Fix This First report.")

    def create_listing_kit(self) -> None:
        current = self._current_book()
        if not current:
            return
        path, data = current
        try:
            kit = write_listing_kit(path, data, self.catalog.get(path.name, {}))
            os.startfile(kit)
            self.status.set(f"Created listing kit: {kit.name}")
        except OSError as exc:
            messagebox.showerror("Could not create listing kit", str(exc), parent=self)

    def open_package(self) -> None:
        current = self._current_book()
        if not current:
            return
        path, data = current
        folder = self._package_folder(path, data)
        if not folder:
            messagebox.showinfo("No package yet", "Create a Complete Book Package first. The finished interior, cover, wrap, and listing notes will appear here.", parent=self)
            return
        os.startfile(folder)

    def preview_cover(self) -> None:
        current = self._current_book()
        if not current:
            return
        path, data = current
        folder = self._package_folder(path, data)
        cover = package_file(folder, "front_cover.png") if folder else None
        if not cover or not cover.exists():
            messagebox.showinfo("No cover yet", "Create a Complete Book Package first, then its cover preview will be available here.", parent=self)
            return
        os.startfile(cover)

    def edit_kdp_details(self) -> None:
        current = self._current_book()
        if not current:
            return
        path, data = current
        record = self.catalog.setdefault(path.name, {})
        asin = simpledialog.askstring("KDP / Amazon details", f"ASIN for {data.get('title', path.stem)} (leave blank until KDP creates it):", initialvalue=str(record.get("asin") or ""), parent=self)
        if asin is None:
            return
        link = simpledialog.askstring("KDP / Amazon details", "Amazon product or KDP Bookshelf link (optional):", initialvalue=str(record.get("kdp_url") or ""), parent=self)
        if link is None:
            return
        record["asin"] = asin.strip()
        record["kdp_url"] = link.strip()
        record["updated"] = datetime.now().isoformat(timespec="seconds")
        save_release_catalog(self.catalog)
        self.refresh()
        self.status.set("Saved KDP / Amazon details.")

    def open_kdp(self) -> None:
        current = self._current_book()
        if not current:
            return
        path, _data = current
        link = str(self.catalog.get(path.name, {}).get("kdp_url") or "")
        webbrowser.open(link if link else "https://kdp.amazon.com/en_US/bookshelf")
        self.status.set("Opened the saved KDP link, or your KDP Bookshelf.")

    def open_amazon(self) -> None:
        current = self._current_book()
        if not current:
            return
        path, data = current
        record = self.catalog.get(path.name, {})
        asin = str(record.get("asin") or "").strip()
        if asin:
            webbrowser.open(f"https://www.amazon.com/dp/{quote_plus(asin)}")
        else:
            webbrowser.open(f"https://www.amazon.com/s?k={quote_plus(str(data.get('title') or 'word search'))}")
        self.status.set("Opened the Amazon product page, or an Amazon search until an ASIN is saved.")

    def import_kdp_report(self) -> None:
        filename = filedialog.askopenfilename(title="Choose downloaded KDP report", filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if not filename:
            return
        try:
            with open(filename, "r", encoding="utf-8-sig", newline="") as report:
                rows = list(csv.DictReader(report))
            if not rows:
                raise ValueError("The selected report has no rows.")
            headers = {header.lower(): header for header in rows[0] if header}
            title_key = next((value for key, value in headers.items() if "title" in key), None)
            order_key = next((value for key, value in headers.items() if "net units" in key or "units sold" in key or key == "units"), None)
            royalty_key = next((value for key, value in headers.items() if "royalty" in key), None)
            if not title_key:
                raise ValueError("Could not find a Title column in this CSV.")
            lookup = {self._clean_title(data.get("title")): path.name for path, data in self.rows.values()}
            totals: dict[str, list[float]] = {}
            for row in rows:
                key = lookup.get(self._clean_title(row.get(title_key, "")))
                if not key:
                    continue
                total = totals.setdefault(key, [0.0, 0.0])
                if order_key:
                    try: total[0] += float(str(row.get(order_key, "0")).replace(",", "") or 0)
                    except ValueError: pass
                if royalty_key:
                    try: total[1] += float(re.sub(r"[^0-9.-]", "", str(row.get(royalty_key, "0"))) or 0)
                    except ValueError: pass
            for key, (orders, royalties) in totals.items():
                record = self.catalog.setdefault(key, {})
                record["orders"] = int(orders)
                record["royalties"] = royalties
                record["last_kdp_import"] = datetime.now().isoformat(timespec="seconds")
            save_release_catalog(self.catalog)
            self.refresh()
            self.status.set(f"Imported KDP results for {len(totals)} matching book(s).")
        except (OSError, ValueError, csv.Error) as exc:
            messagebox.showerror("Could not import KDP report", str(exc), parent=self)

    def market_watch(self) -> None:
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Choose a book", "Select a book to open its market searches.", parent=self)
            return
        _path, data = self.rows[selected[0]]
        title = str(data.get("title") or "word search")
        query = quote_plus(title)
        webbrowser.open(f"https://trends.google.com/trends/explore?q={query}")
        webbrowser.open(f"https://www.amazon.com/s?k={query}")
        self.status.set("Opened Google Trends and an Amazon search for the selected book.")


class VisualProofingDialog(tk.Toplevel):
    """One calm place to review a finished package before KDP upload."""
    def __init__(self, parent: "WordSearchCreator") -> None:
        super().__init__(parent)
        self.parent = parent
        self.title("Visual Proofing Center")
        self.geometry("980x700")
        self.minsize(820, 600)
        self.transient(parent)
        self.status = tk.StringVar(value="Run the proof check to review this book and its finished package.")
        self.summary = tk.StringVar(value="Choose a theme in Book Studio first.")
        self.package: Path | None = None
        self.cover_image: ImageTk.PhotoImage | None = None
        self.wrap_image: ImageTk.PhotoImage | None = None
        self.blocking_issues: list[str] = []
        self._build()
        self.run_proof()

    def _build(self) -> None:
        frame = ttk.Frame(self, padding=18); frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1); frame.columnconfigure(1, weight=1); frame.rowconfigure(2, weight=1)
        ttk.Label(frame, text="VISUAL PROOFING CENTER", font=("Segoe UI", 18, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(frame, text="Review the cover, full wrap, and readiness checks before you upload. This never changes your book files.", foreground="#555555").grid(row=1, column=0, columnspan=2, sticky="w", pady=(3, 12))
        left = ttk.Labelframe(frame, text="FRONT COVER", padding=10, style="Section.TLabelframe"); left.grid(row=2, column=0, sticky="nsew", padx=(0, 8))
        right = ttk.Labelframe(frame, text="FULL KDP WRAP", padding=10, style="Section.TLabelframe"); right.grid(row=2, column=1, sticky="nsew", padx=(8, 0))
        self.cover_label = ttk.Label(left, text="No front cover found yet.", anchor="center"); self.cover_label.pack(fill="both", expand=True)
        self.wrap_label = ttk.Label(right, text="No full-wrap preview found yet.", anchor="center"); self.wrap_label.pack(fill="both", expand=True)
        check = ttk.Labelframe(frame, text="READINESS", padding=12, style="Section.TLabelframe"); check.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        ttk.Label(check, textvariable=self.summary, wraplength=900, justify="left").pack(anchor="w")
        actions = ttk.Frame(frame); actions.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        for column in range(5): actions.columnconfigure(column, weight=1)
        ttk.Button(actions, text="Run Proof Again", command=self.run_proof, style="Action.TButton").grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(actions, text="Open Interior PDF", command=lambda: self._open_file("interior.pdf"), style="Action.TButton").grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Button(actions, text="Open KDP Wrap PDF", command=lambda: self._open_file("kdp_full_wrap.pdf"), style="Action.TButton").grid(row=0, column=2, sticky="ew", padx=4)
        self.approve_button = ttk.Button(actions, text="Mark Proof Approved", command=self.mark_approved, style="Primary.TButton", state="disabled"); self.approve_button.grid(row=0, column=3, sticky="ew", padx=4)
        ttk.Button(actions, text="Open Package", command=self.open_package, style="Action.TButton").grid(row=0, column=4, sticky="ew", padx=(4, 0))
        ttk.Label(frame, textvariable=self.status, style="Status.TLabel", wraplength=900).grid(row=5, column=0, columnspan=2, sticky="ew", pady=(14, 0))

    def _show_image(self, label: ttk.Label, target: Path, attribute: str, max_size: tuple[int, int]) -> None:
        if not target.exists(): return
        try:
            image = Image.open(target); image.thumbnail(max_size, Image.LANCZOS)
            photo = ImageTk.PhotoImage(image); setattr(self, attribute, photo)
            label.configure(image=photo, text="")
        except OSError:
            label.configure(text=f"Could not display {target.name}.")

    def run_proof(self) -> None:
        if not self.parent.selected_theme:
            self.status.set("Choose a theme in Book Studio, then reopen Proofing Center.")
            return
        try: seed = int(self.parent.seed.get())
        except ValueError: seed = 7
        self.status.set("Checking the theme and locating the newest finished package…")
        threading.Thread(target=self._check, args=(self.parent.selected_theme, seed), daemon=True).start()

    def _check(self, theme: Path, seed: int) -> None:
        errors, warnings, notes = quality_gate(theme, seed)
        data = json.loads(theme.read_text(encoding="utf-8-sig"))
        package = find_latest_book_package(str(data.get("title") or theme.stem))
        package_issues: list[str] = []
        if not package:
            package_issues.append("No complete package found. Create Complete Book Package before approving proof.")
        else:
            for filename in ("interior.pdf", "front_cover.png", "kdp_full_wrap.pdf", "kdp_full_wrap_preview.png"):
                if not package_file(package, filename).exists(): package_issues.append(f"Package is missing {filename}.")
            try:
                from pypdf import PdfReader
                pages = len(PdfReader(str(package_file(package, "interior.pdf"))).pages)
                notes.append(f"Interior PDF has {pages} pages; expected about {estimated_page_count(data)} pages before optional Signature Edition extras.")
            except Exception as exc:
                package_issues.append(f"Could not inspect interior PDF: {exc}")
        self.after(0, self._proof_finished, data, package, errors, warnings + package_issues, notes, package_issues)

    def _proof_finished(self, data: dict, package: Path | None, errors: list[str], warnings: list[str], notes: list[str], package_issues: list[str]) -> None:
        self.package = package; self.blocking_issues = errors + package_issues
        title = str(data.get("title") or "Selected book")
        lines = [f"{title} — {len(data.get('puzzles', []))} puzzles."]
        score, score_label = kdp_package_score(data, package, self.blocking_issues)
        lines.append(f"KDP package score: {score}/100 — {score_label}.")
        lines.append("Theme quality: PASS." if not errors else f"Theme quality: {len(errors)} blocking issue(s).")
        lines.append("Package: READY." if package and not package_issues else "Package: needs attention.")
        if warnings: lines.append("Notes: " + " • ".join(warnings[:3]))
        if notes: lines.append("Verified: " + " • ".join(notes[:2]))
        self.summary.set("\n".join(lines))
        if package:
            self._show_image(self.cover_label, package_file(package, "front_cover.png"), "cover_image", (390, 420))
            self._show_image(self.wrap_label, package_file(package, "kdp_full_wrap_preview.png"), "wrap_image", (390, 420))
        allowed = package is not None and not self.blocking_issues
        self.approve_button.configure(state="normal" if allowed else "disabled")
        self.status.set("Proof is ready. Open both PDFs for a final visual page-by-page review, then mark it approved." if allowed else "Proof found items to resolve before approval.")

    def _open_file(self, filename: str) -> None:
        target = package_file(self.package, filename) if self.package else None
        if not target or not target.exists():
            messagebox.showinfo("File not ready", "Create a complete book package first.", parent=self); return
        os.startfile(target)

    def open_package(self) -> None:
        if self.package: os.startfile(self.package)
        else: messagebox.showinfo("No package yet", "Create a complete book package first.", parent=self)

    def mark_approved(self) -> None:
        if self.blocking_issues or not self.parent.selected_theme: return
        catalog = load_release_catalog(); record = catalog.setdefault(self.parent.selected_theme.name, {})
        record["proof_approved"] = True; record["proof_approved_at"] = datetime.now().isoformat(timespec="seconds")
        record["updated"] = record["proof_approved_at"]
        save_release_catalog(catalog)
        self.status.set("Proof approval saved in My Books Dashboard. Your files were not changed.")
        self.approve_button.configure(state="disabled")


class SeriesExpansionDialog(tk.Toplevel):
    """Create the next distinct book in a series from a fresh word bank."""
    def __init__(self, parent: "WordSearchCreator", initial_source: Path | None = None) -> None:
        super().__init__(parent); self.parent = parent; self.title("Series Expansion")
        self.geometry("780x680"); self.minsize(680, 580); self.transient(parent); self.grab_set()
        self.paths = saved_theme_files(); self.source = tk.StringVar(); self.title_value = tk.StringVar(); self.subtitle = tk.StringVar(); self.series = tk.StringVar(); self.status = tk.StringVar(value="Choose an existing book, then import a fresh word bank for its companion edition.")
        self._build()
        if initial_source and initial_source in self.paths:
            try:
                data = json.loads(initial_source.read_text(encoding="utf-8-sig"))
                self.source.set(str(data.get("title") or initial_source.stem))
                self._source_changed()
                self.status.set("Selected book loaded. Import a fresh word bank for a clearly distinct companion.")
            except (OSError, json.JSONDecodeError):
                pass

    def _build(self) -> None:
        frame = ttk.Frame(self, padding=18); frame.pack(fill="both", expand=True); frame.columnconfigure(1, weight=1); frame.rowconfigure(5, weight=1)
        ttk.Label(frame, text="SERIES EXPANSION", font=("Segoe UI", 18, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(frame, text="Build a coordinated companion book without copying the first book's puzzles. The new book keeps the series visual identity and uses your fresh word bank.", foreground="#555555", wraplength=700).grid(row=1, column=0, columnspan=2, sticky="w", pady=(3, 14))
        ttk.Label(frame, text="Source book").grid(row=2, column=0, sticky="w", pady=5)
        titles = [json.loads(path.read_text(encoding="utf-8-sig")).get("title", path.stem) for path in self.paths]
        picker = ttk.Combobox(frame, textvariable=self.source, values=titles, state="readonly"); picker.grid(row=2, column=1, sticky="ew", padx=(12, 0), pady=5); picker.bind("<<ComboboxSelected>>", self._source_changed)
        self._field(frame, 3, "New book title", self.title_value); self._field(frame, 4, "Subtitle", self.subtitle); self._field(frame, 5, "Series name", self.series)
        ttk.Label(frame, text="Fresh word bank").grid(row=6, column=0, sticky="nw", pady=(8, 0))
        words_frame = ttk.Frame(frame); words_frame.grid(row=6, column=1, sticky="nsew", padx=(12, 0), pady=(8, 0)); words_frame.columnconfigure(0, weight=1)
        self.words = ScrolledText(words_frame, height=10, wrap="word", font=("Segoe UI", 10)); self.words.grid(row=0, column=0, sticky="nsew")
        ttk.Button(words_frame, text="Import Word Bank File…", command=self._import).grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Label(words_frame, text="Use a TXT list or a separate JSON theme. You need at least three times the source book's words-per-puzzle for varied new puzzles.", foreground="#666666", wraplength=500).grid(row=2, column=0, sticky="w", pady=(6, 0))
        actions = ttk.Frame(frame); actions.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(16, 0)); actions.columnconfigure(0, weight=1); actions.columnconfigure(1, weight=1)
        ttk.Button(actions, text="Create Companion Book", command=self.create, style="Primary.TButton").grid(row=0, column=0, sticky="ew", padx=(0, 5)); ttk.Button(actions, text="Cancel", command=self.destroy).grid(row=0, column=1, sticky="ew", padx=(5, 0))
        ttk.Label(frame, textvariable=self.status, style="Status.TLabel", wraplength=700).grid(row=8, column=0, columnspan=2, sticky="ew", pady=(14, 0))

    @staticmethod
    def _field(frame: ttk.Frame, row: int, label: str, variable: tk.StringVar) -> None:
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=5); ttk.Entry(frame, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=(12, 0), pady=5)

    def _source_changed(self, _event: object = None) -> None:
        if not self.source.get(): return
        index = [json.loads(path.read_text(encoding="utf-8-sig")).get("title", path.stem) for path in self.paths].index(self.source.get())
        data = json.loads(self.paths[index].read_text(encoding="utf-8-sig"))
        self.series.set(str(data.get("series") or "My Word Search Collection")); self.title_value.set(""); self.subtitle.set("")

    def _import(self) -> None:
        filename = filedialog.askopenfilename(title="Choose a fresh word bank", initialdir=THEMES_DIR, filetypes=[("Word banks and themes", "*.txt *.json"), ("All files", "*.*")], parent=self)
        if not filename: return
        path = Path(filename)
        try:
            if path.suffix.lower() == ".json":
                data = json.loads(path.read_text(encoding="utf-8-sig")); raw = [str(word) for puzzle in data.get("puzzles", []) if isinstance(puzzle, dict) for word in puzzle.get("words", [])] if isinstance(data, dict) else data
                words = BookBlueprintDialog._clean_items(raw if isinstance(raw, list) else [])
            else: words = BookBlueprintDialog._clean_source(path.read_text(encoding="utf-8-sig"))
            if not words: raise ValueError("No usable words were found.")
        except (OSError, ValueError, json.JSONDecodeError) as exc: messagebox.showerror("Could not import word bank", str(exc), parent=self); return
        self.words.delete("1.0", "end"); self.words.insert("1.0", ", ".join(words)); self.status.set(f"Imported and cleaned {len(words)} unique words from {path.name}.")

    def create(self) -> None:
        if not self.source.get() or not self.title_value.get().strip(): messagebox.showwarning("Book details", "Choose a source book and add a new title.", parent=self); return
        try: source_path = self.paths[[json.loads(path.read_text(encoding="utf-8-sig")).get("title", path.stem) for path in self.paths].index(self.source.get())]; source = json.loads(source_path.read_text(encoding="utf-8-sig"))
        except (ValueError, OSError, json.JSONDecodeError): messagebox.showerror("Source book", "The source theme could not be read.", parent=self); return
        count = len(source.get("puzzles", [])); words_each = max((len(puzzle.get("words", [])) for puzzle in source.get("puzzles", []) if isinstance(puzzle, dict)), default=12)
        words = BookBlueprintDialog._clean_source(self.words.get("1.0", "end-1c")); minimum = count * words_each
        if len(words) < minimum: messagebox.showwarning("More unique words needed", f"This companion needs {minimum} unique words for {count} puzzles with no repeated words. You currently have {len(words)}.", parent=self); return
        title = self.title_value.get().strip(); topic = str(source.get("detected_topic") or source.get("title") or "Series")
        shuffled_words = words[:]; random.Random(f"{title}|no-repeat").shuffle(shuffled_words); puzzles = []
        for number in range(1, count + 1):
            start=(number-1)*words_each; puzzles.append({"name": f"{title} Puzzle {number:03d}", "words": shuffled_words[start:start+words_each]})
        data = {key: value for key, value in source.items() if key not in {"title", "subtitle", "puzzles", "detected_topic", "clipart_search_terms"}}
        data.update({"title": title, "subtitle": self.subtitle.get().strip() or f"{count} coordinated word search puzzles", "author": "Jordan M. Slade", "series": self.series.get().strip() or str(source.get("series") or "My Word Search Collection"), "detected_topic": topic, "difficulty_label": puzzle_difficulty_label({"puzzles": puzzles}), "clipart_search_terms": f"{title} illustration clipart transparent background", "no_repeat_words": True, "cover_badge": "NO REPEATED WORDS", "puzzles": puzzles})
        target = THEMES_DIR / f"{WordSearchCreator._safe_filename(title).lower()}.json"; suffix = 2
        while target.exists(): target = THEMES_DIR / f"{WordSearchCreator._safe_filename(title).lower()}_{suffix}.json"; suffix += 1
        target.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        self.parent._load_theme_list(); self.parent._set_theme(target); self.parent.status.set(f"Created series companion: {target.name}")
        messagebox.showinfo("Companion book created", "Your companion theme is now in the library and loaded into Book Studio. Run Check Book before production.", parent=self); self.destroy()


def local_niche_matches(query: str) -> list[tuple[Path, dict]]:
    terms={term for term in re.findall(r"[a-z0-9]+", query.casefold()) if len(term)>2}
    matches=[]
    for path in saved_theme_files():
        try: data=json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError,json.JSONDecodeError): continue
        haystack=" ".join(str(data.get(key) or "") for key in ("title","subtitle","detected_topic","series")).casefold()
        if terms and any(term in haystack for term in terms): matches.append((path,data))
    return matches


class NicheResearchDialog(tk.Toplevel):
    """Research helper that opens live sources while keeping the user's review in control."""
    def __init__(self,parent: "WordSearchCreator") -> None:
        super().__init__(parent); self.parent=parent; self.title("Niche Research Center"); self.geometry("820x650"); self.minsize(680,520); self.transient(parent)
        self.query=tk.StringVar(); self.summary=tk.StringVar(value="Enter a niche, then run a local library check before opening live research."); self._build()

    def _build(self) -> None:
        frame=ttk.Frame(self,padding=18); frame.pack(fill="both",expand=True); frame.columnconfigure(0,weight=1); frame.rowconfigure(4,weight=1)
        ttk.Label(frame,text="NICHE RESEARCH CENTER",font=("Segoe UI",18,"bold")).grid(row=0,column=0,sticky="w")
        ttk.Label(frame,text="Use live sources to research current interest. The local check below only compares against your own theme library—it does not claim live sales data.",foreground="#555555",wraplength=760).grid(row=1,column=0,sticky="w",pady=(3,12))
        search=ttk.Frame(frame); search.grid(row=2,column=0,sticky="ew"); search.columnconfigure(0,weight=1); ttk.Entry(search,textvariable=self.query,font=("Segoe UI",11)).grid(row=0,column=0,sticky="ew"); ttk.Button(search,text="Check My Library",command=self.check,style="Primary.TButton").grid(row=0,column=1,padx=(8,0))
        ttk.Label(frame,textvariable=self.summary,wraplength=760,justify="left",style="Status.TLabel").grid(row=3,column=0,sticky="ew",pady=(12,0))
        self.results=ScrolledText(frame,wrap="word",font=("Segoe UI",10),padx=12,pady=12); self.results.grid(row=4,column=0,sticky="nsew",pady=(12,0)); self.results.insert("1.0","Your matching existing themes will appear here."); self.results.configure(state="disabled")
        actions=ttk.Frame(frame); actions.grid(row=5,column=0,sticky="ew",pady=(14,0));
        for col in range(5): actions.columnconfigure(col,weight=1)
        ttk.Button(actions,text="Google Trends",command=lambda:self.open("trends")).grid(row=0,column=0,sticky="ew",padx=(0,4)); ttk.Button(actions,text="Amazon Competition",command=lambda:self.open("amazon")).grid(row=0,column=1,sticky="ew",padx=4); ttk.Button(actions,text="Keyword Ideas",command=lambda:self.open("keywords")).grid(row=0,column=2,sticky="ew",padx=4); ttk.Button(actions,text="Save Competitor Note",command=self.note).grid(row=0,column=3,sticky="ew",padx=4); ttk.Button(actions,text="Use in Builder",command=self.use).grid(row=0,column=4,sticky="ew",padx=(4,0))

    def check(self) -> None:
        query=self.query.get().strip()
        if not query: messagebox.showinfo("Enter a niche","Enter a niche first, such as Gardening, Fall Word Search, or Bible Puzzles.",parent=self); return
        matches=local_niche_matches(query); level="Open in your library" if not matches else ("Some overlap in your library" if len(matches)<3 else "Established in your library")
        self.summary.set(f"Local portfolio result: {level}. {len(matches)} matching active theme(s). Now open live sources to judge current trend interest and marketplace competition.")
        self.results.configure(state="normal"); self.results.delete("1.0","end")
        if matches:
            self.results.insert("1.0","RELATED THEMES YOU ALREADY HAVE\n\n"+"\n".join(f"• {data.get('title',path.stem)} — {data.get('detected_topic','General Interest')}" for path,data in matches))
        else: self.results.insert("1.0","No active theme titles or detected topics overlap with this niche. That is useful for avoiding duplication, but it is not a live market-demand score.")
        self.results.configure(state="disabled")

    def open(self, source: str) -> None:
        query=self.query.get().strip()
        if not query: messagebox.showinfo("Enter a niche","Enter a niche first.",parent=self); return
        encoded=quote_plus(query+" word search")
        urls={"trends":f"https://trends.google.com/trends/explore?q={encoded}","amazon":f"https://www.amazon.com/s?k={encoded}","keywords":f"https://www.google.com/search?q={encoded}"}
        webbrowser.open(urls[source])

    def use(self) -> None:
        query=self.query.get().strip()
        if not query: messagebox.showinfo("Enter a niche","Enter a niche first.",parent=self); return
        GuidedBookBuilderDialog(self.parent, initial_topic=query); self.destroy()

    def note(self) -> None:
        niche=self.query.get().strip()
        if not niche: messagebox.showinfo("Enter a niche","Enter a niche first.",parent=self); return
        note=simpledialog.askstring("Competitor Note","Save what you observed: price, cover pattern, subtitle wording, gaps, or page count.",parent=self)
        if note and note.strip(): save_competitor_note(niche,note.strip()); self.summary.set("Competitor note saved locally for future research.")


class PublicationPipelineDialog(tk.Toplevel):
    def __init__(self,parent: "WordSearchCreator") -> None:
        super().__init__(parent); self.parent=parent; self.title("Publication Pipeline"); self.geometry("1020x650"); self.transient(parent); self.catalog=load_release_catalog(); self._build()
    def _build(self) -> None:
        frame=ttk.Frame(self,padding=18); frame.pack(fill="both",expand=True); ttk.Label(frame,text="PUBLICATION PIPELINE",font=("Segoe UI",18,"bold")).pack(anchor="w"); ttk.Label(frame,text="Idea → Research → Theme Ready → Package Created → KDP Uploaded → Published",foreground="#555555").pack(anchor="w",pady=(2,12))
        tree=ttk.Treeview(frame,columns=("stage","title","package"),show="headings"); tree.heading("stage",text="STAGE"); tree.heading("title",text="BOOK"); tree.heading("package",text="PACKAGE"); tree.column("stage",width=170); tree.column("title",width=430); tree.column("package",width=300); tree.pack(fill="both",expand=True)
        for path in saved_theme_files():
            try:data=json.loads(path.read_text(encoding="utf-8-sig"))
            except (OSError,json.JSONDecodeError):continue
            record=self.catalog.get(path.name,{}); package=find_latest_book_package(str(data.get("title") or path.stem)); stage=str(record.get("stage") or ("Package Created" if package else "Theme Ready")); tree.insert("","end",values=(stage,data.get("title",path.stem),"Yes" if package else "Not yet"))


class SeasonalCalendarDialog(tk.Toplevel):
    def __init__(self,parent: "WordSearchCreator") -> None:
        super().__init__(parent); self.title("Seasonal Publishing Calendar"); self.geometry("720x500"); self.transient(parent); text=ScrolledText(self,wrap="word",font=("Segoe UI",10),padx=16,pady=16); text.pack(fill="both",expand=True); text.insert("1.0","SEASONAL PUBLISHING CALENDAR\n\nChristmas / Winter: begin research and creation July–September; publish before October.\nHalloween / Fall: begin May–July; publish before August.\nThanksgiving: begin June–August; publish before September.\nSpring / Gardening: begin November–January; publish before February.\nSummer / Travel: begin January–March; publish before April.\nBack to School: begin April–May; publish before July.\n\nThese are planning lead times, not guarantees of demand. Use Niche Research Center to confirm current interest before creating a series."); text.configure(state="disabled")


class TopicPackBuilderDialog(tk.Toplevel):
    def __init__(self,parent: "WordSearchCreator") -> None:
        super().__init__(parent); self.title("Topic Pack Builder"); self.geometry("620x540"); self.transient(parent); self.master_library=load_master_word_bank(); self.name=tk.StringVar(); self.pack_choice_map=self._grouped_pack_choices(); self._build()

    def _grouped_pack_choices(self) -> dict[str, str]:
        packs = self.master_library.get("topic_packs", {}) if isinstance(self.master_library, dict) else {}
        families = self.master_library.get("pack_families", {}) if isinstance(self.master_library, dict) else {}
        choices: dict[str, str] = {}
        for family, names in families.items() if isinstance(families, dict) else []:
            for pack in names if isinstance(names, list) else []:
                if pack in packs: choices[f"{family}  —  {pack}"] = pack
        for pack in packs: choices.setdefault(str(pack), str(pack))
        return choices
    def _build(self) -> None:
        frame=ttk.Frame(self,padding=18); frame.pack(fill="both",expand=True); frame.columnconfigure(0,weight=1); frame.rowconfigure(3,weight=1); ttk.Label(frame,text="TOPIC PACK BUILDER",font=("Segoe UI",18,"bold")).grid(row=0,column=0,sticky="w"); ttk.Label(frame,text="Combine several existing topic packs into one focused reusable word-bank file.",foreground="#555555").grid(row=1,column=0,sticky="w",pady=(2,10)); ttk.Entry(frame,textvariable=self.name).grid(row=2,column=0,sticky="ew"); self.list=tk.Listbox(frame,selectmode="extended",exportselection=False); self.list.grid(row=3,column=0,sticky="nsew",pady=10); self.packs=list(self.pack_choice_map); [self.list.insert("end",pack) for pack in self.packs]; ttk.Button(frame,text="Create Combined Pack",command=self.create,style="Primary.TButton").grid(row=4,column=0,sticky="e")
    def create(self) -> None:
        name=self.name.get().strip(); selected=self.list.curselection()
        if not name or not selected: messagebox.showwarning("Choose packs","Name the pack and select at least one source pack.",parent=self); return
        sources=[source for index in selected for source in self.master_library["topic_packs"][self.pack_choice_map[self.packs[index]]]]; words=BookBlueprintDialog._clean_items([word for source in sources for word in self.master_library.get("topics",{}).get(source,[])]); target=WORD_BANKS_DIR / f"{WordSearchCreator._safe_filename(name)}.json"; target.write_text(json.dumps({"name":name,"source_topics":sorted(set(sources)),"words":words},indent=2)+"\n",encoding="utf-8"); messagebox.showinfo("Topic pack created",f"Created {target.name} with {len(words)} words. Import it in Guided Book Builder.",parent=self); self.destroy()


class HelpCenterDialog(tk.Toplevel):
    def __init__(self,parent: "WordSearchCreator") -> None:
        super().__init__(parent); self.title("What Does This Do?"); self.geometry("690x570"); self.transient(parent)
        text=ScrolledText(self,wrap="word",font=("Segoe UI",10),padx=16,pady=16); text.pack(fill="both",expand=True)
        text.insert("1.0", "WHAT DOES THIS DO?\n\nFreshness\nHow much vocabulary is unique across the book. Higher variety usually means less repetition.\n\nSignature Edition\nAdds premium Passport, achievement, and collection pages to the interior.\n\nPuzzle Seed\nA number that controls the random grid layout. Change it only when you want a new placement layout.\n\nProof Score\nA readiness score based on book checks and whether the finished interior, cover, wrap, and checklist exist.\n\nSpine Safety\nShort books may be too thin for readable spine text. The app warns you before you depend on it.\n\nWord-Bank Freshness\nA check for repeated word groups. It helps you avoid books that feel too similar from puzzle to puzzle.\n\nGuided Book Builder\nUses your words to suggest a production-ready book plan. You can change every recommendation before approval.\n")
        text.configure(state="disabled")


class ErrorLogDialog(tk.Toplevel):
    def __init__(self,parent: "WordSearchCreator") -> None:
        super().__init__(parent); self.title("Error Log"); self.geometry("860x560"); self.transient(parent)
        text=ScrolledText(self,wrap="word",font=("Segoe UI",10),padx=16,pady=16); text.pack(fill="both",expand=True)
        entries=load_error_log()
        if not entries: text.insert("1.0","No saved problems. You are all clear.")
        for entry in entries:
            text.insert("end",f"{entry.get('time','')} — {entry.get('action','Action')}\nBook: {entry.get('book','')}\nWhat happened: {entry.get('what_happened','')}\nSuggested next step: {entry.get('suggestion','')}\n\n")
        text.configure(state="disabled")


class CreateNewBookDialog(tk.Toplevel):
    """The normal, low-decision start for every supported book type.

    It intentionally hands off to the established creators; it does not create
    a second package engine or skip their validation and preview stops.
    """
    TYPES = ("Word Search", "Sudoku", "Cryptogram", "Word Scramble + Trivia", "Mixed Brain Games")

    def __init__(self, parent: "WordSearchCreator") -> None:
        super().__init__(parent)
        self.parent = parent
        self.title("Create New Book")
        self.geometry("760x610")
        self.minsize(650, 500)
        self.transient(parent)
        self.grab_set()
        self.kind = tk.StringVar(value="Word Search")
        self.topic = tk.StringVar()
        self.edition = tk.StringVar(value="Standard")
        self.difficulty = tk.StringVar(value="Automatic")
        self.show_advanced = tk.BooleanVar(value=False)
        self.recommendations: dict[str, str] = {}
        self._build()
        self._load_recommendations()

    def _build(self) -> None:
        root = ttk.Frame(self, padding=22)
        root.pack(fill="both", expand=True)
        root.columnconfigure(1, weight=1)
        ttk.Label(root, text="Create New Book", font=("Segoe UI", 20, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(root, text="Three simple steps. The studio chooses the checked defaults; the detailed tools remain available whenever you want them.", wraplength=680, foreground="#777777").grid(row=1, column=0, columnspan=2, sticky="w", pady=(3, 20))
        ttk.Label(root, text="1  Choose book type").grid(row=2, column=0, sticky="w", pady=7)
        ttk.Combobox(root, textvariable=self.kind, values=self.TYPES, state="readonly").grid(row=2, column=1, sticky="ew", pady=7)
        ttk.Label(root, text="2  Choose a topic").grid(row=3, column=0, sticky="w", pady=7)
        topic_row = ttk.Frame(root); topic_row.grid(row=3, column=1, sticky="ew", pady=7); topic_row.columnconfigure(0, weight=1)
        ttk.Entry(topic_row, textvariable=self.topic).grid(row=0, column=0, sticky="ew")
        self.recommended = ttk.Combobox(topic_row, state="readonly", width=24)
        self.recommended.grid(row=0, column=1, padx=(8, 0))
        self.recommended.bind("<<ComboboxSelected>>", self._choose_recommendation)
        ttk.Label(root, text="3  Confirm the simple plan").grid(row=4, column=0, sticky="nw", pady=(12, 7))
        self.plan = tk.StringVar(value="Standard edition • automatic difficulty • matching cover direction • final review before files are marked ready")
        ttk.Label(root, textvariable=self.plan, wraplength=500, justify="left").grid(row=4, column=1, sticky="w", pady=(12, 7))
        ttk.Checkbutton(root, text="Show advanced choices", variable=self.show_advanced, command=self._toggle_advanced).grid(row=5, column=0, columnspan=2, sticky="w", pady=(12, 4))
        self.advanced = ttk.Labelframe(root, text="Advanced choices — optional", padding=12)
        self.advanced.columnconfigure(1, weight=1)
        ttk.Label(self.advanced, text="Edition").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Combobox(self.advanced, textvariable=self.edition, values=("Standard", "Signature Edition"), state="readonly").grid(row=0, column=1, sticky="ew", padx=(10, 0), pady=4)
        ttk.Label(self.advanced, text="Difficulty").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Combobox(self.advanced, textvariable=self.difficulty, values=("Automatic", "Easy", "Standard", "Challenging", "Mixed"), state="readonly").grid(row=1, column=1, sticky="ew", padx=(10, 0), pady=4)
        self.status = tk.StringVar(value="Loading saved topic recommendations…")
        ttk.Label(root, textvariable=self.status, wraplength=680, foreground="#777777").grid(row=7, column=0, columnspan=2, sticky="w", pady=(12, 6))
        actions = ttk.Frame(root); actions.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(12, 0)); actions.columnconfigure(0, weight=1)
        ttk.Button(actions, text="Create Best Version", command=self.continue_to_creator, style="Primary.TButton").grid(row=0, column=0, sticky="ew")
        ttk.Button(actions, text="Cancel", command=self.destroy).grid(row=0, column=1, padx=(8, 0))

    def _toggle_advanced(self) -> None:
        if self.show_advanced.get():
            self.advanced.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(2, 4))
        else:
            self.advanced.grid_remove()

    def _load_recommendations(self) -> None:
        try:
            from publishing import PublishingService
            choices = PublishingService(APP_DIR).recommended_books(limit=5)
        except Exception:
            choices = []
        for choice in choices:
            topic = str(choice.get("topic") or "").strip()
            if not topic:
                continue
            label = f"Recommended: {topic}"
            self.recommendations[label] = topic
        self.recommended.configure(values=tuple(self.recommendations))
        self.status.set("Pick a recommended topic or type your own. The plan always opens the existing creator and its quality checks.")

    def _choose_recommendation(self, _event: object = None) -> None:
        self.topic.set(self.recommendations.get(self.recommended.get(), self.topic.get()))

    def continue_to_creator(self) -> None:
        topic = self.topic.get().strip()
        kind = self.kind.get()
        if not topic:
            messagebox.showwarning("Choose a topic", "Type a topic or choose one of the recommendations first.", parent=self)
            return
        edition = self.edition.get()
        self.destroy()
        if kind == "Word Search":
            GuidedBookBuilderDialog(self.parent, initial_topic=topic, initial_pack=topic, initial_count=(100 if edition == "Signature Edition" else 48))
            self.parent.status.set(f"Opened the Word Search plan for {topic}. The normal quality check remains in place before package creation.")
        else:
            self.parent._open_other_puzzle_studio(kind, topic, edition)


def resolve_topic_pack_choice(requested: str, choices: dict[str, str]) -> str:
    """Resolve plain-English wizard topics to the closest saved topic pack."""
    wanted={token for token in re.findall(r"[a-z0-9]+",str(requested).casefold()) if token not in {"and","the","for","of"}}
    exact=next((label for label,pack in choices.items() if str(pack).casefold()==str(requested).casefold()),"")
    if exact or not wanted:
        return exact
    ranked=[]
    for label,pack in choices.items():
        tokens={token for token in re.findall(r"[a-z0-9]+",str(pack).casefold()) if token not in {"and","the","for","of"}}
        overlap=len(wanted & tokens)
        score=overlap/max(len(wanted),1)
        if overlap:
            ranked.append((score,overlap,-abs(len(tokens)-len(wanted)),label))
    ranked.sort(reverse=True)
    return ranked[0][3] if ranked and ranked[0][0] >= .5 else ""


def recommended_builder_count(capacity: int, requested_count: int | None = None) -> int:
    """Honor a wizard edition choice when the selected content can support it."""
    if requested_count and capacity >= requested_count:
        return requested_count
    if capacity >= 100:
        return 100
    if capacity >= 60:
        return 60
    if capacity >= 48:
        return 48
    return max(1, capacity)


class GuidedBookBuilderDialog(tk.Toplevel):
    """Single-screen production path from a clean word bank to an approved package."""
    def __init__(self, parent: "WordSearchCreator", initial_topic: str = "", initial_pack: str = "", initial_count: int | None = None) -> None:
        super().__init__(parent); self.parent=parent; self.title("Guided Book Builder"); self.geometry("940x790"); self.minsize(780,680); self.transient(parent); self.grab_set()
        self.topic=tk.StringVar(value=initial_topic); self.title_value=tk.StringVar(); self.subtitle=tk.StringVar(); self.audience=tk.StringVar(value="Adults & Teens"); self.buyer_angle=tk.StringVar(value="Relaxation"); self.words_each=tk.StringVar(value="12"); self.requested_count=initial_count; self.count=tk.StringVar(value=str(initial_count or 48)); self.mood=tk.StringVar(value="Calm and natural"); self.topic_pack=tk.StringVar(); self.master_library=load_master_word_bank(); self.pack_choice_map=self._grouped_pack_choices(); self.explanation=tk.StringVar(value="Add a topic and word bank to see recommendations."); self.review=tk.StringVar(value="Create the plan to unlock the final review and approval step."); self.status=tk.StringVar(value="Step 1: import a word bank or paste words."); self.created_path: Path|None=None; self._build()
        if initial_pack:
            choice = resolve_topic_pack_choice(initial_pack, self.pack_choice_map)
            if choice:
                self.topic_pack.set(choice)
                self._load_topic_pack(automatic=True)
            else:
                self.status.set(f"No reviewed topic pack could be matched confidently to {initial_pack}. Choose a focused pack before creating this book.")

    def _grouped_pack_choices(self) -> dict[str, str]:
        packs = self.master_library.get("topic_packs", {}) if isinstance(self.master_library, dict) else {}
        families = self.master_library.get("pack_families", {}) if isinstance(self.master_library, dict) else {}
        choices: dict[str, str] = {}
        if isinstance(families, dict):
            for family, pack_names in sorted(families.items(), key=lambda item: str(item[0]).casefold()):
                for pack in pack_names if isinstance(pack_names, list) else []:
                    if pack in packs:
                        choices[f"{family}  —  {pack}"] = pack
        for pack in packs:
            choices.setdefault(str(pack), str(pack))
        return choices

    def _build(self) -> None:
        frame=scrollable_dialog_page(self,padding=18); frame.columnconfigure(1,weight=1); frame.rowconfigure(7,weight=1)
        ttk.Label(frame,text="GUIDED BOOK BUILDER",font=("Segoe UI",19,"bold")).grid(row=0,column=0,columnspan=2,sticky="w")
        ttk.Label(frame,text="Start with a focused topic, then the app fills in clean words and recommends a book plan. You can still change every detail.",foreground="#555555",wraplength=850).grid(row=1,column=0,columnspan=2,sticky="w",pady=(2,12))
        starter=ttk.Labelframe(frame,text="1 — START WITH A FOCUSED TOPIC",padding=10); starter.grid(row=2,column=0,columnspan=2,sticky="ew",pady=(0,10)); starter.columnconfigure(1,weight=1)
        ttk.Label(starter,text="Topic pack").grid(row=0,column=0,sticky="w")
        pack_picker=ttk.Combobox(starter,textvariable=self.topic_pack,values=tuple(self.pack_choice_map),state="readonly")
        pack_picker.grid(row=0,column=1,sticky="ew",padx=8); pack_picker.bind("<<ComboboxSelected>>", lambda _event: self._load_topic_pack(automatic=True))
        add_hover_help(pack_picker,"Choose a focused pack. The app loads only the clean related words and fills in recommended book and cover settings.")
        ttk.Button(starter,text="Use This Topic",command=self._load_topic_pack,style="Primary.TButton").grid(row=0,column=2,sticky="e")
        ttk.Label(starter,text="Pick a pack first for the simplest path. Import or use the full library only when you are building something new.",foreground="#666666",wraplength=760).grid(row=1,column=0,columnspan=3,sticky="w",pady=(7,0))
        for row,label,var in ((3,"Topic or niche",self.topic),(4,"Book title (optional)",self.title_value),(5,"Subtitle (optional)",self.subtitle)):
            ttk.Label(frame,text=label).grid(row=row,column=0,sticky="w",pady=5); ttk.Entry(frame,textvariable=var).grid(row=row,column=1,sticky="ew",padx=(12,0),pady=5)
        ttk.Label(frame,text="Audience and puzzle size").grid(row=6,column=0,sticky="w",pady=5)
        settings=ttk.Frame(frame); settings.grid(row=6,column=1,sticky="w",padx=(12,0)); ttk.Combobox(settings,textvariable=self.audience,values=("Adults","Teens","Adults & Teens"),state="readonly",width=14).pack(side="left"); ttk.Combobox(settings,textvariable=self.buyer_angle,values=("Relaxation","Large Print","Gift","Brain Exercise","Senior-Friendly","Teen Fun"),state="readonly",width=16).pack(side="left",padx=6); ttk.Combobox(settings,textvariable=self.words_each,values=("12","20"),state="readonly",width=5).pack(side="left"); ttk.Label(settings,text="words per puzzle").pack(side="left",padx=(4,0))
        ttk.Label(frame,text="Words for this book").grid(row=7,column=0,sticky="nw",pady=(10,5))
        box=ttk.Frame(frame); box.grid(row=7,column=1,sticky="nsew",padx=(12,0)); box.columnconfigure(0,weight=1)
        self.words=ScrolledText(box,height=10,wrap="word"); self.words.grid(row=0,column=0,sticky="nsew"); self.words.bind("<KeyRelease>",lambda _e:self.recommend())
        word_actions=ttk.Frame(box); word_actions.grid(row=1,column=0,sticky="ew",pady=(7,0)); word_actions.columnconfigure(1,weight=1)
        ttk.Button(word_actions,text="Import a Word Bank…",command=self._import,style="Action.TButton").grid(row=0,column=0,sticky="w")
        ttk.Button(word_actions,text="Use Entire Master Library",command=self._load_master,style="Action.TButton").grid(row=0,column=1,sticky="e")
        ttk.Button(box,text="Check 2-Book No-Repeat Capacity",command=self._check_no_repeat_capacity,style="Action.TButton").grid(row=2,column=0,sticky="w",pady=(6,0))
        card=ttk.Labelframe(frame,text="2 — AUTOMATIC RECOMMENDATION",padding=10); card.grid(row=8,column=0,columnspan=2,sticky="ew",pady=(12,0)); ttk.Label(card,textvariable=self.explanation,wraplength=840,justify="left").pack(anchor="w")
        review=ttk.Labelframe(frame,text="3 — FINAL REVIEW BEFORE APPROVAL",padding=10); review.grid(row=9,column=0,columnspan=2,sticky="ew",pady=(10,0)); ttk.Label(review,textvariable=self.review,wraplength=840,justify="left").pack(anchor="w")
        actions=ttk.Frame(frame); actions.grid(row=10,column=0,columnspan=2,sticky="ew",pady=(15,0)); actions.columnconfigure(0,weight=1); actions.columnconfigure(1,weight=1); actions.columnconfigure(2,weight=1)
        ttk.Button(actions,text="Get Title Ideas",command=self._title_ideas).grid(row=0,column=0,sticky="ew",padx=(0,5)); ttk.Button(actions,text="Create Book Plan",command=self.create,style="Action.TButton").grid(row=0,column=1,sticky="ew",padx=5); self.approve=ttk.Button(actions,text="Approve This Plan & Create",command=self.approve_package,state="disabled",style="Primary.TButton"); self.approve.grid(row=0,column=2,sticky="ew",padx=(5,0))
        ttk.Label(frame,textvariable=self.status,style="Status.TLabel",wraplength=840).grid(row=11,column=0,columnspan=2,sticky="ew",pady=(12,0))

    def _import(self) -> None:
        filename=filedialog.askopenfilename(title="Choose word bank",initialdir=THEMES_DIR,filetypes=[("Word banks and themes","*.txt *.json"),("All files","*.*")],parent=self)
        if not filename:return
        path=Path(filename)
        try:
            if path.suffix.lower()==".json":
                data=json.loads(path.read_text(encoding="utf-8-sig")); raw=(data.get("words") or [str(w) for p in data.get("puzzles",[]) if isinstance(p,dict) for w in p.get("words",[])]) if isinstance(data,dict) else data; words=BookBlueprintDialog._clean_items(raw if isinstance(raw,list) else [])
            else: words=BookBlueprintDialog._clean_source(path.read_text(encoding="utf-8-sig"))
        except (OSError,json.JSONDecodeError) as exc: messagebox.showerror("Could not import",str(exc),parent=self); return
        self.words.delete("1.0","end"); self.words.insert("1.0",", ".join(words)); self.recommend()

    def _load_master(self) -> None:
        if not self.master_library: messagebox.showinfo("Master library", "The master word bank has not been built yet.", parent=self); return
        words=BookBlueprintDialog._clean_items(self.master_library.get("words",[])); self.words.delete("1.0","end"); self.words.insert("1.0",", ".join(words)); self.status.set(f"Loaded {len(words)} words from the master library. Narrow the topic/title so the final book stays focused."); self.recommend()

    def _load_topic_pack(self, automatic: bool = False) -> None:
        selected=self.topic_pack.get(); pack=self.pack_choice_map.get(selected, selected); sources=self.master_library.get("topic_packs",{}).get(pack,[]); topics=self.master_library.get("topics",{}); words=BookBlueprintDialog._clean_items([word for source in sources for word in topics.get(source,[])])
        if not words: messagebox.showinfo("Choose a topic pack", "Choose one of the focused topic packs first.", parent=self); return
        self.words.delete("1.0","end"); self.words.insert("1.0",", ".join(words)); self.topic.set(pack)
        if not self.title_value.get().strip(): self.title_value.set(f"{pack} Word Search")
        if not self.subtitle.get().strip(): self.subtitle.set(f"No-repeat themed word search puzzles for {self.audience.get().lower()}")
        self.recommend()
        self.status.set(f"Applied {pack}: {len(words)} focused words plus automatic book and cover recommendations." if automatic else f"Applied {pack}: words and recommended book settings are ready. You can still change anything.")

    def _check_no_repeat_capacity(self) -> None:
        """Explain book capacity in simple publishing terms before a plan is made."""
        words=BookBlueprintDialog._clean_source(self.words.get("1.0","end-1c"))
        if not words and self.topic_pack.get():
            selected=self.topic_pack.get(); pack=self.pack_choice_map.get(selected, selected); sources=self.master_library.get("topic_packs",{}).get(pack,[]); topics=self.master_library.get("topics",{}); words=BookBlueprintDialog._clean_items([word for source in sources for word in topics.get(source,[])])
        if not words:
            messagebox.showinfo("No-repeat book check", "Load a focused pack, import a word bank, or paste words first.", parent=self); return
        per=int(self.words_each.get()); unique=len(set(words)); selected_count=max(1, int(self.count.get() or "48"))
        selected = content_capacity(unique, selected_count, per, target_books=2)
        standard = content_capacity(unique, 48, per, target_books=2)
        signature = content_capacity(unique, 100, per, target_books=2)
        messagebox.showinfo("No-repeat book capacity", f"This word bank has {unique} clean, unique words.\n\nYOUR CURRENT PLAN ({selected_count} puzzles × {per} words)\n{selected['message']}\n\n48-PUZZLE EDITION\n{standard['message']}\n\n100-PUZZLE SIGNATURE EDITION\n{signature['message']}\n\nThis is an honest capacity check for books with no repeated word anywhere.", parent=self)

    def recommend(self) -> None:
        words=BookBlueprintDialog._clean_source(self.words.get("1.0","end-1c")); per=int(self.words_each.get()); capacity=len(words)//per; suggested=str(recommended_builder_count(capacity, self.requested_count)); self.count.set(suggested)
        guarantee=content_capacity(len(words), int(suggested), per, target_books=2)
        recommendation=recommend_theme_from_words([{"words":words}], self.topic.get().strip()); title=self.title_value.get().strip() or (f"{self.topic.get().strip()} Word Search" if self.topic.get().strip() else "Your Word Search")
        self.explanation.set(f"Why: {len(words)} clean words supports {suggested} puzzles with {per} words each. {guarantee['message']} Detected topic: {recommendation['topic']}. Suggested cover: {recommendation['palette'].replace('-', ' ').title()} / {recommendation['style']}. Draft title: {title}.")

    def _title_ideas(self) -> None:
        options=title_options(self.topic.get(),int(self.count.get()),self.audience.get())
        choice=simpledialog.askstring("Title Ideas","Choose a title number, or cancel:\n\n"+"\n".join(f"{i+1}. {title}" for i,(title,_sub) in enumerate(options)),parent=self)
        if choice and choice.strip().isdigit() and 1<=int(choice.strip())<=len(options):
            title,subtitle=options[int(choice.strip())-1]; self.title_value.set(title); self.subtitle.set(subtitle); self.recommend()

    def create(self) -> None:
        topic=self.topic.get().strip(); words=BookBlueprintDialog._clean_source(self.words.get("1.0","end-1c")); per=int(self.words_each.get()); count=int(self.count.get())
        required=count*per
        if not topic or len(words)<required: messagebox.showwarning("More unique words needed",f"Add a topic and at least {required} clean, unique words for {count} puzzles with no repeated words. You currently have {len(words)}.",parent=self); return
        rec=recommend_theme_from_words([{"words":words}], topic); title=self.title_value.get().strip() or f"{topic} Word Search"; groups=[]; shuffled_words=words[:]; random.Random(f"{title}|no-repeat").shuffle(shuffled_words)
        for number in range(1,count+1):
            start=(number-1)*per; groups.append({"name":f"{topic} Puzzle {number:03d}","words":shuffled_words[start:start+per]})
        data={"title":title,"subtitle":self.subtitle.get().strip() or f"{count} themed word search puzzles for {self.audience.get().lower()}","author":"Jordan M. Slade","audience":self.audience.get(),"buyer_angle":self.buyer_angle.get(),"palette":rec["palette"],"cover_style":rec["style"],"detected_topic":topic,"recommended_palette":rec["palette"],"recommended_cover_style":rec["style"],"difficulty_label":puzzle_difficulty_label({"puzzles":groups}),"clipart_search_terms":f"{topic} illustration clipart transparent background","no_repeat_words":True,"cover_badge":"NO REPEATED WORDS","puzzles":groups}
        path=THEMES_DIR/f"{WordSearchCreator._safe_filename(title).lower()}.json"; suffix=2
        while path.exists(): path=THEMES_DIR/f"{WordSearchCreator._safe_filename(title).lower()}_{suffix}.json"; suffix+=1
        path.write_text(json.dumps(data,indent=2,ensure_ascii=False)+"\n",encoding="utf-8"); self.created_path=path; self.parent._load_theme_list(); self.parent._set_theme(path); self.approve.configure(state="normal")
        pages=estimated_page_count(data); price,_=recommended_us_paperback_price(pages)
        balance=" ".join(word_bank_balance_notes(words))
        source_label = self.pack_choice_map.get(self.topic_pack.get(), self.topic_pack.get()) or "Your cleaned word list"
        from publishing.production_intelligence import title_assessment
        known_titles=[]
        for candidate in saved_theme_files():
            if candidate == path: continue
            try: known_titles.append(str(json.loads(candidate.read_text(encoding="utf-8-sig")).get("title") or ""))
            except (OSError, json.JSONDecodeError): continue
        title_check=title_assessment(data["title"], data["subtitle"], topic, known_titles)
        guarantee=content_capacity(len(words), count, per, target_books=2)
        plan=production_plan_summary(title=data['title'], subtitle=data['subtitle'], difficulty=data['difficulty_label'], puzzle_count=count, words_per_puzzle=per, pages=pages, price=price, palette=rec['palette'], layout=rec['style'], folder=str(path.relative_to(APP_DIR)), capacity=guarantee)
        self.review.set(plan + f"\n\nTITLE QUALITY\n{title_check['score']}/100 — {title_check['label']}\n" + "\n".join(f"• {item}" for item in title_check["notes"]) + f"\n\nWORD SOURCE\n{source_label} — {len(words)} cleaned unique words\n\nCHECK\n{balance}\n\nApprove only if this is the book you want to make. The final visual review checks puzzle placement, cover safety, and listing files before anything is marked ready.")
        self.status.set("Plan created and loaded. Review this summary, then approve when ready.")

    def approve_package(self) -> None:
        if not self.created_path:return
        if not messagebox.askyesno("Approve complete package","This will create the approved interior, cover, KDP wrap, listing copy, and checklist. Your exact settings will be saved in Production History. Continue?",parent=self):return
        self.parent._generate_studio_package(); self.status.set("Package creation started. The Book Studio status bar will show progress.")


class SeriesBuilderDialog(tk.Toplevel):
    """Set a coordinated visual identity, then hand the series to production."""
    PALETTES = ("holly-jolly", "spooky-night", "autumn-harvest", "coastal-blue", "royal-plum", "forest-cabin", "midnight-gold", "tropical-pop", "scholarly-blue", "notebook-mint", "library-burgundy", "starlight-indigo", "citrus-study", "graphite-copper", "pixel-neon", "cinema-red")
    STYLES = ("Gallery Frame", "Color Block", "Halo Spotlight", "Ticket Stub", "Diagonal Stripe", "Retro Pop")
    def __init__(self, parent):
        super().__init__(parent); self.parent=parent; self.title("Series Factory"); self.geometry("760x650"); self.minsize(680, 560); self.transient(parent); self.grab_set()
        self.name=tk.StringVar(value="My Word Search Collection"); self.palette=tk.StringVar(value=self.PALETTES[0]); self.style=tk.StringVar(value=self.STYLES[0]); self.organize=tk.BooleanVar(value=False); self.lock_visuals=tk.BooleanVar(value=True); self.paths=saved_theme_files(); self.row_paths={}; self._build()
    def _build(self):
        frame=ttk.Frame(self,padding=18); frame.pack(fill="both",expand=True); frame.columnconfigure(1,weight=1); frame.rowconfigure(3,weight=1)
        ttk.Label(frame,text="SERIES FACTORY",font=("Segoe UI",17,"bold")).grid(row=0,column=0,columnspan=2,sticky="w")
        ttk.Label(frame,text="Select related books once. The factory saves a coordinated cover look for each one, then can send the whole series directly to Production Queue.",wraplength=590,foreground="#555555").grid(row=1,column=0,columnspan=2,sticky="w",pady=(3,12))
        ttk.Label(frame,text="Series name").grid(row=2,column=0,sticky="w"); ttk.Entry(frame,textvariable=self.name).grid(row=2,column=1,sticky="ew",padx=(10,0))
        self.tree=ttk.Treeview(frame,columns=("book",),show="tree headings",selectmode="extended",height=14); self.tree.heading("#0",text="SERIES / GROUP"); self.tree.heading("book",text="BOOK"); self.tree.column("#0",width=270); self.tree.column("book",width=350); self.tree.grid(row=3,column=0,columnspan=2,sticky="nsew",pady=12)
        groups={}
        for path in self.paths:
            try: data=json.loads(path.read_text(encoding="utf-8-sig")); group=str(data.get("series") or path.parent.relative_to(THEMES_DIR) if path.parent != THEMES_DIR else "Unfiled Themes"); title=str(data.get("title") or path.stem)
            except (OSError,json.JSONDecodeError): continue
            parent_id=groups.setdefault(group, self.tree.insert("", "end", text=group, values=(f"{group} collection",), open=True))
            iid=self.tree.insert(parent_id,"end",text="",values=(title,)); self.row_paths[iid]=path
        ttk.Label(frame,text="Starting palette").grid(row=4,column=0,sticky="w"); ttk.Combobox(frame,textvariable=self.palette,values=self.PALETTES,state="readonly").grid(row=4,column=1,sticky="ew",padx=(10,0))
        ttk.Label(frame,text="Starting layout").grid(row=5,column=0,sticky="w",pady=(8,0)); ttk.Combobox(frame,textvariable=self.style,values=self.STYLES,state="readonly").grid(row=5,column=1,sticky="ew",padx=(10,0),pady=(8,0))
        ttk.Checkbutton(frame,text="Organize selected books into Themes\\Series\\[series name]",variable=self.organize).grid(row=6,column=0,columnspan=2,sticky="w",pady=(8,0))
        ttk.Checkbutton(frame,text="Lock the same colors and layout across this series",variable=self.lock_visuals).grid(row=7,column=0,columnspan=2,sticky="w",pady=(4,0))
        note=ttk.Labelframe(frame,text="HOW IT WORKS",padding=10)
        ttk.Label(note,text="Lock on: every book uses the exact same colors and layout. Lock off: the factory rotates coordinated colors and layouts for more variety.",wraplength=560,foreground="#555555").pack(anchor="w")
        note.grid(row=8,column=0,columnspan=2,sticky="ew",pady=(4,0))
        actions=ttk.Frame(frame); actions.grid(row=9,column=0,columnspan=2,sticky="ew",pady=(16,0)); actions.columnconfigure(0,weight=1); actions.columnconfigure(1,weight=1)
        ttk.Button(actions,text="Save Series Look",command=lambda:self.save(False),style="Action.TButton").grid(row=0,column=0,sticky="ew",padx=(0,5))
        ttk.Button(actions,text="Save + Open Production Queue",command=lambda:self.save(True),style="Primary.TButton").grid(row=0,column=1,sticky="ew",padx=(5,0))
    def save(self, open_queue: bool = False):
        selected=[item for item in self.tree.selection() if item in self.row_paths]
        if len(selected)<2: messagebox.showwarning("Select books","Select at least two book rows (not a group heading) for a series.",parent=self); return
        series_name=self.name.get().strip()
        if not series_name:
            messagebox.showwarning("Series name","Give your collection a series name first.",parent=self); return
        palette_start=self.PALETTES.index(self.palette.get()); style_start=self.STYLES.index(self.style.get()); members=[]; selected_paths=[]
        folder=THEMES_DIR / "Series" / WordSearchCreator._safe_filename(series_name)
        if self.organize.get(): folder.mkdir(parents=True,exist_ok=True)
        automatic_theme_backup("applying coordinated Series Manager settings")
        for offset,item in enumerate(selected):
            path=self.row_paths[item]; data=json.loads(path.read_text(encoding="utf-8-sig")); index=0 if self.lock_visuals.get() else offset; data["series"]=series_name; data["palette"]=self.PALETTES[(palette_start+index)%len(self.PALETTES)]; data["cover_style"]=PublishReadyDialog.STYLE_MAP[self.STYLES[(style_start+index)%len(self.STYLES)]]; data["series_design"]={**(data.get("series_design") if isinstance(data.get("series_design"),dict) else {}),"family":series_name,"layout":data["cover_style"],"visual_lock":self.lock_visuals.get()}; data["series_template"]={"palette":data["palette"],"cover_style":data["cover_style"],"difficulty":puzzle_difficulty_label(data),"puzzle_count":len(data.get("puzzles",[])),"words_per_puzzle":max((len(p.get("words",[])) for p in data.get("puzzles",[]) if isinstance(p,dict)),default=0),"bonus_pages":"Use the current book's recommended bonus pages","pricing":"Use the automatic marketplace price recommendation"}; path.write_text(json.dumps(data,indent=2)+"\n",encoding="utf-8")
            if self.organize.get() and path.parent != folder:
                target=folder / path.name
                if target.exists(): target=folder / f"{path.stem}_{datetime.now():%H%M%S}{path.suffix}"
                shutil.move(str(path),str(target)); path=target
            members.append(data["title"]); selected_paths.append(path)
        save_niche_cover_memory(series_name,{"palette":self.palette.get(),"style":PublishReadyDialog.STYLE_MAP[self.style.get()]})
        individual_prices=[]
        for path in selected_paths:
            try:
                member_data=json.loads(path.read_text(encoding="utf-8-sig")); member_pages=estimated_page_count(member_data); member_price,_=recommended_us_paperback_price(member_pages,is_signature_edition(member_data)); individual_prices.append(member_price)
            except (OSError,json.JSONDecodeError): continue
        discount=0.15 if len(members)==2 else 0.20 if len(members)<=4 else 0.25
        series_digital=max(2.99,float(int(max(0,sum(max(4.99, price-3.00) for price in individual_prices)*(1-discount))))+.99)
        (folder if self.organize.get() else THEMES_DIR).joinpath(f"{WordSearchCreator._safe_filename(series_name).lower()}_series.json").write_text(json.dumps({"series":series_name,"author":"Jordan M. Slade","members":members,"palette":self.palette.get(),"cover_style":PublishReadyDialog.STYLE_MAP[self.style.get()],"visual_lock":self.lock_visuals.get(),"series_template":{"palette":self.palette.get(),"cover_style":PublishReadyDialog.STYLE_MAP[self.style.get()],"difficulty":"Keep each member's recommended difficulty","puzzle_count":"Keep each member's planned puzzle count","bonus_pages":"Use matching themed bonus pages","pricing":"Use automatic marketplace price recommendations"},"recommended_pricing":{"individual_paperback_range":f"${min(individual_prices or [0]):.2f}–${max(individual_prices or [0]):.2f}","digital_bundle":series_digital,"bundle_savings_percent":round(discount*100),"note":"Starting-price guidance only. Confirm each marketplace's current costs and rules before publishing."},"created":datetime.now().isoformat(timespec="seconds")},indent=2)+"\n",encoding="utf-8")
        self.parent._load_theme_list()
        if open_queue:
            self.destroy(); ProductionQueueDialog(self.parent, initial_paths=selected_paths); return
        messagebox.showinfo("Series saved",f"Saved a coordinated look for {len(members)} books.\n\nUse Series Factory again and choose Save + Open Production Queue when you are ready to make the packages.",parent=self); self.destroy()


class ProductionHistoryDialog(tk.Toplevel):
    """A calm, audit-friendly record of completed local packages."""
    def __init__(self, parent: "WordSearchCreator") -> None:
        super().__init__(parent); self.parent=parent; self.title("Production History"); self.geometry("1060x590"); self.minsize(780, 440); self.transient(parent)
        outer=ttk.Frame(self,padding=18); outer.pack(fill="both",expand=True); outer.rowconfigure(2,weight=1)
        ttk.Label(outer,text="PRODUCTION HISTORY",font=("Segoe UI",18,"bold")).grid(row=0,column=0,sticky="w")
        ttk.Label(outer,text="Each row is a completed version: its source file, settings, checksum, page count, approval result, and next marketplace step are saved here. Loading a version never creates files until you approve it again.",foreground="#555555",wraplength=1000).grid(row=1,column=0,sticky="w",pady=(3,12))
        self.tree=ttk.Treeview(outer,columns=("title","created","pages","approval","marketplaces"),show="headings",height=16)
        for key,label,width in (("title","Book",300),("created","Created",160),("pages","Pages",70),("approval","Local approval",260),("marketplaces","Marketplace next step",210)):
            self.tree.heading(key,text=label); self.tree.column(key,width=width,anchor="w")
        self.tree.grid(row=2,column=0,sticky="nsew"); self.rows={}
        actions=ttk.Frame(outer); actions.grid(row=3,column=0,sticky="ew",pady=(12,0)); actions.columnconfigure(0,weight=1); actions.columnconfigure(1,weight=1); actions.columnconfigure(2,weight=1)
        ttk.Button(actions,text="Refresh",command=self.refresh,style="Action.TButton").grid(row=0,column=0,sticky="ew",padx=(0,5))
        ttk.Button(actions,text="Open Package Folder",command=self.open_folder,style="Action.TButton").grid(row=0,column=1,sticky="ew",padx=5)
        ttk.Button(actions,text="Load This Version to Review",command=self.load_version,style="Primary.TButton").grid(row=0,column=2,sticky="ew",padx=(5,0))
        self.refresh()

    def refresh(self) -> None:
        self.tree.delete(*self.tree.get_children()); self.rows={}
        try: records=json.loads(PRODUCTION_HISTORY_FILE.read_text(encoding="utf-8-sig"))
        except (OSError,json.JSONDecodeError): records=[]
        for index, record in enumerate(records if isinstance(records,list) else []):
            if not isinstance(record,dict): continue
            markets=record.get("marketplaces",{}); next_step=next((f"{name}: {status}" for name,status in markets.items() if status != "Not prepared"), "Not prepared") if isinstance(markets,dict) else "Not prepared"
            iid=f"record_{index}"; self.rows[iid]=record
            self.tree.insert("","end",iid=iid,values=(record.get("title","Untitled"),record.get("created",""),record.get("pages","—"),record.get("approval","Completed package"),next_step))

    def _selected(self) -> dict[str, object] | None:
        selected=self.tree.selection(); return self.rows.get(selected[0]) if selected else None

    def open_folder(self) -> None:
        record=self._selected()
        if not record: return
        folder=Path(str(record.get("package") or ""))
        if folder.is_dir(): os.startfile(folder)
        else: messagebox.showinfo("Package not found","That older package folder is no longer on this computer. The saved source settings can still be loaded when the theme file exists.",parent=self)

    def load_version(self) -> None:
        record=self._selected()
        if not record: return
        theme=Path(str(record.get("theme_path") or ""))
        if not theme.is_file():
            messagebox.showinfo("Source not found","This version's source theme is no longer in its saved location. Restore the theme file first, then try again.",parent=self); return
        self.parent._set_theme(theme)
        settings=record.get("settings",{})
        if isinstance(settings,dict):
            for name, variable in (("title",self.parent.book_title),("subtitle",self.parent.subtitle),("author",self.parent.author)):
                if settings.get(name): variable.set(str(settings[name]))
        self.parent.status.set(f"Loaded saved version: {record.get('title','book')}. Review it and choose Create Package only when ready.")
        self.parent.lift(); self.destroy()


class ThemeDashboardDialog(tk.Toplevel):
    """A visual, scannable view of every active production theme."""
    def __init__(self, parent: "WordSearchCreator") -> None:
        super().__init__(parent); self.parent = parent; self.title("Theme Dashboard"); self.geometry("1050x720"); self.minsize(820, 560); self.transient(parent)
        self.filter = tk.StringVar(); self.ready_only = tk.BooleanVar(value=False); self._build(); self.refresh()

    def _build(self) -> None:
        outer = ttk.Frame(self, padding=18); outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="PRODUCTION DASHBOARD", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(outer, text="Themes are ranked by what is most ready to make next: complete, repeat-free, topic-matched, and supported by enough clean source words.", foreground="#555555", wraplength=960).pack(anchor="w", pady=(2, 10))
        filters = ttk.Frame(outer); filters.pack(fill="x")
        search = ttk.Entry(filters, textvariable=self.filter); search.pack(side="left", fill="x", expand=True); self.filter.trace_add("write", lambda *_: self.refresh())
        ttk.Checkbutton(filters, text="Show only ready-to-make books", variable=self.ready_only, command=self.refresh).pack(side="right", padx=(12,0))
        self.tree = ttk.Treeview(outer, columns=("title", "puzzles", "difficulty", "freshness", "topic", "next", "package", "status"), show="headings", height=20)
        for key, label, width in (("title", "Book", 270), ("puzzles", "Puzzles", 65), ("difficulty", "Difficulty", 88), ("freshness", "Freshness", 86), ("topic", "Topic Fit", 80), ("next", "Make Next", 105), ("package", "Package", 80), ("status", "Status", 150)):
            self.tree.heading(key, text=label); self.tree.column(key, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True, pady=10); self.tree.bind("<Double-1>", self._use)
        ttk.Button(outer, text="Use Selected Theme in Book Studio", command=self._use, style="Primary.TButton").pack(anchor="e")

    def refresh(self) -> None:
        self.tree.delete(*self.tree.get_children()); self.rows: dict[str, Path] = {}; query = self.filter.get().strip().casefold()
        library = load_master_word_bank()
        ranked_rows: list[tuple[int, str, Path, dict, str, str, str, str, str]] = []
        for index, path in enumerate(saved_theme_files()):
            try: data = json.loads(path.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError): continue
            title = str(data.get("title") or path.stem)
            if query and query not in title.casefold(): continue
            ready, status = quick_theme_readiness(data); freshness, _ = word_bank_freshness(data); safety = publisher_safety_report(data, library)
            health = read_theme_health(THEME_HEALTH_CACHE_FILE, path)
            direct_fit, _direct_rule = direct_topic_fit_report(data)
            topic_fit = direct_fit if direct_fit is not None else safety.get("topic_fit")
            topic_text = f"{topic_fit}%" if isinstance(topic_fit, int) else "Review"
            package = "Ready" if find_latest_book_package(title) else "Not yet"
            launch_score, launch_label, _launch_reasons = theme_launch_readiness(data, library)
            if health is None:
                ready, status = False, "Needs content check"
            elif health.get("status") == "Blocked":
                ready, status = False, "Needs word-bank rebuild"
            elif ready:
                status = "Production check passed"
            if self.ready_only.get() and (not ready or health is None or health.get("status") != "Passed" or launch_label != "MAKE NEXT"):
                continue
            if safety.get("review_words"): status = "Rights review"
            elif direct_fit is not None and direct_fit < 60: status = "Topic-fit fix"
            elif safety.get("warnings") and ready: status = "Review notes"
            elif ready: status = "Ready"
            ranked_rows.append((launch_score, title.casefold(), path, data, freshness, topic_text, package, status, launch_label))
        for index, (launch_score, _sort_title, path, data, freshness, topic_text, package, status, launch_label) in enumerate(sorted(ranked_rows, key=lambda row: (-row[0], row[1]))):
            iid=f"theme_{index}"; self.rows[iid]=path
            self.tree.insert("", "end", iid=iid, values=(str(data.get("title") or path.stem), len(data.get("puzzles", [])), puzzle_difficulty_label(data), f"{freshness}%", topic_text, f"{launch_score}/100", package, launch_label if launch_label == "MAKE NEXT" else status))

    def _use(self, _event: object = None) -> None:
        selected = self.tree.selection()
        if not selected: return
        self.parent._set_theme(self.rows[selected[0]]); self.parent.lift(); self.destroy()


class PublisherSafetyDialog(tk.Toplevel):
    """One page that turns safety signals into simple publishing decisions."""
    def __init__(self, parent: "WordSearchCreator") -> None:
        super().__init__(parent); self.parent = parent; self.title("Publisher Safety Check"); self.geometry("800x600"); self.minsize(650, 470); self.transient(parent); self.grab_set()
        frame = ttk.Frame(self, padding=18); frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="PUBLISHER SAFETY CHECK", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(frame, text="Checks that the book, cover, and listing make the same promise. It flags likely protected names for your review; it does not replace legal or KDP review.", foreground="#555555", wraplength=740).pack(anchor="w", pady=(3, 12))
        self.summary = ttk.Label(frame, wraplength=740); self.summary.pack(anchor="w", pady=(0, 10))
        self.report = ScrolledText(frame, wrap="word", font=("Segoe UI", 10), padx=12, pady=12); self.report.pack(fill="both", expand=True)
        actions = ttk.Frame(frame); actions.pack(fill="x", pady=(12, 0))
        ttk.Button(actions, text="Run Full Book Check", command=parent._check_quality, style="Primary.TButton").pack(side="left")
        ttk.Button(actions, text="Close", command=self.destroy, style="Action.TButton").pack(side="right")
        self.show_report()

    def show_report(self) -> None:
        if not self.parent.selected_theme:
            self.summary.configure(text="Choose a saved theme first.", foreground="#a33a1d"); return
        try: data = json.loads(self.parent.selected_theme.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc: self.summary.configure(text=f"Could not read the selected book: {exc}", foreground="#a33a1d"); return
        result = publisher_safety_report(data); warnings = result["warnings"]; notes = result["notes"]
        self.summary.configure(text="Review needed before publishing." if warnings else "No automatic safety concerns found. Run the full Book Check before creating a package.", foreground="#9a5b00" if warnings else "#245b4f")
        self.report.insert("end", "REVIEW BEFORE PUBLISHING\n")
        if warnings:
            for item in warnings: self.report.insert("end", f"• {item}\n")
        else: self.report.insert("end", "• No cover-promise mismatch or common protected-name review term was found.\n")
        self.report.insert("end", "\nWHAT THE APP CHECKED\n")
        for item in notes: self.report.insert("end", f"• {item}\n")
        self.report.insert("end", "\nFINAL HUMAN CHECK\n• Open the reader preview and the final cover. Make sure a buyer gets exactly what the title, subtitle, artwork, badge, and KDP listing describe.\n• If a word is a brand, character, celebrity, or franchise reference, do not use it automatically—verify your rights first.\n")
        self.report.configure(state="disabled")


class EditionDesignerDialog(tk.Toplevel):
    """Save a coordinated edition look without making another complicated cover screen."""
    def __init__(self, parent: "WordSearchCreator") -> None:
        super().__init__(parent); self.parent = parent; self.title("Edition Designer"); self.geometry("720x520"); self.minsize(620, 450); self.transient(parent); self.grab_set()
        data = self._data(); self.palette = tk.StringVar(value=str(data.get("palette") or parent.cover_palette.get())); self.style = tk.StringVar(value=next((label for label, value in PublishReadyDialog.STYLE_MAP.items() if value == str(data.get("cover_style") or "")), parent.cover_style.get())); self.badge = tk.StringVar(value=str(data.get("cover_badge") or parent.cover_badge.get())); self.signature = tk.BooleanVar(value=is_signature_edition(data)); self._build(data)

    def _data(self) -> dict:
        try: return json.loads(self.parent.selected_theme.read_text(encoding="utf-8-sig")) if self.parent.selected_theme else {}
        except (OSError, json.JSONDecodeError): return {}

    def _build(self, data: dict) -> None:
        frame = ttk.Frame(self, padding=18); frame.pack(fill="both", expand=True); frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text="EDITION DESIGNER", font=("Segoe UI", 18, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(frame, text="Save a coordinated look for this book or edition. It changes only the saved cover recommendation—your existing pages and words stay untouched.", wraplength=640, foreground="#555555").grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 16))
        for row, label, variable, values in ((2, "Color family", self.palette, CoverCreatorDialog.PALETTES), (3, "Cover layout", self.style, tuple(PublishReadyDialog.STYLE_MAP))):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=7); ttk.Combobox(frame, textvariable=variable, values=values, state="readonly").grid(row=row, column=1, sticky="ew", padx=(12, 0), pady=7)
        ttk.Label(frame, text="Front-cover callout").grid(row=4, column=0, sticky="w", pady=7); ttk.Entry(frame, textvariable=self.badge).grid(row=4, column=1, sticky="ew", padx=(12, 0), pady=7)
        ttk.Checkbutton(frame, text="Make this a Signature Edition (adds premium inside pages when you create the package)", variable=self.signature).grid(row=5, column=0, columnspan=2, sticky="w", pady=(10, 6))
        ttk.Label(frame, text="Tip: use the same color family and layout throughout a series; change the title, callout, and optional cover art so each book is easy to recognize.", foreground="#555555", wraplength=640).grid(row=6, column=0, columnspan=2, sticky="w", pady=(6, 0))
        buttons = ttk.Frame(frame); buttons.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(22, 0)); buttons.columnconfigure(0, weight=1); buttons.columnconfigure(1, weight=1)
        ttk.Button(buttons, text="Save Edition Look", command=self.save, style="Primary.TButton").grid(row=0, column=0, sticky="ew", padx=(0, 6)); ttk.Button(buttons, text="Cancel", command=self.destroy, style="Action.TButton").grid(row=0, column=1, sticky="ew", padx=(6, 0))

    def save(self) -> None:
        if not self.parent.selected_theme: return
        data = self._data()
        if self.signature.get() and len(data.get("puzzles", [])) < SIGNATURE_PUZZLE_TARGET:
            messagebox.showwarning("Signature Edition size", f"A Signature Edition is a {SIGNATURE_PUZZLE_TARGET}-puzzle collection. This theme has {len(data.get('puzzles', []))} puzzles, so its standard-edition setting was left unchanged.", parent=self)
            return
        automatic_theme_backup("saving Edition Designer settings")
        data["palette"] = self.palette.get(); data["cover_style"] = PublishReadyDialog.STYLE_MAP.get(self.style.get(), self.style.get()); data["cover_badge"] = self.badge.get().strip() or "WORD SEARCH PUZZLES"; data["signature_edition"] = {"enabled": bool(self.signature.get())}
        self.parent.selected_theme.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        self.parent._set_theme(self.parent.selected_theme); self.parent.signature_edition.set(self.signature.get()); self.parent.status.set("Saved the edition look. Review Before Creating will use it."); self.destroy()


class MarketPulseDialog(tk.Toplevel):
    """A small honest tracker for live research the user chooses to record."""
    def __init__(self, parent: "WordSearchCreator") -> None:
        super().__init__(parent); self.parent = parent; self.title("Market Pulse Tracker"); self.geometry("760x560"); self.minsize(640, 460); self.transient(parent)
        self.niche = tk.StringVar(value=str(parent.theme_name.get() or parent.book_title.get() or "")); self.interest = tk.StringVar(value="Promising"); self._build(); self.refresh()

    def _build(self) -> None:
        frame = ttk.Frame(self, padding=18); frame.pack(fill="both", expand=True); frame.columnconfigure(1, weight=1); frame.rowconfigure(4, weight=1)
        ttk.Label(frame, text="MARKET PULSE TRACKER", font=("Segoe UI", 18, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(frame, text="Open current live sources, then save your own short observation. This keeps a useful history without pretending that a changing website provides a permanent sales score.", wraplength=700, foreground="#555555").grid(row=1, column=0, columnspan=2, sticky="w", pady=(3, 12))
        ttk.Label(frame, text="Niche").grid(row=2, column=0, sticky="w"); ttk.Entry(frame, textvariable=self.niche).grid(row=2, column=1, sticky="ew", padx=(12, 0))
        buttons = ttk.Frame(frame); buttons.grid(row=3, column=0, columnspan=2, sticky="ew", pady=10)
        ttk.Button(buttons, text="Open Google Trends", command=lambda: self.open("trends")).pack(side="left", padx=(0, 6)); ttk.Button(buttons, text="Open Amazon Search", command=lambda: self.open("amazon")).pack(side="left", padx=6); ttk.Button(buttons, text="Save Today’s Observation", command=self.save, style="Primary.TButton").pack(side="right")
        self.history = ScrolledText(frame, wrap="word", font=("Segoe UI", 10), padx=12, pady=12); self.history.grid(row=4, column=0, columnspan=2, sticky="nsew")

    def open(self, source: str) -> None:
        niche = self.niche.get().strip()
        if not niche: messagebox.showinfo("Enter a niche", "Enter a niche first.", parent=self); return
        query = quote_plus(niche + " word search")
        webbrowser.open(f"https://trends.google.com/trends/explore?q={query}" if source == "trends" else f"https://www.amazon.com/s?k={query}")

    def save(self) -> None:
        niche = self.niche.get().strip()
        if not niche: messagebox.showinfo("Enter a niche", "Enter a niche first.", parent=self); return
        note = simpledialog.askstring("Today’s market note", "What did you see? Example: many covers use bright travel art; low competition for RV road trips.", parent=self)
        if not note or not note.strip(): return
        try: records = json.loads(MARKET_PULSE_FILE.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError): records = []
        if not isinstance(records, list): records = []
        records.insert(0, {"time": datetime.now().isoformat(timespec="seconds"), "niche": niche, "note": note.strip()})
        MARKET_PULSE_FILE.write_text(json.dumps(records[:200], indent=2, ensure_ascii=False) + "\n", encoding="utf-8"); self.refresh()

    def refresh(self) -> None:
        try: records = json.loads(MARKET_PULSE_FILE.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError): records = []
        self.history.configure(state="normal")
        self.history.delete("1.0", "end")
        self.history.insert("end", "SAVED MARKET OBSERVATIONS\n\n")
        if isinstance(records, list) and records:
            for item in records[:40]: self.history.insert("end", f"{item.get('time', '')} — {item.get('niche', '')}\n{item.get('note', '')}\n\n")
        else: self.history.insert("end", "No observations saved yet. Open a live source, jot down what you notice, and this tracker will keep it with your project.")
        self.history.configure(state="disabled")


class WordSearchCreator(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self._app_preferences = load_app_preferences()
        self.title("SladePuzzleCo Book Studio")
        self.geometry("1180x720")
        self.minsize(920, 600)
        self.resizable(True, True)
        # The studio is designed as a full-screen workspace.  F11 remains
        # available for the borderless full-screen view.
        self.bind("<F11>", self._toggle_fullscreen)
        self.bind("<Control-n>", lambda _event: (self._open_create_new_book(), "break")[1])
        self.bind("<Control-o>", lambda _event: (self._open_recent_package(), "break")[1])
        self.bind("<Control-p>", lambda _event: (self._open_production_dashboard(), "break")[1])
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.dark_mode = tk.BooleanVar(value=True)  # Kept for compatibility with older saved preferences.
        saved_theme = str(self._app_preferences.get("ui_theme") or "Studio Dark")
        self.ui_theme = tk.StringVar(value=saved_theme if saved_theme in ("Studio Dark", "Paper Light", "Neon Code Rain", "Midnight Indigo") else "Studio Dark")
        self.compact_home = tk.BooleanVar(value=bool(self._app_preferences.get("compact_home", False)))
        self._package_in_progress = False
        self._setup_styles()
        self.selected_theme: Path | None = None
        self.last_output: Path | None = None
        self.last_wrap_preview: Path | None = None

        self.theme_name = tk.StringVar()
        self.book_title = tk.StringVar()
        self.cover_title_feedback = tk.StringVar()
        self.subtitle = tk.StringVar()
        self.subtitle_feedback = tk.StringVar()
        self.book_specs = tk.StringVar(value="Estimated interior: choose a theme")
        self.author = tk.StringVar(value="Jordan M. Slade")
        self.seed = tk.StringVar(value="7")
        self.auto_seed = tk.BooleanVar(value=True)
        self.customize_visible = tk.BooleanVar(value=False)
        self.output_name = tk.StringVar()
        self.theme_filter = tk.StringVar()
        self.cover_palette = tk.StringVar(value="nature")
        self.cover_style = tk.StringVar(value="Playful Illustrated")
        self.cover_badge = tk.StringVar(value="WORD SEARCH PUZZLES")
        self.cover_imprint = tk.StringVar(value="Jordan M. Slade")
        self.cover_art = tk.StringVar()
        self.cover_art_focus = tk.StringVar(value="center")
        self.cover_art_note = tk.StringVar(value="Choose an OpenClipart image and I will suggest its crop focus automatically.")
        self.cover_layout_note = tk.StringVar()
        self.cover_plan = tk.StringVar(value="Your theme will choose the recommended colors, layout, callout, and publisher details automatically.")
        self.cover_style.trace_add("write", lambda *_args: self._update_layout_note())
        self.cover_palette.trace_add("write", lambda *_args: self._update_layout_note())
        self.book_title.trace_add("write", lambda *_args: self._update_book_automation())
        self.subtitle.trace_add("write", lambda *_args: self._update_subtitle_feedback())
        self.archive_after_package = tk.BooleanVar(value=False)
        self.signature_edition = tk.BooleanVar(value=False)
        self.main_assistant_prompt = tk.StringVar()
        self.main_assistant_theme: Path | None = None
        self.smart_kind = tk.StringVar(value="Word Search")
        self.smart_topic = tk.StringVar()
        self.smart_edition = tk.StringVar(value="Standard")
        self.trend_status = tk.StringVar(value="Find one current niche, then review it before building.")
        self.status = tk.StringVar(value="Choose a theme, then click Generate Book.")

        self._update_layout_note()
        self._update_title_feedback()
        self._update_subtitle_feedback()
        self._build_window()
        # Loading every saved theme must stay lightweight. Full topic-fit and
        # rights checks belong to Check / Fix, not the startup paint path.
        self._load_theme_list()
        self._bring_to_front()
        self.after(900, self._restore_comfort_settings)

    def _bring_to_front(self) -> None:
        """Ensure Windows shows the main window after a launcher starts it."""
        try:
            self.state("normal")
            width = min(1280, max(920, self.winfo_screenwidth() - 80))
            height = min(780, max(600, self.winfo_screenheight() - 120))
            self.geometry(f"{width}x{height}+40+30")
            self.deiconify()
            self.update_idletasks()
            self.lift()
            self.focus_force()
            self.attributes("-topmost", True)
            self.after(650, lambda: self.attributes("-topmost", False))
            self.after(120, lambda: self.state("zoomed"))
        except tk.TclError:
            pass

    def _restore_comfort_settings(self) -> None:
        """Restore familiar screen settings after Windows has shown the app."""
        if self.compact_home.get():
            self._apply_compact_home()
        last_theme = Path(str(self._app_preferences.get("last_theme") or ""))
        if last_theme.is_file():
            self._set_theme(last_theme)
        geometry = str(self._app_preferences.get("window_geometry") or "")
        state = str(self._app_preferences.get("window_state") or "")
        if geometry and state == "normal":
            try: self.geometry(geometry)
            except tk.TclError: pass

    def _on_close(self) -> None:
        if self._package_in_progress and not messagebox.askyesno("Package still being created", "A package is still being created. Closing now stops the app before the final checks finish. Close anyway?", parent=self):
            return
        try:
            save_app_preferences({
                "ui_theme": self.ui_theme.get(), "compact_home": self.compact_home.get(),
                "last_theme": str(self.selected_theme.resolve()) if self.selected_theme else "",
                "window_geometry": self.geometry(), "window_state": self.state(),
            })
        finally:
            self.destroy()

    def _setup_styles(self) -> None:
        """Apply a calm light or high-contrast dark workspace."""
        themes = {
            "Studio Dark": ("#212121", "#292929", "#212121", "#ececec", "#a6a6a6", "#3b3b3b", "#10a37f", True),
            "Paper Light": ("#f5f2eb", "#f5f2eb", "#203d4c", "#203d4c", "#555555", "#b9c8c5", "#26706b", False),
            "Neon Code Rain": ("#020a05", "#07170c", "#00280f", "#baffc3", "#75cd84", "#1d6631", "#00a83f", True),
            "Midnight Indigo": ("#121427", "#202244", "#292452", "#f2efff", "#c2bce6", "#585682", "#6c63c9", True),
        }
        bg, panel, hero, text, muted, border, primary, dark = themes.get(self.ui_theme.get(), themes["Studio Dark"])
        self.dark_mode.set(dark)
        self.configure(background=bg)
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("App.TFrame", background=bg)
        sidebar_bg = "#171717" if dark else "#f7f7f7"
        raised = "#292929" if dark else "#ffffff"
        style.configure("Chat.Main.TFrame", background=bg)
        style.configure("Chat.Sidebar.TFrame", background=sidebar_bg)
        style.configure("Chat.Header.TFrame", background=hero)
        style.configure("Chat.Composer.TFrame", background="#303030" if dark else "#f2f2f2")
        style.configure("Hero.TFrame", background=hero)
        style.configure("HeroTitle.TLabel", background=hero, foreground=text, font=("Segoe UI", 12, "bold"))
        style.configure("HeroText.TLabel", background=hero, foreground=muted, font=("Segoe UI", 9))
        style.configure("Hero.TCheckbutton", background=hero, foreground="#d9e6ea", font=("Segoe UI", 9, "bold"))
        style.map("Hero.TCheckbutton", background=[("active", hero)], foreground=[("active", "#ffffff")])
        style.configure("TLabel", background=bg, foreground=text)
        style.configure("Section.TLabelframe", background=panel, borderwidth=1, relief="solid", bordercolor=border)
        style.configure("Section.TLabelframe.Label", background=panel, foreground=text, font=("Segoe UI", 10, "bold"))
        style.configure("TLabelframe", background=panel)
        style.configure("TEntry", fieldbackground="#2d3942" if dark else "#ffffff", foreground=text, insertcolor=text)
        style.configure("TCombobox", fieldbackground="#2d3942" if dark else "#ffffff", background=panel, foreground=text)
        style.map("TCombobox", fieldbackground=[("readonly", "#2d3942" if dark else "#ffffff")], foreground=[("readonly", text)])
        style.configure("Theme.Treeview", background="#202a31" if dark else "#ffffff", foreground="#edf4f7" if dark else "#203d4c", fieldbackground="#202a31" if dark else "#ffffff", rowheight=27, bordercolor=border)
        style.map("Theme.Treeview", background=[("selected", "#26706b")], foreground=[("selected", "#ffffff")])
        style.configure("Primary.TButton", font=("Segoe UI", 10, "bold"), padding=(12, 9), foreground="#ffffff", background=primary)
        style.map("Primary.TButton", background=[("active", primary), ("disabled", "#9eb9b6")])
        style.configure("Action.TButton", font=("Segoe UI", 10), padding=(10, 8))
        style.configure("Suggestion.TButton", font=("Segoe UI", 9), padding=(8, 5))
        style.configure("Chat.Sidebar.TLabel", background=sidebar_bg, foreground="#ececec" if dark else "#222222", font=("Segoe UI", 9))
        style.configure("Chat.SidebarTitle.TLabel", background=sidebar_bg, foreground="#ececec" if dark else "#222222", font=("Segoe UI", 11, "bold"))
        style.configure("Chat.SidebarSection.TLabel", background=sidebar_bg, foreground="#a6a6a6" if dark else "#777777", font=("Segoe UI", 8, "bold"))
        style.configure("Chat.HeaderTitle.TLabel", background=hero, foreground=text, font=("Segoe UI Semibold", 14))
        style.configure("Chat.HeaderText.TLabel", background=hero, foreground=muted, font=("Segoe UI", 9))
        style.configure("Chat.Sidebar.TButton", font=("Segoe UI", 9), padding=(10, 8), foreground="#ececec" if dark else "#222222", background=sidebar_bg, borderwidth=0, relief="flat", anchor="w")
        style.map("Chat.Sidebar.TButton", background=[("active", "#2b2b2b" if dark else "#e9e9e9")])
        style.configure("Chat.Chip.TButton", font=("Segoe UI", 9), padding=(10, 5), foreground=text, background="#303030" if dark else "#f1f1f1", borderwidth=0, relief="flat")
        style.map("Chat.Chip.TButton", background=[("active", "#3a3a3a" if dark else "#e7e7e7")])
        style.configure("Chat.Send.TButton", font=("Segoe UI", 11, "bold"), padding=(9, 7), foreground="#ffffff", background=primary, borderwidth=0)
        style.map("Chat.Send.TButton", background=[("active", "#0d8b6c")])
        style.configure("Chat.Input.TEntry", fieldbackground="#303030" if dark else "#f2f2f2", foreground=text, insertcolor=text, borderwidth=0, relief="flat")
        style.configure("Chat.WelcomeCard.TFrame", background=raised, relief="flat")
        style.configure("Chat.WelcomeTitle.TLabel", background=raised, foreground=text, font=("Segoe UI", 10, "bold"))
        style.configure("Chat.WelcomeText.TLabel", background=raised, foreground=muted, font=("Segoe UI", 9))
        style.configure("Chat.Quick.TButton", font=("Segoe UI", 9, "bold"), padding=(10, 8), foreground=text, background=raised, borderwidth=0, relief="flat")
        style.map("Chat.Quick.TButton", background=[("active", "#363636" if dark else "#eeeeee")])
        style.configure("Chat.Start.TButton", font=("Segoe UI Semibold", 10), padding=(14, 12), foreground="#ffffff", background=primary, borderwidth=0)
        style.map("Chat.Start.TButton", background=[("active", "#0d8b6c" if dark else "#1b625d")])
        style.configure("Chat.Card.TFrame", background=raised, relief="flat")
        style.configure("Chat.CardTitle.TLabel", background=raised, foreground=text, font=("Segoe UI Semibold", 10))
        style.configure("Chat.CardText.TLabel", background=raised, foreground=muted, font=("Segoe UI", 9))
        style.configure("Status.TLabel", background="#173d3a" if dark else "#e5f1ed", foreground="#c6eee7" if dark else "#245b4f", padding=(10, 8), font=("Segoe UI", 9))
        style.configure("TNotebook", background=bg, borderwidth=0)
        style.configure("TNotebook.Tab", padding=(15, 8), font=("Segoe UI", 10, "bold"))
        if hasattr(self, "_content_canvas"):
            self._content_canvas.configure(background=bg)

    def _toggle_dark_mode(self) -> None:
        self.ui_theme.set("Studio Dark" if self.dark_mode.get() else "Paper Light")
        self._apply_ui_theme()

    def _apply_ui_theme(self, *_args: object) -> None:
        self._setup_styles()
        self._apply_main_assistant_appearance()
        self.status.set(f"Appearance changed to {self.ui_theme.get()}.")

    def _load_library_summary_async(self) -> None:
        """Keep the first visible paint quick while the large library is read."""
        def read() -> None:
            try:
                library_data = load_master_word_bank()
                words = int(library_data.get("total_unique_words", 0)) if isinstance(library_data, dict) else 0
                topics = len(library_data.get("topics", {})) if isinstance(library_data, dict) else 0
                intelligence = library_intelligence_summary()
                text = (f"Library: {words:,} words across {topics} topics | "
                        f"{intelligence['ready_48']} ready now | {intelligence['needs_expansion']} safely being expanded")
            except Exception:
                text = "Library details will appear when you open a word-search tool."
            self.after(0, lambda: self.library_summary.set(text) if self.winfo_exists() else None)
        threading.Thread(target=read, daemon=True).start()

    def _toggle_compact_home(self) -> None:
        self.compact_home.set(not self.compact_home.get())
        self._apply_compact_home()

    def _apply_compact_home(self) -> None:
        if not hasattr(self, "home_sidebar"):
            return
        if self.compact_home.get():
            self.home_sidebar.grid_remove()
            self.status.set("Compact view is on. Use the Book Assistant or the top buttons; switch it off anytime from Appearance.")
        else:
            self.home_sidebar.grid()
            self.status.set("Full view is on. Your creation and publishing shortcuts are visible again.")

    def _build_window(self) -> None:
        # Laptop screens often have less usable height than the studio needs.
        # Keep every button reachable with one natural mouse-wheel scroll.
        shell = ttk.Frame(self, style="App.TFrame"); shell.pack(fill="both", expand=True)
        shell.columnconfigure(0, weight=1); shell.rowconfigure(0, weight=1)
        self._content_canvas = tk.Canvas(shell, highlightthickness=0, background="#171d22")
        self._content_canvas.grid(row=0, column=0, sticky="nsew")
        self._content_scrollbar = ttk.Scrollbar(shell, orient="vertical", command=self._content_canvas.yview)
        self._content_scrollbar.grid(row=0, column=1, sticky="ns")
        self._content_canvas.configure(yscrollcommand=self._content_scrollbar.set)
        outer = ttk.Frame(self._content_canvas, padding=0, style="Chat.Main.TFrame")
        self._content_outer = outer
        self._content_window = self._content_canvas.create_window((0, 0), window=outer, anchor="nw")
        outer.bind("<Configure>", self._refresh_content_scrollbar)
        self._content_canvas.bind("<Configure>", self._resize_content_window)
        self._content_canvas.bind_all("<MouseWheel>", self._scroll_studio)
        outer.columnconfigure(0, weight=1); outer.rowconfigure(1, weight=1); outer.rowconfigure(2, weight=0)
        hero = ttk.Frame(outer, padding=(18, 10), style="Chat.Header.TFrame"); hero.grid(row=0, column=0, sticky="ew")
        ttk.Label(hero, text="SLADEPUZZLECO  /  BOOK STUDIO", style="HeroTitle.TLabel").pack(side="left")
        hero_actions = ttk.Frame(hero, style="Chat.Header.TFrame"); hero_actions.pack(side="right")
        appearance = ttk.Frame(hero_actions, style="Chat.Header.TFrame"); appearance.pack(side="right")
        ttk.Label(appearance, text="Appearance", style="HeroText.TLabel").pack(side="left", padx=(0, 7))
        theme_picker = ttk.Combobox(appearance, textvariable=self.ui_theme, values=("Studio Dark", "Paper Light", "Neon Code Rain", "Midnight Indigo"), state="readonly", width=18)
        theme_picker.pack(side="left"); theme_picker.bind("<<ComboboxSelected>>", self._apply_ui_theme)
        ttk.Checkbutton(appearance, text="Compact view", variable=self.compact_home, command=self._apply_compact_home, style="Hero.TCheckbutton").pack(side="left", padx=(10, 0))
        ttk.Button(hero_actions, text="New conversation", command=self._reset_main_assistant, style="Chat.Chip.TButton").pack(side="left", padx=(0, 6))
        ttk.Button(hero_actions, text="Production dashboard", command=self._open_production_dashboard, style="Chat.Chip.TButton").pack(side="left", padx=(0, 6))
        ttk.Button(hero_actions, text="Create a book", command=self._open_create_new_book, style="Chat.Chip.TButton").pack(side="left", padx=(0, 6))
        ttk.Button(hero_actions, text="Check / fix", command=self._open_book_readiness, style="Chat.Chip.TButton").pack(side="left", padx=(0, 6))
        ttk.Button(hero_actions, text="Review cover", command=self._open_cover_choices, style="Chat.Chip.TButton").pack(side="left", padx=(0, 6))
        ttk.Button(hero_actions, text="Prepare / publish", command=self._open_publishing_manager, style="Chat.Chip.TButton").pack(side="left", padx=(0, 6))
        self.workspace_button = ttk.Button(hero_actions, text="Word Search details", command=self._toggle_word_search_workspace, style="Chat.Chip.TButton")
        self.workspace_button.pack(side="left", padx=(8, 0))
        self._build_home_dashboard(outer)
        self.workspace = ttk.Frame(outer, style="App.TFrame")
        self.workspace.grid(row=2, column=0, sticky="nsew")
        self.workspace.columnconfigure(0, weight=1); self.workspace.rowconfigure(0, weight=1)
        studio = ttk.Panedwindow(self.workspace, orient="horizontal"); studio.grid(row=0, column=0, sticky="nsew")
        library = ttk.Labelframe(studio, text="STEP 1 — CHOOSE A BOOK", padding=12, style="Section.TLabelframe", width=260)
        editor = ttk.Frame(studio, padding=(16, 0, 0, 0), style="App.TFrame")
        studio.add(library, weight=1); studio.add(editor, weight=3)
        library.columnconfigure(0, weight=1); library.rowconfigure(6, weight=1)
        ttk.Label(library, text="Recently used", foreground="#555555").grid(row=0, column=0, sticky="w")
        self.recent_theme = tk.StringVar()
        self.recent_picker = ttk.Combobox(library, textvariable=self.recent_theme, state="readonly")
        self.recent_picker.grid(row=1, column=0, sticky="ew", pady=(5, 10)); self.recent_picker.bind("<<ComboboxSelected>>", self._recent_theme_changed)
        self.favorite_button = ttk.Button(library, text="☆ Add Current Theme to Favorites", command=self._toggle_current_favorite, style="Action.TButton")
        self.favorite_button.grid(row=2, column=0, sticky="ew")
        # The Master Library is large.  Do not make the visible app wait for it
        # on launch; load this helpful summary after the window is responsive.
        self.library_summary=tk.StringVar(value="Library: checking your saved topics in the background…")
        ttk.Label(library,textvariable=self.library_summary,foreground="#245b4f",wraplength=235).grid(row=3,column=0,sticky="w",pady=(8,0))
        ttk.Label(library, text="Search your saved themes", foreground="#555555").grid(row=4, column=0, sticky="w", pady=(10, 0))
        search = ttk.Entry(library, textvariable=self.theme_filter); search.grid(row=5, column=0, sticky="ew", pady=(5, 9)); self.theme_filter.trace_add("write", self._refresh_theme_library)
        self.theme_tree = ttk.Treeview(library, show="tree", style="Theme.Treeview", selectmode="browse")
        self.theme_tree.grid(row=6, column=0, sticky="nsew"); self.theme_tree.bind("<<TreeviewSelect>>", self._theme_changed)
        ttk.Button(library, text="Start a New Book…", command=self._open_guided_book_builder, style="Primary.TButton").grid(row=7, column=0, sticky="ew", pady=(10, 6))
        library_tools = ttk.Menubutton(library, text="More Book & Library Tools ▾", style="Action.TButton")
        library_menu = tk.Menu(library_tools, tearoff=False)
        library_menu.add_command(label="Choose My Next Book", command=self._open_theme_dashboard)
        library_menu.add_command(label="Library & Quality Center", command=self._open_word_bank_health)
        library_menu.add_command(label="Word Intelligence Center", command=self._open_word_intelligence)
        library_menu.add_command(label="Refresh Library Intelligence", command=self._refresh_library_intelligence)
        library_menu.add_command(label="Research New Ideas", command=self._open_niche_research)
        library_menu.add_separator()
        library_menu.add_command(label="Build a Book from a Topic Pack", command=self._open_topic_pack_builder)
        library_menu.add_command(label="New Book Blueprint (Advanced)", command=self._open_book_blueprint)
        library_menu.add_command(label="New or Edit Theme", command=self._open_theme_builder)
        library_menu.add_command(label="Rebuild Current Theme from Its Topic", command=self._rebuild_current_theme)
        library_menu.add_command(label="Import Word Bank", command=self._open_word_bank_importer)
        library_menu.add_command(label="Move Current Theme to Folder", command=self._move_theme_to_folder)
        library_menu.add_command(label="Archive Current Theme / Mark as Research", command=self._archive_current_theme)
        library_menu.add_command(label="Series Manager", command=self._open_series_builder)
        library_tools.configure(menu=library_menu); library_tools.grid(row=8, column=0, sticky="ew")
        editor.columnconfigure(0, weight=1); editor.columnconfigure(1, weight=1)
        details = ttk.Labelframe(editor, text="STEP 2 — NAME YOUR BOOK", padding=14, style="Section.TLabelframe"); details.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        cover = ttk.Labelframe(editor, text="STEP 3 — COVER PLAN", padding=14, style="Section.TLabelframe"); cover.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        for card in (details, cover): card.columnconfigure(1, weight=1)
        self._studio_field(details, 0, "Title", self.book_title); self._studio_field(details, 1, "Subtitle", self.subtitle)
        ttk.Label(details, text="Slade Puzzles is used as the publisher automatically. A fresh puzzle pattern and inside-pages name will be created for your package.", foreground="#666666", wraplength=285).grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Label(details, textvariable=self.cover_title_feedback, foreground="#9a5b00", wraplength=280).grid(row=3, column=0, columnspan=2, sticky="w", pady=(5, 0))
        ttk.Label(details, textvariable=self.subtitle_feedback, foreground="#666666", wraplength=280).grid(row=4, column=0, columnspan=2, sticky="w", pady=(3, 0))
        ttk.Label(details, textvariable=self.book_specs, foreground="#245b4f", wraplength=280).grid(row=5, column=0, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Label(cover, text="AUTOMATIC COVER PLAN", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(cover, textvariable=self.cover_plan, foreground="#245b4f", wraplength=310).grid(row=1, column=0, columnspan=2, sticky="w", pady=(3, 8))
        art_label = ttk.Label(cover, text="Cover picture"); art_label.grid(row=2, column=0, sticky="w", pady=5); add_hover_help(art_label, "The app picks the best matching local background automatically when one is available. You can use a different saved picture whenever you want.")
        ttk.Entry(cover, textvariable=self.cover_art, state="readonly").grid(row=2, column=1, sticky="ew", padx=(10, 0), pady=5)
        ttk.Button(cover, text="Use Best Matching Picture", command=self._apply_theme_background_photo, style="Primary.TButton").grid(row=3, column=0, sticky="ew", pady=(5, 0))
        ttk.Button(cover, text="See Other Matching Pictures", command=self._open_photo_choice_picker, style="Action.TButton").grid(row=3, column=1, sticky="ew", padx=(10, 0), pady=(5, 0))
        picture_tools = ttk.Menubutton(cover, text="More Picture Options ▾", style="Action.TButton")
        picture_menu = tk.Menu(picture_tools, tearoff=False)
        picture_menu.add_command(label="Generate an approved background…", command=self._open_background_generator)
        picture_menu.add_command(label="Browse reference art (not used in production)…", command=self._find_free_artwork)
        picture_menu.add_command(label="Choose a picture for preview only…", command=self._choose_cover_art)
        picture_menu.add_command(label="Open reference-art library…", command=self._open_saved_art_library)
        picture_menu.add_separator()
        picture_menu.add_command(label="Match cover colors to this picture", command=self._match_art_colors)
        picture_menu.add_command(label="Check picture quality", command=self._check_art_quality)
        picture_tools.configure(menu=picture_menu); picture_tools.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(5, 0))
        ttk.Label(cover, textvariable=self.cover_art_note, foreground="#666666", wraplength=280).grid(row=5, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Button(cover, text="Customize Details (optional)", command=self._toggle_customize, style="Action.TButton").grid(row=6, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        self.customize_frame = ttk.Labelframe(editor, text="OPTIONAL DETAILS", padding=14, style="Section.TLabelframe")
        self.customize_frame.columnconfigure(0, weight=1); self.customize_frame.columnconfigure(1, weight=1)
        advanced_book = ttk.Frame(self.customize_frame, style="App.TFrame"); advanced_book.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        advanced_cover = ttk.Frame(self.customize_frame, style="App.TFrame"); advanced_cover.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        for panel in (advanced_book, advanced_cover): panel.columnconfigure(1, weight=1)
        self._studio_field(advanced_book, 0, "Author", self.author); self._studio_field(advanced_book, 1, "Puzzle pattern", self.seed); self._studio_field(advanced_book, 2, "Inside-pages file", self.output_name)
        ttk.Checkbutton(advanced_book, text="Use a fresh puzzle pattern automatically", variable=self.auto_seed).grid(row=3, column=0, columnspan=2, sticky="w", pady=(7, 0))
        self._studio_field(advanced_cover, 0, "Cover callout", self.cover_badge); self._studio_field(advanced_cover, 1, "Back-cover name", self.cover_imprint)
        ttk.Label(advanced_cover, text="Colors").grid(row=2, column=0, sticky="w", pady=5)
        ttk.Combobox(advanced_cover, textvariable=self.cover_palette, values=CoverCreatorDialog.PALETTES, state="readonly").grid(row=2, column=1, sticky="ew", padx=(10, 0), pady=5)
        ttk.Label(advanced_cover, text="Cover layout").grid(row=3, column=0, sticky="w", pady=5)
        ttk.Combobox(advanced_cover, textvariable=self.cover_style, values=tuple(PublishReadyDialog.STYLE_MAP), state="readonly").grid(row=3, column=1, sticky="ew", padx=(10, 0), pady=5)
        ttk.Button(advanced_cover, text="Reset to Theme Recommendation", command=self._reset_cover_settings, style="Action.TButton").grid(row=4, column=0, sticky="ew", pady=(7, 0))
        ttk.Button(advanced_cover, text="Try a Random Good Cover", command=self._random_good_cover, style="Action.TButton").grid(row=4, column=1, sticky="ew", padx=(10, 0), pady=(7, 0))
        actions = ttk.Labelframe(editor, text="STEP 4 — REVIEW, CREATE & PROOF", padding=14, style="Section.TLabelframe"); actions.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(16, 0)); actions.columnconfigure(0, weight=1); actions.columnconfigure(1, weight=1); actions.columnconfigure(2, weight=1)
        self.quality_button = ttk.Button(actions, text="Preview Cover", command=self._preview_this_topic, style="Action.TButton"); self.quality_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        create_options = ttk.Menubutton(actions, text="Proof & Extra Outputs ▾", style="Action.TButton")
        create_menu = tk.Menu(create_options, tearoff=False)
        create_menu.add_command(label="Create Quick Proof Bundle", command=self._create_proof_bundle_only)
        create_menu.add_separator()
        create_menu.add_command(label="Create Interior PDF Only", command=self._generate)
        create_menu.add_command(label="Run Exact Publish Ready Check", command=self._open_publish_ready_dashboard)
        create_menu.add_command(label="Create 3-Puzzle Reader Preview", command=self._generate_reader_preview)
        create_options.configure(menu=create_menu); create_options.grid(row=0, column=1, sticky="ew", padx=6)
        self.generate_button = ttk.Button(actions, text="Review & Create Package", command=self._open_buyer_preview, style="Primary.TButton"); self.generate_button.grid(row=0, column=2, sticky="ew", padx=(6, 0))
        cover_tools = ttk.Menubutton(actions, text="Cover Tools ▾", style="Action.TButton")
        cover_menu = tk.Menu(cover_tools, tearoff=False)
        cover_menu.add_command(label="Create Front Cover Only", command=self._generate_studio_cover)
        cover_menu.add_command(label="Preview Cover + Safe Guide", command=self._preview_studio_cover)
        cover_menu.add_command(label="Preview Full KDP Wrap", command=self._preview_wrap)
        cover_menu.add_separator()
        cover_menu.add_command(label="Compare Cover Variations", command=self._open_cover_gallery)
        cover_menu.add_command(label="Edit Back-Cover Blurb", command=self._edit_back_cover_blurb)
        cover_menu.add_command(label="Picture Library & Free CC0 Artwork", command=self._find_free_artwork)
        cover_tools.configure(menu=cover_menu); cover_tools.grid(row=1, column=0, sticky="ew", padx=(0, 6), pady=(10, 0))
        self.open_button = ttk.Button(actions, text="Proofing Center", command=self._open_proofing_center, style="Action.TButton"); self.open_button.grid(row=1, column=1, sticky="ew", padx=6, pady=(10, 0))
        production_tools = ttk.Menubutton(actions, text="More Tools & Help ▾", style="Action.TButton")
        production_menu = tk.Menu(production_tools, tearoff=False)
        production_menu.add_command(label="Publication Pipeline", command=self._open_publication_pipeline)
        production_menu.add_command(label="My Books Dashboard", command=self._open_release_manager)
        planning=tk.Menu(production_menu,tearoff=False); planning.add_command(label="Seasonal Publishing Calendar",command=self._open_seasonal_calendar); planning.add_command(label="Theme Preview Card",command=self._show_theme_preview_card); planning.add_command(label="Theme Notes & Research",command=self._edit_theme_notes); production_menu.add_cascade(label="Planning & Research",menu=planning)
        manage=tk.Menu(production_menu,tearoff=False); manage.add_command(label="Create Marketing Copy",command=self._create_marketing_copy); manage.add_command(label="Series Differentiation",command=self._open_series_differentiation); manage.add_command(label="Edition Designer",command=self._open_edition_designer); manage.add_command(label="Create Next in Series",command=self._open_series_expansion); manage.add_command(label="Open Production Queue",command=self._open_production_queue); manage.add_command(label="Production History",command=self._open_production_history); production_menu.add_cascade(label="Production Management",menu=manage)
        settings_menu=tk.Menu(production_menu,tearoff=False); settings_menu.add_command(label="Review This Book's Safety",command=self._open_publisher_safety); settings_menu.add_command(label="Check the Whole Project",command=self._run_project_check); settings_menu.add_command(label="Market Pulse Tracker",command=self._open_market_pulse); settings_menu.add_separator(); settings_menu.add_command(label="Create Production Lock + First-Five Tracker",command=self._create_production_lock); settings_menu.add_command(label="Open First-Five Review Tracker",command=self._open_launch_batch_tracker); settings_menu.add_command(label="Create Theme Backup",command=self._create_backup); settings_menu.add_command(label="Restore Backup Safely",command=self._restore_backup); settings_menu.add_command(label="Edit Brand Kit",command=self._edit_brand_kit); settings_menu.add_command(label="Refresh Smart Theme Scan",command=self._refresh_smart_theme_scan); production_menu.add_cascade(label="Safety & Settings",menu=settings_menu)
        production_menu.add_separator(); production_menu.add_command(label="First Book Walkthrough", command=self._show_first_book_walkthrough); production_menu.add_command(label="What Does This Do?", command=self._open_help_center); production_menu.add_command(label="Open Error Log", command=self._open_error_log); production_menu.add_command(label="About This Version", command=self._show_version)
        production_tools.configure(menu=production_menu); production_tools.grid(row=1, column=2, sticky="ew", padx=(6, 0), pady=(10, 0))
        self.status_label = ttk.Label(outer, textvariable=self.status, wraplength=740, style="Status.TLabel")
        self.status_label.grid(row=3, column=0, sticky="ew", padx=12, pady=(8, 0))
        self.workspace.grid_remove()
        self.status_label.grid_remove()
        self._set_workspace_scrolling(False)
        self.after_idle(self._sync_content_window_height)
        self.after(120, self._load_library_summary_async)

    def _build_home_dashboard(self, parent: ttk.Widget) -> None:
        """A clean, assistant-first home screen instead of a tool-dense dashboard."""
        home = ttk.Frame(parent, style="Chat.Main.TFrame")
        self.home_view = home
        home.grid(row=1, column=0, sticky="nsew")
        home.columnconfigure(1, weight=1); home.rowconfigure(0, weight=1)

        sidebar = ttk.Frame(home, padding=(14, 18), style="Chat.Sidebar.TFrame", width=236)
        self.home_sidebar = sidebar
        sidebar.grid(row=0, column=0, sticky="nsw")
        sidebar.grid_propagate(False)
        ttk.Label(sidebar, text="SLADEPUZZLECO", style="Chat.SidebarTitle.TLabel").pack(anchor="w")
        ttk.Label(sidebar, text="Your publishing workspace", style="Chat.Sidebar.TLabel").pack(anchor="w", pady=(2, 16))
        ttk.Button(sidebar, text="◆  Production dashboard", command=self._open_production_dashboard, style="Chat.Sidebar.TButton").pack(fill="x", pady=(0, 8))
        ttk.Label(sidebar, text="YOUR FOUR STEPS", style="Chat.SidebarSection.TLabel").pack(anchor="w", pady=(4, 4))
        ttk.Button(sidebar, text="1  Create a book", command=self._open_create_new_book, style="Chat.Sidebar.TButton").pack(fill="x", pady=1)
        create_more = ttk.Menubutton(sidebar, text="    More creation options ▾", style="Chat.Sidebar.TButton")
        create_menu = tk.Menu(create_more, tearoff=False)
        create_menu.add_command(label="Word Search library", command=self._show_word_search_workspace)
        create_menu.add_command(label="Guided Word Search Builder", command=self._open_guided_book_builder)
        create_menu.add_separator()
        for label, kind in (("Sudoku books", "Sudoku"), ("Cryptogram books", "Cryptogram"), ("Scramble + Trivia books", "Word Scramble + Trivia"), ("Mixed puzzle books", "Mixed Brain Games")):
            create_menu.add_command(label=label, command=lambda value=kind: self._open_other_puzzle_studio(value))
        create_more.configure(menu=create_menu); create_more.pack(fill="x", pady=1)
        ttk.Separator(sidebar).pack(fill="x", pady=8)
        ttk.Button(sidebar, text="2  Check / fix a book", command=self._open_book_readiness, style="Chat.Sidebar.TButton").pack(fill="x", pady=1)
        check_more = ttk.Menubutton(sidebar, text="    Checks, proof & help ▾", style="Chat.Sidebar.TButton")
        check_menu = tk.Menu(check_more, tearoff=False)
        check_menu.add_command(label="Book readiness", command=self._open_book_readiness)
        check_menu.add_command(label="Review & proof", command=self._open_proofing_center)
        check_menu.add_command(label="Check whole project", command=self._run_project_check)
        check_menu.add_command(label="Word Library health", command=self._open_word_bank_health)
        check_menu.add_command(label="Error log", command=self._open_error_log)
        check_menu.add_separator()
        check_menu.add_command(label="Help & explanations", command=self._open_help_center)
        check_more.configure(menu=check_menu); check_more.pack(fill="x", pady=1)
        ttk.Separator(sidebar).pack(fill="x", pady=8)
        ttk.Button(sidebar, text="3  Review / approve a cover", command=self._open_cover_choices, style="Chat.Sidebar.TButton").pack(fill="x", pady=1)
        cover_more = ttk.Menubutton(sidebar, text="    Cover tools & artwork ▾", style="Chat.Sidebar.TButton")
        cover_menu = tk.Menu(cover_more, tearoff=False)
        cover_menu.add_command(label="Choose a cover direction", command=self._open_cover_choices)
        cover_menu.add_command(label="Compare cover variations", command=self._open_cover_gallery)
        cover_menu.add_command(label="Open Cover Creator", command=self._open_cover_creator)
        cover_menu.add_command(label="Open artwork library", command=self._open_saved_art_library)
        cover_more.configure(menu=cover_menu); cover_more.pack(fill="x", pady=1)
        ttk.Separator(sidebar).pack(fill="x", pady=8)
        ttk.Button(sidebar, text="4  Prepare / publish a package", command=self._open_publishing_manager, style="Chat.Sidebar.TButton").pack(fill="x", pady=1)
        publish_more = ttk.Menubutton(sidebar, text="    Packages & publishing tools ▾", style="Chat.Sidebar.TButton")
        publish_menu = tk.Menu(publish_more, tearoff=False)
        publish_menu.add_command(label="Publishing Center", command=self._open_publishing_manager)
        publish_menu.add_command(label="Production dashboard", command=self._open_production_dashboard)
        publish_menu.add_command(label="Approved queue", command=self._open_production_queue)
        publish_menu.add_command(label="Open saved packages", command=self._open_output_folder)
        publish_menu.add_command(label="Open most recent package", command=self._open_recent_package)
        publish_more.configure(menu=publish_menu); publish_more.pack(fill="x", pady=1)

        chat_panel = ttk.Frame(home, style="Chat.Main.TFrame")
        chat_panel.grid(row=0, column=1, sticky="nsew", padx=(28, 32))
        chat_panel.columnconfigure(0, weight=1); chat_panel.rowconfigure(1, weight=1)
        header = ttk.Frame(chat_panel, style="Chat.Main.TFrame", padding=(0, 14, 0, 7)); header.grid(row=0, column=0, sticky="ew")
        ttk.Label(header, text="What would you like to make?", style="Chat.HeaderTitle.TLabel").pack(anchor="w")
        ttk.Label(header, text="Describe the book you want, or follow the four steps at left: create, check, review the cover, then prepare the package. The studio applies checked content, matching cover direction, reader-friendly formatting, and publishing-ready defaults automatically.", style="Chat.HeaderText.TLabel", wraplength=840).pack(anchor="w", pady=(4, 11))
        chips = ttk.Frame(header, style="Chat.Main.TFrame"); chips.pack(fill="x")
        for prompt in ("National parks word search", "Large-print Sudoku", "Space cryptograms", "Mixed brain games"):
            ttk.Button(chips, text=prompt, command=lambda value=prompt: self._use_main_assistant_example(value), style="Chat.Chip.TButton").pack(side="left", padx=(0, 6))
        next_card = ttk.Frame(header, padding=(14, 10), style="Chat.WelcomeCard.TFrame")
        next_card.pack(fill="x", pady=(8, 0))
        ttk.Label(next_card, text="NEXT BEST STEP", style="Chat.SidebarSection.TLabel").pack(anchor="w")
        self.home_next_text = tk.StringVar(value="Checking your local book catalog…")
        ttk.Label(next_card, textvariable=self.home_next_text, style="Chat.WelcomeText.TLabel", wraplength=650).pack(side="left", anchor="w", pady=(3, 0))
        self.home_next_button = ttk.Button(next_card, text="Open", command=self._run_home_next_action, style="Chat.Start.TButton")
        self.home_next_button.pack(side="right", padx=(12, 0))
        self.home_next_action: dict[str, str] = {"kind": "create", "book_id": "", "label": "Create your first book", "detail": ""}
        chat_shell = ttk.Frame(chat_panel, style="Chat.Main.TFrame")
        chat_shell.grid(row=1, column=0, sticky="nsew")
        chat_shell.columnconfigure(0, weight=1); chat_shell.rowconfigure(0, weight=1)
        welcome = ttk.Frame(chat_shell, padding=(12, 9), style="Chat.WelcomeCard.TFrame")
        welcome.grid(row=0, column=0, sticky="ew", pady=(0, 7))
        ttk.Label(welcome, text="Smart Book Setup", style="Chat.WelcomeTitle.TLabel").grid(row=0, column=0, columnspan=4, sticky="w")
        ttk.Label(welcome, text="Choose the idea here. Puzzle size, difficulty, interior design, cover direction, and publishing details are recommended inside the checked review plan.", style="Chat.WelcomeText.TLabel", wraplength=860).grid(row=1, column=0, columnspan=4, sticky="w", pady=(3, 8))
        ttk.Combobox(welcome, textvariable=self.smart_kind, values=CreateNewBookDialog.TYPES, state="readonly", width=22).grid(row=2, column=0, sticky="ew", padx=(0, 6))
        ttk.Entry(welcome, textvariable=self.smart_topic, width=32).grid(row=2, column=1, sticky="ew", padx=(0, 6))
        ttk.Combobox(welcome, textvariable=self.smart_edition, values=("Standard", "Signature Edition"), state="readonly", width=18).grid(row=2, column=2, sticky="ew", padx=(0, 6))
        ttk.Button(welcome, text="Review Book Plan", command=self._review_smart_book_plan, style="Chat.Start.TButton").grid(row=2, column=3, sticky="ew")
        welcome.columnconfigure(1, weight=1)
        trend = ttk.Frame(welcome, style="Chat.WelcomeCard.TFrame"); trend.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(8, 0)); trend.columnconfigure(0, weight=1)
        ttk.Label(trend, textvariable=self.trend_status, style="Chat.WelcomeText.TLabel", wraplength=650).grid(row=0, column=0, sticky="w")
        self.trend_button = ttk.Button(trend, text="Find a Trending Niche", command=self._find_trending_niche, style="Chat.Quick.TButton")
        self.trend_button.grid(row=0, column=1, padx=(10, 0))
        self.main_assistant_chat = tk.Text(chat_shell, wrap="word", height=4, relief="flat", borderwidth=0, highlightthickness=0, padx=14, pady=6, font=("Segoe UI", 10), spacing3=11)
        self.main_assistant_chat.grid(row=1, column=0, sticky="nsew")
        chat_shell.rowconfigure(0, weight=0)
        chat_shell.rowconfigure(1, weight=1)
        self.main_assistant_chat.bind("<MouseWheel>", lambda event: self.main_assistant_chat.yview_scroll(-1 * int(event.delta / 120), "units"))
        composer = ttk.Frame(chat_panel, style="Chat.Composer.TFrame", padding=(14, 9))
        composer.grid(row=2, column=0, sticky="ew", pady=(6, 8))
        composer.columnconfigure(0, weight=1)
        entry = ttk.Entry(composer, textvariable=self.main_assistant_prompt, font=("Segoe UI", 11), style="Chat.Input.TEntry")
        entry.grid(row=0, column=0, sticky="ew", padx=(0, 8)); entry.bind("<Return>", lambda _event: self._main_assistant_send())
        ttk.Button(composer, text="↑", width=3, command=self._main_assistant_send, style="Chat.Send.TButton").grid(row=0, column=1)
        self._apply_main_assistant_appearance()
        self._main_assistant_say("Hi — I’m your Book Assistant. Tell me what you want to create in everyday words.\n\nI will guide you through four clear steps: create a book, check or fix it, review its cover, and prepare its package. I can start a Word Search from your saved themes, make Sudoku with numbers, letters, and shapes, build Cryptograms or Scramble + Trivia, or create a Mixed Brain Games book with a separate themed title page before each section. You can also say “Show commands,” “check my book,” “review my cover,” or “prepare my package.”")
        self.after(250, self._refresh_home_next_action)

    def _review_smart_book_plan(self) -> None:
        """Route the embedded setup through the established checked creators."""
        topic = self.smart_topic.get().strip()
        if not topic:
            messagebox.showwarning("Add a topic", "Type a topic or use Find a Trending Niche first.", parent=self)
            return
        kind, edition = self.smart_kind.get(), self.smart_edition.get()
        if kind == "Word Search":
            GuidedBookBuilderDialog(self, initial_topic=topic, initial_pack=topic,
                                    initial_count=100 if edition == "Signature Edition" else 48)
        else:
            self._open_other_puzzle_studio(kind, topic, edition)
        self.status.set(f"Opened the review plan for {topic}. Nothing has been created or published yet.")

    def _find_trending_niche(self) -> None:
        """Run one explicit, bounded research request without freezing Tk."""
        self.trend_button.configure(state="disabled")
        self.trend_status.set("Checking current web evidence and your local production capacity…")
        def work() -> None:
            try:
                from publishing import PublishingService
                from publishing.trend_research import TrendResearchService
                result = TrendResearchService(APP_DIR, PublishingService(APP_DIR)).discover()
                self.after(0, lambda: self._show_trend_proposal(result))
            except Exception as exc:
                self.after(0, lambda detail=str(exc): self._trend_failed(detail))
        threading.Thread(target=work, name="trend-research", daemon=True).start()

    def _show_trend_proposal(self, proposal) -> None:
        self.trend_button.configure(state="normal")
        self.smart_topic.set(proposal.topic)
        if proposal.puzzle_type in CreateNewBookDialog.TYPES:
            self.smart_kind.set(proposal.puzzle_type)
        source_note = proposal.source
        self.trend_status.set(f"Review suggestion: {proposal.topic} • {source_note}")
        citations = "\n".join(f"• {url}" for url in proposal.source_urls) or "• No live citations—local fallback only."
        approved = messagebox.askyesno("Review niche suggestion",
            f"TOPIC\n{proposal.topic}\n\nPUZZLE TYPE\n{proposal.puzzle_type}\n\nAUDIENCE\n{proposal.audience}\n\nWHY REVIEW IT\n{proposal.buyer_angle}\n\nEVIDENCE\n{proposal.evidence_summary}\n\nSOURCES\n{citations}\n\nUse this idea in Smart Book Setup?",
            parent=self)
        if approved:
            self._main_assistant_say(f"I added {proposal.topic} to Smart Book Setup for review. The existing content and production checks will decide whether it can make a full book.")

    def _trend_failed(self, detail: str) -> None:
        self.trend_button.configure(state="normal")
        self.trend_status.set("Trend research needs attention. Your existing local tools are unchanged.")
        messagebox.showwarning("Could not research a niche", detail, parent=self)

    def _apply_main_assistant_appearance(self) -> None:
        if not hasattr(self, "main_assistant_chat"):
            return
        dark = self.dark_mode.get()
        if self.ui_theme.get() == "Neon Code Rain":
            colors = ("#020a05", "#baffc3", "#00a83f")
        else:
            colors = ("#212121" if dark else "#ffffff", "#ececec" if dark else "#203d4c", "#10a37f")
        self.main_assistant_chat.configure(background=colors[0], foreground=colors[1], insertbackground=colors[1], selectbackground=colors[2], selectforeground="#ffffff")
        assistant_fill = "#292929" if dark else "#f5f5f5"
        user_fill = "#303030" if dark else "#e6f3ef"
        self.main_assistant_chat.tag_configure("assistant_label", foreground=colors[1], font=("Segoe UI", 8, "bold"), spacing1=14, lmargin1=10)
        self.main_assistant_chat.tag_configure("assistant_message", foreground=colors[1], background=assistant_fill, lmargin1=10, lmargin2=10, rmargin=120, spacing3=12, spacing1=4)
        self.main_assistant_chat.tag_configure("user_label", foreground="#bfbfbf" if dark else "#555555", font=("Segoe UI", 8, "bold"), justify="right", lmargin1=140, lmargin2=140, rmargin=10, spacing1=12)
        self.main_assistant_chat.tag_configure("user_message", foreground=colors[1], background=user_fill, justify="right", lmargin1=140, lmargin2=140, rmargin=10, spacing3=11)

    def _refresh_home_next_action(self) -> None:
        """Read the existing catalog in the background and show one next step."""
        if not hasattr(self, "home_next_text"):
            return
        def work() -> None:
            try:
                from publishing import PublishingService
                from publishing.ease_of_use import home_summary
                result = home_summary(PublishingService(APP_DIR).db.list_books())
            except Exception:
                result = {"next": {"kind": "create", "book_id": "", "label": "Create a new book", "detail": "Start with a checked topic and the studio will apply the best defaults."}}
            self.after(0, lambda: self._show_home_next_action(result["next"]))
        threading.Thread(target=work, daemon=True).start()

    def _show_home_next_action(self, action: dict) -> None:
        if not hasattr(self, "home_next_text"):
            return
        self.home_next_action = {key: str(value) for key, value in action.items()}
        self.home_next_text.set(f"{action.get('label', 'Create a new book')} — {action.get('detail', '')}")
        self.home_next_button.configure(text="Create New Book" if action.get("kind") == "create" else "Open Book Control Center")

    def _run_home_next_action(self) -> None:
        action = getattr(self, "home_next_action", {})
        if action.get("kind") == "create" or not action.get("book_id"):
            self._open_create_new_book()
            return
        self._open_book_control_center(str(action.get("book_id") or ""))

    def _open_book_control_center(self, book_id: str) -> None:
        """Open the existing book-level hub, not a second copy of its data."""
        try:
            from publishing import PublishingService
            from publishing.ui import BookPublishingDialog
            service = PublishingService(APP_DIR)
            book = service.db.get_book(book_id)
            if not book:
                self._open_publishing_manager(open_dashboard=True)
                return
            BookPublishingDialog(self, service, book, self._refresh_home_next_action)
        except Exception as exc:
            log_plain_error("Book Control Center", "", exc, "Open Publishing Center and select the book again. Your files were not changed.")
            messagebox.showerror("Book Control Center problem", str(exc), parent=self)

    def _main_assistant_say(self, message: str) -> None:
        self.main_assistant_chat.configure(state="normal")
        self.main_assistant_chat.insert("end", "\nSlade Puzzles\n", "assistant_label")
        self.main_assistant_chat.insert("end", f"{message}\n", "assistant_message")
        self.main_assistant_chat.see("end")
        self.main_assistant_chat.configure(state="disabled")

    def _use_main_assistant_example(self, prompt: str) -> None:
        self.main_assistant_prompt.set(prompt)
        self._main_assistant_send()

    def _reset_main_assistant(self) -> None:
        if not hasattr(self, "main_assistant_chat"):
            return
        self.main_assistant_chat.configure(state="normal"); self.main_assistant_chat.delete("1.0", "end"); self.main_assistant_chat.configure(state="disabled")
        self.main_assistant_theme = None
        self._main_assistant_say("Fresh start. What would you like to make today?")

    def _main_assistant_send(self) -> None:
        request = self.main_assistant_prompt.get().strip()
        if not request:
            return
        self.main_assistant_prompt.set("")
        self.main_assistant_chat.configure(state="normal")
        self.main_assistant_chat.insert("end", "\nYou\n", "user_label")
        self.main_assistant_chat.insert("end", f"{request}\n", "user_message")
        self.main_assistant_chat.configure(state="disabled")
        words = request.casefold()
        if self._run_assistant_window_command(words):
            return
        if any(term in words for term in ("mixed", "brain games", "variety puzzle", "variety book", "puzzle collection", "multiple puzzle")):
            self._main_assistant_say("Opening Mixed Brain Games with its section dividers and separate answer keys ready to go.")
            self._open_other_puzzle_studio("Mixed Brain Games"); return
        if any(term in words for term in ("space cryptogram", "space cipher", "astronomy cryptogram", "celestial cipher")):
            self._main_assistant_say("Opening the Space & Astronomy Cryptogram Signature Edition: 100 checked, no-duplicate code-breaking puzzles with a matching space cover direction.")
            self._open_other_puzzle_studio("Cryptogram", "Space & Astronomy", "Signature Edition"); return
        if any(term in words for term in ("general knowledge trivia", "curiosity trivia", "trivia book", "curiosity cabinet")):
            self._main_assistant_say("Opening the General Knowledge & Curiosity Signature Edition: 100 checked scramble-and-trivia challenges with a matching playful cover direction.")
            self._open_other_puzzle_studio("Word Scramble + Trivia", "General Knowledge & Curiosity", "Signature Edition"); return
        for terms, kind, reply in (
            (("sudoku", "number puzzle", "letter sudoku", "shape sudoku"), "Sudoku", "Opening the 100-puzzle Sudoku Signature Edition with the number, letter, and shape mix already included."),
            (("cryptogram", "cipher", "code breaking", "codebreak"), "Cryptogram", "Opening Cryptograms. The studio will use the checked content library and stop if there are not enough unique games."),
            (("scramble", "trivia", "quick facts"), "Word Scramble + Trivia", "Opening Scramble + Trivia with its verified content check."),
        ):
            if any(term in words for term in terms):
                self._main_assistant_say(reply); self._open_other_puzzle_studio(kind, "General Starter", "Signature Edition" if kind == "Sudoku" else "Standard"); return
        chosen = self._find_main_assistant_theme(words)
        if chosen:
            self.main_assistant_theme = chosen
            self._set_theme(chosen)
            if not self.workspace.winfo_ismapped():
                self._toggle_word_search_workspace()
            self._main_assistant_say(f"I found a matching Word Search theme: {self.book_title.get()}. I applied its recommended title, cover direction, picture, and book settings. You can now use “Preview cover,” “Show cover options,” or “Create package.”")
            return
        if any(term in words for term in ("cover", "preview", "package", "create book", "build it")) and self.main_assistant_theme:
            self._main_assistant_say("I’m opening cover directions so you can select a look before creating the final package.")
            self._open_cover_choices(); return
        try:
            from publishing.commercial_profiles import idea_commercial_guidance, render_idea_guidance
            guidance = render_idea_guidance(idea_commercial_guidance(request))
            self._main_assistant_say(guidance + "\n\nI did not create anything. Add a specific topic or name a saved theme when you want me to route this into the checked creation workflow.")
        except Exception:
            self._main_assistant_say("I couldn’t confidently match that request yet. Try a topic such as space, gardening, travel, Christmas, national parks, pets, cars, or school vocabulary—or name a puzzle type.")

    def _assistant_window_commands(self) -> tuple[dict[str, object], ...]:
        """Safe, everyday-language routes to the app's main user-facing windows."""
        return (
            {"label": "Production dashboard", "say": "Opening Production Dashboard. It shows locally ready books and the best next step.", "phrases": ("production dashboard", "what is ready", "what's ready", "ready to make", "what should i make next", "next book"), "action": self._open_production_dashboard},
            {"label": "Check / fix a book", "say": "Opening Book Readiness. It checks whether your exact idea has enough reviewed content before a book is created and explains what needs attention.", "phrases": ("what can i make now", "book readiness", "check availability", "check content", "what needs attention", "check my book", "check a book", "fix my book", "check fix"), "action": self._open_book_readiness},
            {"label": "Production History", "say": "Opening Production History. You can inspect or safely reload an approved version there.", "phrases": ("production history", "book history", "approved versions", "reload version"), "action": self._open_production_history},
            {"label": "Prepare / publish a package", "say": "Opening Publishing Center, where you can prepare marketplace files and manage saved books.", "phrases": ("publishing center", "publishing manager", "open publishing", "marketplace manager", "prepare my package", "prepare package", "publish my package", "prepare publish"), "action": self._open_publishing_manager},
            {"label": "Create New Book", "say": "Opening Create New Book. Choose a type and topic, then the studio will apply the checked defaults.", "phrases": ("create new book", "start a new book", "new book", "make a book"), "action": self._open_create_new_book},
            {"label": "Guided Word Search", "say": "Opening the detailed Guided Word Search Builder.", "phrases": ("guided book builder", "guided word search", "word search builder"), "action": self._open_guided_book_builder},
            {"label": "Word Search workspace", "say": "Opening the Word Search workspace and your saved themes.", "phrases": ("word search workspace", "word search library", "open themes", "theme library"), "action": self._show_word_search_workspace},
            {"label": "Sudoku creator", "say": "Opening Sudoku with the checked starter settings ready.", "phrases": ("open sudoku", "sudoku creator", "sudoku studio"), "action": lambda: self._open_other_puzzle_studio("Sudoku")},
            {"label": "Cryptogram creator", "say": "Opening Cryptograms with the checked starter settings ready.", "phrases": ("open cryptogram", "cryptogram creator", "cryptogram studio"), "action": lambda: self._open_other_puzzle_studio("Cryptogram")},
            {"label": "Scramble + Trivia creator", "say": "Opening Scramble + Trivia with the checked starter settings ready.", "phrases": ("open scramble", "scramble creator", "trivia creator", "open trivia"), "action": lambda: self._open_other_puzzle_studio("Word Scramble + Trivia")},
            {"label": "Mixed Brain Games creator", "say": "Opening Mixed Brain Games with its themed section dividers.", "phrases": ("open mixed games", "mixed games creator", "mixed puzzle creator"), "action": lambda: self._open_other_puzzle_studio("Mixed Brain Games")},
            {"label": "Theme Builder", "say": "Opening Theme Builder to make or edit a Word Search theme.", "phrases": ("theme builder", "edit a theme", "make a theme"), "action": self._open_theme_builder},
            {"label": "Topic Pack Builder", "say": "Opening Topic Pack Builder to start a book from a checked topic pool.", "phrases": ("topic pack builder", "build from topic", "topic pack"), "action": self._open_topic_pack_builder},
            {"label": "Book Blueprint", "say": "Opening Book Blueprint for a more detailed book plan.", "phrases": ("book blueprint", "advanced book plan", "detailed book plan"), "action": self._open_book_blueprint},
            {"label": "Batch Generator", "say": "Opening Batch Generator. Review the listed books carefully before starting a batch.", "phrases": ("batch generator", "batch books", "create a batch"), "action": self._open_batch_generator},
            {"label": "Proofing Center", "say": "Opening Proofing Center so you can review the book before sharing or uploading it.", "phrases": ("proofing center", "open proofing", "quality check", "book proof"), "action": self._open_proofing_center},
            {"label": "Publish-ready review", "say": "Opening the exact publish-ready review for the selected Word Search.", "phrases": ("publish ready", "kdp check", "upload check"), "action": self._open_publish_ready_dashboard},
            {"label": "Book ideas dashboard", "say": "Opening the book ideas dashboard with the strongest ready themes.", "phrases": ("book ideas", "theme dashboard", "choose my next book", "next theme"), "action": self._open_theme_dashboard},
            {"label": "Word Library health", "say": "Opening Word Library health so you can see which topics are ready to use.", "phrases": ("word library", "library health", "word bank health", "content capacity"), "action": self._open_word_bank_health},
            {"label": "Word Intelligence", "say": "Opening Word Intelligence for topic connections and word-library details.", "phrases": ("word intelligence", "word connections", "topic connections"), "action": self._open_word_intelligence},
            {"label": "Niche research", "say": "Opening Niche Research for topic ideas and research notes.", "phrases": ("niche research", "research ideas", "market research"), "action": self._open_niche_research},
            {"label": "Series Builder", "say": "Opening Series Builder to plan connected books together.", "phrases": ("series builder", "open series", "plan a series"), "action": self._open_series_builder},
            {"label": "Series expansion", "say": "Opening Series Expansion to plan the next related book.", "phrases": ("series expansion", "next in series", "expand series"), "action": self._open_series_expansion},
            {"label": "Production queue", "say": "Opening your Production Queue.", "phrases": ("production queue", "open queue", "approved queue"), "action": self._open_production_queue},
            {"label": "My Books dashboard", "say": "Opening My Books dashboard to view your existing releases.", "phrases": ("my books dashboard", "release manager", "my releases"), "action": self._open_release_manager},
            {"label": "Review / approve a cover", "say": "Opening your cover directions so you can review and choose a look before creating a book.", "phrases": ("review my cover", "review cover", "approve cover", "cover gallery", "cover ideas", "compare covers", "cover options", "show cover options"), "action": self._open_cover_choices},
            {"label": "Cover Creator", "say": "Opening Cover Creator for a focused cover design session.", "phrases": ("cover creator", "design a cover", "make a cover"), "action": self._open_cover_creator},
            {"label": "Market Pulse", "say": "Opening Market Pulse for your saved niche research and release planning.", "phrases": ("market pulse", "market tracker", "trend tracker"), "action": self._open_market_pulse},
            {"label": "Saved packages", "say": "Opening your saved book packages.", "phrases": ("saved packages", "open packages", "open output folder", "my finished books"), "action": self._open_output_folder},
            {"label": "Help", "say": "Opening Help & explanations.", "phrases": ("open help", "help center", "what does this do"), "action": self._open_help_center},
            {"label": "Error log", "say": "Opening Error Log so you can see any plain-English fix notes.", "phrases": ("error log", "show errors", "open errors"), "action": self._open_error_log},
        )

    def _run_assistant_window_command(self, words: str) -> bool:
        if any(phrase in words for phrase in ("show commands", "show windows", "what can you open", "open command list", "help with commands")):
            self._main_assistant_say("Opening the command guide. You can choose a window there, or simply ask in everyday words.")
            self._open_assistant_commands()
            return True
        for command in self._assistant_window_commands():
            if any(phrase in words for phrase in command["phrases"]):
                self._main_assistant_say(str(command["say"]))
                command["action"]()
                return True
        return False

    def _open_assistant_commands(self) -> None:
        """A browseable, no-memory-required guide to the Book Assistant's windows."""
        dialog = tk.Toplevel(self)
        dialog.title("Book Assistant command guide")
        dialog.geometry("820x610")
        dialog.minsize(680, 460)
        dialog.configure(background="#171d22")
        dialog.transient(self)
        try:
            dialog.state("zoomed")
        except tk.TclError:
            pass
        root = ttk.Frame(dialog, padding=24, style="Chat.Main.TFrame")
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=1)
        ttk.Label(root, text="Ask the Book Assistant to open a tool", style="Chat.HeaderTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(root, text="Pick a tool below, or type one of the example phrases in the Book Assistant. Every option opens the same screen as the normal buttons—nothing is created until you review and approve it.", style="Chat.HeaderText.TLabel", wraplength=740).grid(row=1, column=0, sticky="w", pady=(5, 16))
        tree = ttk.Treeview(root, columns=("tool", "say"), show="headings", selectmode="browse", style="Theme.Treeview")
        tree.heading("tool", text="Open this")
        tree.heading("say", text="Try saying or typing")
        tree.column("tool", width=260, anchor="w")
        tree.column("say", width=500, anchor="w")
        tree.grid(row=2, column=0, sticky="nsew")
        commands = self._assistant_window_commands()
        command_by_id: dict[str, dict[str, object]] = {}
        for index, command in enumerate(commands):
            item_id = f"command_{index}"
            command_by_id[item_id] = command
            examples = ", ".join(f'“{phrase}”' for phrase in command["phrases"][:2])
            tree.insert("", "end", iid=item_id, values=(command["label"], examples))
        actions = ttk.Frame(root, style="Chat.Main.TFrame")
        actions.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        def open_selected() -> None:
            selected = tree.selection()
            if not selected:
                messagebox.showinfo("Choose a tool", "Choose a tool first.", parent=dialog)
                return
            command = command_by_id[selected[0]]
            dialog.destroy()
            self._main_assistant_say(str(command["say"]))
            command["action"]()
        ttk.Button(actions, text="Open selected tool", command=open_selected, style="Chat.Start.TButton").pack(side="left")
        ttk.Button(actions, text="Close", command=dialog.destroy, style="Chat.Quick.TButton").pack(side="right")
        tree.bind("<Double-1>", lambda _event: open_selected())

    def _find_main_assistant_theme(self, request: str) -> Path | None:
        generic = {"make", "create", "book", "puzzle", "word", "search", "the", "a", "an", "for", "with", "want", "i", "about", "colorful"}
        wanted = {item for item in re.findall(r"[a-z0-9]+", request) if item not in generic and len(item) > 2}
        candidates = []
        for label, path in getattr(self, "theme_paths", {}).items():
            score = sum(token in f"{label} {path.stem}".casefold() for token in wanted)
            if score:
                candidates.append((score, len(label), path))
        return max(candidates, key=lambda item: (item[0], -item[1]))[2] if candidates else None

    def _open_output_folder(self) -> None:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        os.startfile(OUTPUT_DIR)

    def _open_recent_package(self) -> None:
        """Open the latest completed package without making the user hunt in out."""
        candidates: list[Path] = []
        if self.last_output and self.last_output.exists():
            candidates.append(self.last_output.parent.parent if self.last_output.parent.name == "01_PRINT_UPLOADS" else self.last_output)
        try:
            history = json.loads(PRODUCTION_HISTORY_FILE.read_text(encoding="utf-8-sig"))
            for record in history if isinstance(history, list) else []:
                if isinstance(record, dict) and record.get("package"):
                    path = Path(str(record["package"]))
                    if path.is_dir(): candidates.append(path)
        except (OSError, json.JSONDecodeError):
            pass
        if candidates:
            os.startfile(max(candidates, key=lambda path: path.stat().st_mtime))
            self.status.set("Opened your most recent completed package.")
        else:
            messagebox.showinfo("No completed package yet", "Your output area is clean right now. Create and approve a book package first; it will appear here automatically.", parent=self)

    def _toggle_word_search_workspace(self) -> None:
        if self.workspace.winfo_ismapped():
            self.workspace.grid_remove()
            self.home_view.grid()
            self._content_outer.rowconfigure(1, weight=1)
            self._content_outer.rowconfigure(2, weight=0)
            self._set_workspace_scrolling(False)
            self.status_label.grid_remove()
            self._sync_content_window_height()
            self.workspace_button.configure(text="Word Search workspace")
            self.status.set("Word Search workspace tucked away. Start with the Book Assistant whenever you want.")
        else:
            self.home_view.grid_remove()
            self.workspace.grid()
            self._content_outer.rowconfigure(1, weight=0)
            self._content_outer.rowconfigure(2, weight=1)
            self._set_workspace_scrolling(True)
            self.status_label.grid()
            self._sync_content_window_height()
            # Grid geometry is not final until Tk returns to idle. Recalculate
            # then as well, otherwise the scrollbar can keep the old home-only
            # range and the entire production workspace becomes unreachable.
            self.after_idle(self._refresh_content_scrollbar)
            self.after(80, self._refresh_content_scrollbar)
            self.workspace_button.configure(text="Hide Word Search workspace")
            self.status.set("Word Search workspace open — choose a saved theme or start a new book.")

    def _show_word_search_workspace(self) -> None:
        """Open the detailed Word Search workspace without accidentally hiding it."""
        if not self.workspace.winfo_ismapped():
            self._toggle_word_search_workspace()
        else:
            self.status.set("Word Search workspace is already open. Choose a saved theme or start a new book.")

    def _set_workspace_scrolling(self, enabled: bool) -> None:
        """Keep the home clean, but never hide overflow behind the taskbar."""
        if not hasattr(self, "_content_scrollbar"):
            return
        self._workspace_scroll_requested = enabled
        if not enabled:
            self._content_canvas.yview_moveto(0)
        self._refresh_content_scrollbar()

    def _refresh_content_scrollbar(self, _event=None) -> None:
        """Show the Studio scrollbar whenever either view is taller than the window."""
        if not hasattr(self, "_content_canvas") or not self._content_canvas.winfo_exists():
            return
        self._content_canvas.configure(scrollregion=self._content_canvas.bbox("all"))
        bbox = self._content_canvas.bbox("all")
        overflow = bool(bbox and (bbox[3] - bbox[1]) > self._content_canvas.winfo_height() + 2)
        if overflow or getattr(self, "_workspace_scroll_requested", False):
            self._content_scrollbar.grid()
        else:
            self._content_scrollbar.grid_remove()

    def _resize_content_window(self, event) -> None:
        """Fill the screen in chat mode; preserve natural height for the detailed workspace."""
        options = {"width": event.width, "height": event.height}
        if hasattr(self, "workspace") and not self.workspace.winfo_ismapped():
            requested = self._content_outer.winfo_reqheight() if hasattr(self, "_content_outer") else 0
            options["height"] = max(event.height, requested)
        elif hasattr(self, "_content_outer"):
            self._content_outer.update_idletasks()
            options["height"] = max(event.height, self._content_outer.winfo_reqheight())
        self._content_canvas.itemconfigure(self._content_window, **options)
        self._refresh_content_scrollbar()

    def _sync_content_window_height(self) -> None:
        if not hasattr(self, "_content_canvas") or not self._content_canvas.winfo_exists():
            return
        if self.workspace.winfo_ismapped():
            self._content_outer.update_idletasks()
            height = max(self._content_canvas.winfo_height(), self._content_outer.winfo_reqheight())
        else:
            height = self._content_canvas.winfo_height()
        self._content_canvas.itemconfigure(self._content_window, width=self._content_canvas.winfo_width(), height=height)

    @staticmethod
    def _studio_field(parent: ttk.Widget, row: int, label: str, variable: tk.StringVar) -> None:
        label_widget = ttk.Label(parent, text=label); label_widget.grid(row=row, column=0, sticky="w", pady=5)
        explanations = {
            "Puzzle pattern": "This is only the random letter arrangement. Keep it the same for the same pages; change it to create a fresh grid layout.",
            "Inside-pages file": "The name of the interior PDF file the app will create. The app adds .pdf for you.",
            "Cover callout": "A short promise on the front cover, such as ‘48 LARGE-PRINT PUZZLES’ or ‘NO REPEATED WORDS’.",
            "Back-cover name": "The small publisher or brand name printed on the back cover. Slade Puzzles is a good default.",
        }
        if label in explanations:
            add_hover_help(label_widget, explanations[label])
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=(10, 0), pady=5)

    def _scroll_studio(self, event) -> None:
        if hasattr(self, "_content_canvas") and self._content_canvas.winfo_exists() and getattr(self, "workspace", None) and self.workspace.winfo_ismapped():
            # Modern touchpads and automation drivers often send deltas smaller
            # than 120; int(delta / 120) turned those real scrolls into zero.
            direction = -1 if event.delta > 0 else 1
            self._content_canvas.yview_scroll(direction * 4, "units")
            return "break"

    def _entry(self, parent: ttk.Frame, row: int, label: str, variable: tk.StringVar, hint: str = "") -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=6)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, columnspan=2, sticky="ew", padx=(12, 0), pady=6)
        if hint:
            ttk.Label(parent, text=hint, foreground="#666666", font=("Segoe UI", 8)).grid(
                row=row, column=1, columnspan=2, sticky="w", padx=(14, 0), pady=(29, 0)
            )

    def _load_theme_list(self) -> None:
        # A full Smart Theme Scan touches every JSON file and can make a large
        # library appear frozen on startup.  It remains available on demand in
        # Safety & Settings; loading the library should stay instant.
        themes = saved_theme_files()
        self.theme_paths: dict[str, Path] = {}
        self.theme_groups: dict[str, str] = {}
        for path in themes:
            theme_data: dict = {}
            try:
                theme_data = json.loads(path.read_text(encoding="utf-8-sig"))
                if not isinstance(theme_data.get("puzzles"), list):
                    continue
                title = str(theme_data.get("title") or path.stem.replace("_", " "))
            except (OSError, json.JSONDecodeError):
                title = path.stem.replace("_", " ")
            decade = re.match(r"^(19[5-9]0s|2000s)_", path.stem)
            if decade and "_Men_" in path.stem:
                label = f"{decade.group(1)} — Men"
            elif decade and "_Women_" in path.stem:
                label = f"{decade.group(1)} — Women"
            elif decade:
                label = f"{decade.group(1)} — General"
            else:
                label = title
            puzzle_count = len(theme_data.get("puzzles", []))
            word_counts = sorted({len(puzzle.get("words", [])) for puzzle in theme_data.get("puzzles", []) if isinstance(puzzle, dict)})
            word_label = f"{word_counts[0]} words" if len(word_counts) == 1 else (f"{word_counts[0]}–{word_counts[-1]} words" if word_counts else "word count unknown")
            ready, ready_label = quick_theme_readiness(theme_data)
            # This browser is navigation, not the production gate. Running the
            # full publisher safety report for hundreds of themes used to lock
            # the Tk event loop during launch. The exact Check / Fix and package
            # routes still run the complete reviewed-content/topic-fit gates.
            if ready:
                ready_label = "Production-ready"
            marker = "✓" if ready else "!"
            label = f"{marker} {label}  •  {puzzle_count} puzzles  •  {word_label}  •  {ready_label}"
            if label in self.theme_paths:
                label = f"{title}  ({path.stem})"
            self.theme_paths[label] = path
            try:
                relative_parent = path.parent.relative_to(THEMES_DIR)
                folder_group = " / ".join(relative_parent.parts) if relative_parent.parts else "Unfiled Themes"
            except ValueError:
                folder_group = "Unfiled Themes"
            series = str(theme_data.get("series") or "").strip()
            self.theme_groups[label] = f"Series • {series}" if series else folder_group
        self._refresh_recent_themes()
        preferred = next((path for path in self.theme_paths.values() if path.stem == "90s_nostalgia"), themes[0] if themes else None)
        if preferred:
            self._set_theme(preferred)
        else:
            self.status.set("No theme files were found in the themes folder.")

    def _refresh_theme_library(self, *_args: object) -> None:
        if not hasattr(self, "theme_tree"):
            return
        selected = self.selected_theme
        query = self.theme_filter.get().strip().lower()
        self.theme_tree.delete(*self.theme_tree.get_children())
        grouped: dict[str, list[str]] = {}
        for label, path in self.theme_paths.items():
            group = self.theme_groups.get(label, "Unfiled Themes")
            haystack = f"{label} {group}".lower()
            if query and query not in haystack:
                continue
            grouped.setdefault(group, []).append(label)
        self.visible_theme_paths: dict[str, Path] = {}
        selected_iid = ""
        for group_index, (group, labels) in enumerate(sorted(grouped.items(), key=lambda item: item[0].casefold())):
            group_iid = f"group_{group_index}"
            self.theme_tree.insert("", "end", iid=group_iid, text=f"{group}  ({len(labels)})", open=True, tags=("group",))
            for book_index, label in enumerate(sorted(labels, key=str.casefold)):
                book_iid = f"book_{group_index}_{book_index}"
                path = self.theme_paths[label]
                self.visible_theme_paths[book_iid] = path
                self.theme_tree.insert(group_iid, "end", iid=book_iid, text=label)
                if path == selected:
                    selected_iid = book_iid
        self.theme_tree.tag_configure("group", font=("Segoe UI", 10, "bold"))
        if selected_iid:
            self.theme_tree.selection_set(selected_iid)
            self.theme_tree.see(selected_iid)

    def _theme_changed(self, _event: object = None) -> None:
        if not hasattr(self, "theme_tree"):
            return
        selection = self.theme_tree.selection()
        path = self.visible_theme_paths.get(selection[0]) if selection else None
        # Rebuilding the tree reselects the current book.  Do not reload that
        # same book again, otherwise Tk can repeatedly fire selection events.
        if path and path != self.selected_theme:
            self._set_theme(path)

    def _refresh_recent_themes(self) -> None:
        """Keep the shortcut list friendly, current, and independent of search."""
        if not hasattr(self, "recent_picker"):
            return
        self.recent_theme_paths: dict[str, Path] = {}
        for path in load_recent_theme_paths():
            if path not in self.theme_paths.values():
                continue
            label = next((name for name, item in self.theme_paths.items() if item == path), path.stem)
            if label in self.recent_theme_paths:
                label = f"{label}  ({path.stem})"
            self.recent_theme_paths[label] = path
        values = list(self.recent_theme_paths)
        self.recent_picker.configure(values=values)
        current_label = next((label for label, path in self.recent_theme_paths.items() if path == self.selected_theme), "")
        self.recent_theme.set(current_label)

    def _recent_theme_changed(self, _event: object = None) -> None:
        path = getattr(self, "recent_theme_paths", {}).get(self.recent_theme.get())
        if path:
            self._set_theme(path)

    def _update_favorite_button(self) -> None:
        if not hasattr(self, "favorite_button"):
            return
        favorites = load_favorite_theme_paths()
        is_favorite = self.selected_theme in favorites if self.selected_theme else False
        self.favorite_button.configure(text="★ Remove Current Theme from Favorites" if is_favorite else "☆ Add Current Theme to Favorites")

    def _toggle_current_favorite(self) -> None:
        if not self.selected_theme:
            messagebox.showinfo("Choose a theme", "Choose a theme first, then add it to Favorites.", parent=self)
            return
        is_favorite = toggle_favorite_theme(self.selected_theme)
        self._update_favorite_button()
        self.status.set(f"{'Saved' if is_favorite else 'Removed'} {self.book_title.get() or self.selected_theme.stem} {'to' if is_favorite else 'from'} Favorites.")

    def _choose_theme(self) -> None:
        selected = filedialog.askopenfilename(
            title="Choose a word-search theme file", initialdir=THEMES_DIR, filetypes=[("JSON theme files", "*.json")]
        )
        if selected:
            self._set_theme(Path(selected))

    def _set_theme(self, path: Path) -> None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            puzzle_count = len(data["puzzles"])
        except (OSError, json.JSONDecodeError, KeyError) as exc:
            messagebox.showerror("Cannot load theme", f"This does not look like a valid theme file.\n\n{exc}")
            return
        self.selected_theme = path
        self.theme_name.set(next((label for label, item in self.theme_paths.items() if item == path), path.stem))
        self.book_title.set(data.get("title", "Word Search"))
        self.subtitle.set(data.get("subtitle", ""))
        loaded_author = str(data.get("author") or "").strip()
        self.author.set("Jordan M. Slade" if not loaded_author or loaded_author == "Slade Puzzles" else loaded_author)
        # Legacy files may be named as Signature editions but contain fewer
        # than the new 100-puzzle premium standard.  Load them as standard
        # books; their data and artwork remain untouched.
        self.signature_edition.set(theme_defaults_to_signature(path, data) and len(data.get("puzzles", [])) >= SIGNATURE_PUZZLE_TARGET)
        self.output_name.set(f"{self._safe_filename(self.book_title.get())}.pdf")
        self.cover_palette.set(data.get("palette", "nature") if data.get("palette", "nature") in CoverCreatorDialog.PALETTES else "nature")
        style_label = next((label for label, value in PublishReadyDialog.STYLE_MAP.items() if value == data.get("cover_style")), None)
        if style_label: self.cover_style.set(style_label)
        self.cover_badge.set(str(data.get("cover_badge") or ("NO REPEATED WORDS" if data.get("no_repeat_words") else f"INCLUDES {puzzle_count} PUZZLES")))
        self.cover_imprint.set(self.author.get())
        format_label = book_format_label(data).replace("PUZZLES", "").title().strip()
        freshness, freshness_label = word_bank_freshness(data)
        difficulty = puzzle_difficulty_label(data)
        self.book_specs.set(f"Estimated interior: about {estimated_page_count(data)} pages • Format: {format_label} • Difficulty: {difficulty} • Word-bank freshness: {freshness}% ({freshness_label}).")
        preferences = load_cover_preferences(path)
        # A series gets a stable cover family by default, while an individual
        # book’s saved preferences still win if the publisher chose them.
        series = str(data.get("series") or "").strip()
        family = load_cover_memory(series) if series and not preferences else {}
        if family.get("palette") in CoverCreatorDialog.PALETTES:
            self.cover_palette.set(family["palette"])
        family_style = next((label for label, value in PublishReadyDialog.STYLE_MAP.items() if value == family.get("style")), None)
        if family_style:
            self.cover_style.set(family_style)
        if preferences.get("palette") in CoverCreatorDialog.PALETTES: self.cover_palette.set(preferences["palette"])
        saved_style = next((label for label, value in PublishReadyDialog.STYLE_MAP.items() if value == preferences.get("style")), None)
        if saved_style: self.cover_style.set(saved_style)
        if preferences.get("badge"): self.cover_badge.set(preferences["badge"])
        self.cover_imprint.set(self.author.get())
        saved_art = preferences.get("art") or str(data.get("cover_art_path") or "")
        saved_art_approved = BackgroundAssetIndex().ledger_details(Path(saved_art)) if saved_art and Path(saved_art).exists() else None
        if saved_art and Path(saved_art).exists() and saved_art_approved:
            self.cover_art.set(saved_art)
            focus, note = suggest_art_plan(Path(saved_art))
            self.cover_art_focus.set(preferences.get("art_focus") or str(data.get("cover_art_focus") or focus))
            _score, quality = art_quality_report(Path(saved_art))
            self.cover_art_note.set(f"{note} {quality} {art_use_note(Path(saved_art))}")
        else:
            if saved_art and Path(saved_art).exists():
                self.cover_art_note.set("A previous cover picture was retained as a reference only. Production covers now use approved project-generated backgrounds; the best approved match has been selected when available.")
            suggestion = recommend_background_photo(data)
            suggested_path = APP_DIR / str(suggestion.get("file") or "") if suggestion else None
            if suggested_path and suggested_path.exists():
                focus = str(suggestion.get("focus") or "center")
                self.cover_art.set(str(suggested_path)); self.cover_art_focus.set(focus)
                if not preferences and not family:
                    self.cover_palette.set(photo_choice_palette(suggestion, self.cover_palette.get()))
                matched_palette = photo_choice_palette(suggestion, self.cover_palette.get())
                self.cover_art_note.set(f"Suggested background photo: {suggestion.get('name', suggested_path.stem)}. Recommended colors: {matched_palette.replace('-', ' ').title()}. Photo Hero is ready; choose another layout anytime.")
                self.cover_style.set("Photo Hero")
            else:
                self.cover_art.set(""); self.cover_art_focus.set("center"); self.cover_art_note.set("Choose an OpenClipart image and I will suggest its crop focus automatically.")
        record_recent_theme(path)
        self._refresh_recent_themes()
        self._update_favorite_button()
        self._refresh_theme_library()
        self.status.set(f"Loaded {puzzle_count} puzzles from {path.name}.")

    @staticmethod
    def _safe_filename(name: str) -> str:
        cleaned = re.sub(r"[<>:\\/*?|\"]+", "", name).strip().replace(" ", "_")
        return cleaned or "word_search_book"

    def _confirm_unique_title(self) -> bool:
        """Warn before making a book whose title matches or is very close to another title."""
        title = self.book_title.get().strip().casefold()
        if not title:
            return True
        title_words = {word for word in re.findall(r"[a-z0-9]+", title) if len(word) > 2}
        for path in saved_theme_files():
            if path == self.selected_theme:
                continue
            try:
                other = json.loads(path.read_text(encoding="utf-8-sig"))
                other_title = str(other.get("title") or "").strip().casefold()
                other_words = {word for word in re.findall(r"[a-z0-9]+", other_title) if len(word) > 2}
                similarity = len(title_words & other_words) / max(1, len(title_words | other_words))
                if other_title == title or similarity >= 0.80:
                    detail = "uses this exact title" if other_title == title else f"has a very similar title ({similarity:.0%} of meaningful title words overlap)"
                    return messagebox.askyesno("Possible duplicate title", f"Another theme {detail}:\n\n{other.get('title') or path.name}\n\nChoose a more distinct title unless these are intentionally linked editions.", parent=self)
            except (OSError, json.JSONDecodeError):
                continue
        return True

    def _generate(self) -> None:
        if not self.selected_theme:
            messagebox.showwarning("Choose a theme", "Choose a theme file before generating a book.")
            return
        if not self._confirm_unique_title():
            self.status.set("Book creation paused so you can choose a distinct title.")
            return
        seed = self._automatic_seed()
        if seed is None:
            return
        errors, warnings, notes = quality_gate(self.selected_theme, seed)
        if errors:
            self.status.set("Book creation stopped: the no-repeat quality rule needs attention.")
            QualityReportDialog(self, "Book Quality Check", errors, warnings, notes)
            return
        filename = self._safe_filename(self.output_name.get())
        if not filename.lower().endswith(".pdf"):
            filename += ".pdf"
        self.last_output = OUTPUT_DIR / filename
        self.generate_button.configure(state="disabled")
        self.open_button.configure(state="disabled")
        self.status.set("Creating your PDF. This can take a moment…")
        threading.Thread(target=self._run_engine, args=(seed,), daemon=True).start()

    def _choose_cover_art(self) -> None:
        filename = filedialog.askopenfilename(title="Choose licensed hero artwork", filetypes=[("Image files", "*.png;*.jpg;*.jpeg;*.webp"), ("All files", "*.*")])
        if filename:
            self.cover_art.set(filename)
            focus, note = suggest_art_plan(Path(filename))
            self.cover_art_focus.set(focus); self.cover_art_note.set(note)
            self._match_art_colors(silent=True)

    def _open_saved_art_library(self) -> None:
        OpenClipartPickerDialog(self, "word search", self._apply_openclipart_asset).show_saved()

    def _check_art_quality(self) -> None:
        path = Path(self.cover_art.get()) if self.cover_art.get().strip() else None
        score, note = art_quality_report(path)
        messagebox.showinfo("Picture quality", f"Picture score: {score}/100\n\n{note}\n\nThe app will add a title panel and contrast protection automatically.", parent=self)

    def _match_art_colors(self, silent: bool = False) -> None:
        path = Path(self.cover_art.get()) if self.cover_art.get().strip() else None
        palette, note = nearest_cover_palette(path, self.cover_palette.get() or "nature")
        if palette in CoverCreatorDialog.PALETTES:
            self.cover_palette.set(palette)
        if not silent:
            self.cover_art_note.set(note)
            self.status.set(note)

    def _toggle_customize(self) -> None:
        if self.customize_visible.get():
            self.customize_frame.grid_remove()
            self.customize_visible.set(False)
            self.status.set("Optional settings hidden. Your automatic book plan is still active.")
        else:
            self.customize_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(16, 0))
            self.customize_visible.set(True)
            self.status.set("Optional settings are open. The automatic recommendations remain available.")

    def _update_book_automation(self) -> None:
        self._update_title_feedback()
        if self.book_title.get().strip():
            self.output_name.set(f"{self._safe_filename(self.book_title.get())}.pdf")

    def _automatic_seed(self) -> int | None:
        if self.auto_seed.get():
            value = random.SystemRandom().randint(100000, 999999999)
            self.seed.set(str(value))
            return value
        try:
            return int(self.seed.get())
        except ValueError:
            messagebox.showwarning("Puzzle pattern", "Puzzle pattern must be a whole number, or turn automatic pattern back on.", parent=self)
            return None

    def _update_layout_note(self) -> None:
        if hasattr(self, "cover_layout_note"):
            self.cover_layout_note.set(COVER_LAYOUT_GUIDANCE.get(self.cover_style.get(), "Choose a layout that keeps the title easy to read at thumbnail size."))
        if hasattr(self, "cover_plan"):
            picture = "uses your selected picture" if self.cover_art.get().strip() else "uses the theme’s built-in illustration"
            self.cover_plan.set(f"{self.cover_palette.get().replace('-', ' ').title()} colors • {self.cover_style.get()} layout • {picture}. The no-repeat puzzle callout and author name are added automatically.")

    def _update_title_feedback(self) -> None:
        length = len(self.book_title.get().strip())
        if length > 48: message = "Cover title warning: this is long. Use a short layout or shorten it for thumbnail readability."
        elif length > 38: message = "Cover title note: consider a short, bold layout for the clearest cover text."
        else: message = "Cover title: good length for readable thumbnail text." if length else ""
        self.cover_title_feedback.set(message)

    def _update_subtitle_feedback(self) -> None:
        length = len(self.subtitle.get().strip())
        if length > 78: message = "Subtitle suggestion: shorten this line for clearer cover text."
        elif length > 58: message = "Subtitle note: this will be small on a cover; keep the most important benefit first."
        else: message = "Subtitle: good cover length." if length else "Subtitle: optional—keep it short if you use one."
        self.subtitle_feedback.set(message)

    def _reset_cover_settings(self) -> None:
        if not self.selected_theme:
            return
        try:
            data = json.loads(self.selected_theme.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            messagebox.showerror("Could not reset cover", str(exc), parent=self); return
        puzzle_count = len(data.get("puzzles", []))
        self.cover_palette.set(data.get("recommended_palette") or data.get("palette") or "nature")
        style_value = data.get("recommended_cover_style") or data.get("cover_style") or "classic"
        label = next((item for item, value in PublishReadyDialog.STYLE_MAP.items() if value == style_value), "Classic")
        self.cover_style.set(label); self.cover_badge.set(f"INCLUDES {puzzle_count} PUZZLES"); self.cover_imprint.set(self.author.get() or "Jordan M. Slade"); self.cover_art.set(""); self.cover_art_focus.set("center"); self.cover_art_note.set("Choose an OpenClipart image and I will suggest its crop focus automatically.")
        self.status.set("Cover settings restored to this theme’s recommended starting point.")

    def _random_good_cover(self) -> None:
        if not self.selected_theme:
            return
        try:
            data = json.loads(self.selected_theme.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            messagebox.showerror("Could not choose cover", str(exc), parent=self); return
        palette, style = compatible_cover_choice(data, self.book_title.get().strip())
        self.cover_palette.set(palette); self.cover_style.set(style)
        self.status.set(f"Suggested a compatible cover: {palette.replace('-', ' ').title()} + {style}.")

    def _find_free_artwork(self) -> None:
        data: dict = {}
        if self.selected_theme:
            try:
                data = json.loads(self.selected_theme.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError):
                data = {}
        query = openclipart_query(data) if data else (self.book_title.get().strip() or self.theme_name.get().strip() or "word search")
        OpenClipartPickerDialog(self, query, self._apply_openclipart_asset)

    def _open_background_generator(self) -> None:
        topic = self.book_title.get().strip() or self.theme_name.get().strip() or "this puzzle topic"
        if self.selected_theme:
            try:
                data = json.loads(self.selected_theme.read_text(encoding="utf-8-sig"))
                topic = str(data.get("detected_topic") or data.get("topic") or data.get("series") or topic)
            except (OSError, json.JSONDecodeError):
                pass
        BackgroundGeneratorDialog(self, topic=topic, palette=self.cover_palette.get())

    def _apply_theme_background_photo(self) -> None:
        if not self.selected_theme:
            return
        try:
            data = json.loads(self.selected_theme.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            messagebox.showerror("Could not read theme", str(exc), parent=self); return
        suggestion = recommend_background_photo(data)
        path = APP_DIR / str(suggestion.get("file") or "") if suggestion else None
        if not suggestion or not path or not path.exists():
            messagebox.showinfo("No background match yet", "This theme does not have a matching stock photo yet. Choose a picture from your computer or use free CC0 artwork instead.", parent=self)
            return
        palette = photo_choice_palette(suggestion, self.cover_palette.get())
        self.cover_art.set(str(path)); self.cover_art_focus.set(str(suggestion.get("focus") or "center")); self.cover_palette.set(palette); self.cover_style.set("Photo Hero")
        self.cover_art_note.set(f"Applied photo background: {suggestion.get('name', path.stem)}. Matched {palette.replace('-', ' ').title()} colors; a faded puzzle grid will appear automatically.")
        self.status.set("Applied the suggested photo background, matching colors, and Photo Hero layout. Preview the cover before creating the package.")

    def _open_photo_choice_picker(self) -> None:
        if not self.selected_theme:
            messagebox.showwarning("Choose a theme", "Choose a theme first, then I can show the best matching cover backgrounds.", parent=self)
            return
        try:
            data = json.loads(self.selected_theme.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            messagebox.showerror("Could not read theme", str(exc), parent=self)
            return
        CoverPhotoPickerDialog(self, data)

    def _use_photo_choice(self, choice: dict[str, object]) -> None:
        path = APP_DIR / str(choice.get("file") or "")
        if not path.exists():
            messagebox.showerror("Picture unavailable", "That saved background is no longer available. Choose another one.", parent=self)
            return
        self.cover_art.set(str(path))
        self.cover_art_focus.set(str(choice.get("focus") or "center"))
        palette = photo_choice_palette(choice, self.cover_palette.get())
        self.cover_palette.set(palette)
        self.cover_style.set("Photo Hero")
        self.cover_art_note.set(f"Selected background: {choice.get('name', path.stem)}. Matched {palette.replace('-', ' ').title()} colors; a faded puzzle grid will appear automatically.")
        self.status.set("Cover background and matching colors selected. Use Review Before Creating to see the final book summary and cover preview.")

    def _apply_openclipart_asset(self, path: Path, record: dict[str, object]) -> None:
        focus, note = suggest_art_plan(path)
        score, quality_note = art_quality_report(path)
        palette, color_note = nearest_cover_palette(path, self.cover_palette.get() or "nature")
        self.cover_art.set(str(path)); self.cover_art_focus.set(focus); self.cover_art_note.set(f"{note} {quality_note} {color_note} {art_use_note(path)}")
        self.cover_style.set("Photo Hero")
        if palette in CoverCreatorDialog.PALETTES:
            self.cover_palette.set(palette)
        if self.selected_theme:
            try:
                data = json.loads(self.selected_theme.read_text(encoding="utf-8-sig"))
                data["cover_art_source"] = record
                data["cover_art_path"] = str(path)
                data["cover_art_focus"] = focus
                self.selected_theme.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            except (OSError, json.JSONDecodeError):
                pass
        self.status.set(f"OpenClipart saved: {record.get('title', path.name)}. Applied Photo Hero, matched colors, and {focus} focus (picture score {score}/100).")

    def _edit_back_cover_blurb(self) -> None:
        if not self.selected_theme: return
        data = json.loads(self.selected_theme.read_text(encoding="utf-8-sig")); current = str(data.get("back_cover_blurb") or book_description(len(data.get("puzzles", [])), data))
        value = simpledialog.askstring("Back-Cover Blurb", "Edit the back-cover description:", initialvalue=current, parent=self)
        if value is None: return
        automatic_theme_backup("editing a back-cover blurb")
        data["back_cover_blurb"] = value.strip(); self.selected_theme.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"); self.status.set("Saved the custom back-cover blurb for this theme.")

    def _preview_studio_cover(self) -> None:
        settings = self._studio_cover_settings()
        if not settings:
            return
        output = OUTPUT_DIR / "cover_preview_safe_guide.png"
        self.status.set("Creating a quick cover preview…")
        threading.Thread(target=self._run_studio_preview, args=(settings, output), daemon=True).start()

    def _preview_this_topic(self) -> None:
        """One-click topic preview: use the recommended local picture if needed."""
        if self.selected_theme and not self.cover_art.get().strip():
            self._apply_theme_background_photo()
        self._preview_studio_cover()

    def _generate_reader_preview(self) -> None:
        if not self.selected_theme: messagebox.showwarning("Choose a theme", "Choose a theme first.", parent=self); return
        seed = self._automatic_seed()
        if seed is None:
            return
        folder = OUTPUT_DIR / "reader_previews"; folder.mkdir(parents=True, exist_ok=True)
        output = folder / f"{self._safe_filename(self.book_title.get() or self.selected_theme.stem)}_3_puzzle_preview.pdf"
        self.status.set("Creating a three-puzzle reader preview…")
        def run() -> None:
            python = WINDOWS_VENV_PYTHON if WINDOWS_VENV_PYTHON.exists() else Path(sys.executable)
            result = subprocess.run([str(python), str(ENGINE), "--themes", str(self.selected_theme), "--out", str(output), "--title", self.book_title.get().strip(), "--subtitle", self.subtitle.get().strip(), "--author", self.author.get().strip() or "Jordan M. Slade", "--seed", str(seed), "--preview-puzzles", "3"], cwd=APP_DIR, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode: self.after(0, lambda: messagebox.showerror("Preview problem", result.stderr or result.stdout, parent=self)); return
            self.after(0, lambda: (self.status.set("Reader preview ready: first three puzzles plus solutions."), os.startfile(output)))
        threading.Thread(target=run, daemon=True).start()

    def _run_studio_preview(self, settings: dict[str, str], output: Path) -> None:
        python = WINDOWS_VENV_PYTHON if WINDOWS_VENV_PYTHON.exists() else Path(sys.executable)
        command = [str(python), str(COVER_ENGINE), "--title", settings["title"], "--subtitle", settings["subtitle"], "--author", settings["author"], "--badge", settings["badge"], "--puzzle-count", str(settings.get("puzzle_count", 0)), "--difficulty", settings["difficulty"], "--format-label", settings.get("format_label", "WORD SEARCH"), "--palette", settings["palette"], "--style", settings["style"], "--theme-file", settings["theme"], "--out", str(output), "--preview"]
        if settings["art"]:
            command.extend(["--art", settings["art"], "--art-focus", settings.get("art_focus", "center")])
        try:
            result = subprocess.run(command, cwd=APP_DIR, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode:
                raise RuntimeError(result.stderr.strip() or result.stdout.strip())
            self.after(0, self._show_studio_preview, output)
        except Exception as exc:
            log_plain_error("Cover preview", settings.get("title", ""), exc, "Check the chosen cover art and try a different cover layout.")
            self.after(0, lambda: messagebox.showerror("Cover preview problem", str(exc), parent=self))

    def _show_studio_preview(self, output: Path) -> None:
        self.status.set("Preview ready. Keep title and badge inside the dashed guide.")
        SafeCoverPreview(self, output)

    def _studio_cover_settings(self) -> dict[str, str] | None:
        if not self.selected_theme or not self.book_title.get().strip():
            messagebox.showwarning("Book details", "Choose a theme and add a title first.")
            return None
        style = PublishReadyDialog.STYLE_MAP[self.cover_style.get()]
        art = Path(self.cover_art.get()) if self.cover_art.get().strip() else None
        difficulty = "Standard"
        theme_data: dict = {}
        try:
            theme_data = json.loads(self.selected_theme.read_text(encoding="utf-8-sig"))
            difficulty = puzzle_difficulty_label(theme_data)
        except (OSError, json.JSONDecodeError):
            pass
        if style == "photo" and (not art or not art.exists()):
            choice = recommend_background_photo(theme_data)
            if choice:
                art = APP_DIR / str(choice["file"])
                self.cover_art.set(str(art))
                self.cover_art_focus.set(str(choice.get("focus") or "center"))
                self.cover_palette.set(photo_choice_palette(choice, self.cover_palette.get()))
                self.cover_art_note.set(f"Automatically selected: {choice.get('name', 'topic-matched cover art')}.")
            else:
                self.cover_art_note.set("Cover Art Required — no approved matching background is available.")
                self.status.set("Production paused until you choose or approve a matching background.")
                return None
        if not art or not BackgroundAssetIndex().ledger_details(art):
            choice = recommend_background_photo(theme_data)
            candidate = APP_DIR / str(choice.get("file") or "") if choice else None
            if candidate and candidate.is_file() and BackgroundAssetIndex().ledger_details(candidate):
                art = candidate; self.cover_art.set(str(art)); self.cover_art_focus.set(str(choice.get("focus") or "center"))
            else:
                self.cover_art_note.set("Cover Art Required — choose an approved asset or review pending artwork.")
                self.status.set("Production paused: no approved cover background is available.")
                return None
        format_label = "LARGE PRINT" if book_format_label(theme_data) == "LARGE PRINT PUZZLES" else "WORD SEARCH"
        settings = {"title": self.book_title.get().strip(), "subtitle": self.subtitle.get().strip(), "author": self.author.get().strip() or "Jordan M. Slade", "badge": self.cover_badge.get().strip(), "puzzle_count": len(theme_data.get("puzzles", [])), "difficulty": difficulty, "format_label": format_label, "palette": self.cover_palette.get(), "style": style, "imprint": self.author.get().strip() or "Jordan M. Slade", "theme": str(self.selected_theme), "art": str(art) if art else "", "art_focus": self.cover_art_focus.get()}
        save_cover_preferences(self.selected_theme, settings)
        try:
            save_niche_cover_memory(str(theme_data.get("series") or theme_data.get("detected_topic") or "General Interest"),settings)
        except (OSError, AttributeError): pass
        return settings

    def _generate_studio_cover(self) -> None:
        settings = self._studio_cover_settings()
        if not settings:
            return
        output = OUTPUT_DIR / f"{self._safe_filename(settings['title'])}_cover.png"
        self.status.set("Creating the front cover…")
        threading.Thread(target=self._run_studio_cover, args=(settings, output), daemon=True).start()

    def _run_studio_cover(self, settings: dict[str, str], output: Path) -> None:
        python = WINDOWS_VENV_PYTHON if WINDOWS_VENV_PYTHON.exists() else Path(sys.executable)
        command = [str(python), str(COVER_ENGINE), "--title", settings["title"], "--subtitle", settings["subtitle"], "--author", settings["author"], "--badge", settings["badge"], "--puzzle-count", str(settings.get("puzzle_count", 0)), "--difficulty", settings["difficulty"], "--format-label", settings.get("format_label", "WORD SEARCH"), "--palette", settings["palette"], "--style", settings["style"], "--theme-file", settings["theme"], "--out", str(output)]
        if settings["art"]:
            command.extend(["--art", settings["art"], "--art-focus", settings.get("art_focus", "center")])
        try:
            result = subprocess.run(command, cwd=APP_DIR, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode:
                raise RuntimeError(result.stderr.strip() or result.stdout.strip())
            if settings.get("art"):
                record_cover_art_use(Path(settings["art"]), settings["title"], settings["theme"])
            self.after(0, self._studio_package_finished, True, output, "Front cover created.")
        except Exception as exc:
            log_plain_error("Front cover creation", settings.get("title", ""), exc, "Check the cover settings and try again. The existing theme was not changed.")
            self.after(0, self._studio_package_finished, False, None, str(exc))

    def _open_quality_score(self) -> None:
        if not self.selected_theme:
            messagebox.showwarning("Choose a theme", "Choose a saved theme first.", parent=self)
            return
        SmartContentQualityDialog(self)

    def _open_series_differentiation(self) -> None:
        if not self.selected_theme:
            messagebox.showwarning("Choose a theme", "Choose a saved theme first.", parent=self)
            return
        SeriesDifferentiationDialog(self)

    def _open_buyer_preview(self) -> None:
        settings = self._studio_cover_settings()
        if not settings:
            return
        if not self._confirm_unique_title():
            self.status.set("Review paused so you can choose a distinct title.")
            return
        settings["archive_after_package"] = self.archive_after_package.get()
        settings["signature_edition"] = self.signature_edition.get()
        seed = self._automatic_seed()
        if seed is None:
            return
        BuyerPreviewDialog(self, settings, seed)

    def _generate_studio_package(self, skip_buyer_preview: bool = False, prepared_settings: dict[str, str] | None = None, prepared_seed: int | None = None) -> None:
        if not skip_buyer_preview:
            self._open_buyer_preview()
            return
        settings = prepared_settings or self._studio_cover_settings()
        if not settings:
            return
        seed = prepared_seed if prepared_seed is not None else self._automatic_seed()
        if seed is None:
            return
        # The Autopilot records the real source and validated facts before any
        # costly subprocess starts. It does not replace this established gate.
        autopilot, autopilot_facts = self._begin_wordsearch_autopilot(settings, seed)
        errors, quality_warnings, _notes = production_stop_errors(self.selected_theme, seed, settings)
        if signature_requested(settings):
            try:
                signature_puzzles = len(json.loads(Path(settings["theme"]).read_text(encoding="utf-8-sig")).get("puzzles", []))
            except (OSError, json.JSONDecodeError):
                signature_puzzles = 0
            if signature_puzzles < SIGNATURE_PUZZLE_TARGET:
                errors.append(f"Signature Editions require {SIGNATURE_PUZZLE_TARGET} puzzles. This theme has {signature_puzzles}. Use the Book Blueprint Wizard to build a new 100-puzzle Signature Edition from a clean word bank.")
        if errors:
            autopilot.fail("validate", " | ".join(errors), human_review=True)
            QualityReportDialog(self, "Book Quality Check", errors, quality_warnings, _notes)
            return
        autopilot.complete("validate", autopilot.stage_fingerprint(autopilot_facts, "validate"), "Capacity, title, safety, and source checks passed before generation.")
        autopilot.attach_orchestrator({**autopilot_facts, **settings, "book_plan_id": str(autopilot_facts.get("book_plan_id") or "checked-theme-plan"), "source_revision": autopilot_facts.get("fingerprint", "")})
        # A completed package with the exact same verified facts is safe to
        # reuse. This is the only automatic resume shortcut: partial folders
        # are never assumed valid and still go through Recovery Center.
        prior = autopilot.record().get("stages", {}).get("package", {})
        package_fingerprint = autopilot.stage_fingerprint(autopilot_facts, "package")
        previous_folder = Path(str(prior.get("artifact") or ""))
        from publishing.package_layout import release_contract
        if prior.get("status") == "complete" and prior.get("fingerprint") == package_fingerprint and prior.get("artifact") and previous_folder.is_dir() and release_contract(previous_folder)["ready"]:
            self.last_output = package_file(previous_folder, "interior.pdf")
            self.last_wrap_preview = package_file(previous_folder, "kdp_full_wrap_preview.png")
            self.status.set("A matching checked package already exists, so Autopilot reused it instead of rebuilding PDFs and cover files.")
            self._studio_package_finished(True, previous_folder, "Matching completed package reused. Review it in Book Control Center or Publishing Manager.")
            return
        from publishing.package_layout import package_root_for_artifact
        generated = autopilot.current_artifact("generate", autopilot.stage_fingerprint(autopilot_facts, "generate"))
        folder = package_root_for_artifact(generated) if generated else None
        if not folder or not folder.is_dir():
            folder = OUTPUT_DIR / f"{self._safe_filename(settings['title'])}_{datetime.now():%Y%m%d_%H%M%S}"
        from publishing.job_queue import ProductionJobQueue
        job_id = hashlib.sha1(f"word-search|{Path(settings['theme']).resolve()}|{settings['title']}".encode("utf-8")).hexdigest()[:12]
        job_queue = ProductionJobQueue(APP_DIR)
        acquired, note = job_queue.acquire(job_id, settings["title"])
        if not acquired:
            self.status.set(note)
            messagebox.showinfo("One book at a time", note, parent=self)
            return
        self._package_in_progress = True
        self.generate_button.configure(state="disabled")
        self.status.set("Starting package: preparing the interior, cover, print wrap, listing files, and final checks…")
        threading.Thread(target=self._run_studio_package, args=(settings, seed, folder, quality_warnings, autopilot, autopilot_facts, job_queue, job_id), daemon=True).start()

    @staticmethod
    def _begin_wordsearch_autopilot(settings: dict[str, str], seed: int):
        """Create a local checkpoint record from the same theme used to build."""
        from publishing.production_autopilot import ProductionAutopilot, canonical_facts
        source_path = Path(settings["theme"])
        try:
            source = json.loads(source_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            source = {}
        source = {**source, "title": settings["title"], "subtitle": settings["subtitle"], "author": settings["author"], "puzzle_count": int(settings.get("puzzle_count") or len(source.get("puzzles") or [])), "puzzle_seed": seed}
        book_id = hashlib.sha1(str(source_path.resolve()).encode("utf-8")).hexdigest()[:12]
        facts = canonical_facts({"book_id": book_id, "source_key": str(source_path), "package_path": "", "metadata": source}, source)
        autopilot = ProductionAutopilot(APP_DIR, book_id)
        autopilot.begin(facts)
        return autopilot, facts

    @staticmethod
    def _write_proof_bundle(folder: Path, settings: dict[str, str], seed: int, pages: int, package_data: dict) -> None:
        """Create the small, easy-to-review proof folder kept with every package."""
        proof = proof_folder(folder, create=True)
        python = WINDOWS_VENV_PYTHON if WINDOWS_VENV_PYTHON.exists() else Path(sys.executable)
        preview_pdf = proof / "reader_preview_3_puzzles.pdf"
        result = subprocess.run(
            [str(python), str(ENGINE), "--themes", settings["theme"], "--out", str(preview_pdf),
             "--title", settings["title"], "--subtitle", settings["subtitle"], "--author", settings["author"],
             "--seed", str(seed), "--preview-puzzles", "3"],
            cwd=APP_DIR, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "The reader preview could not be created.")
        for source, target in ((package_file(folder, "front_cover.png"), proof / "front_cover.png"),
                               (package_file(folder, "front_cover_thumbnail.png"), proof / "buyer_thumbnail.png"),
                               (package_file(folder, "kdp_full_wrap_preview.png"), proof / "full_wrap_preview.png"),
                               (package_file(folder, "KDP_LISTING_KIT.txt"), proof / "KDP_LISTING_PREVIEW.txt")):
            if source.exists(): shutil.copy2(source, target)
        proof_text = [
            "PROOF REVIEW BUNDLE", "=" * 48, f"Title: {settings['title']}",
            f"Interior pages: {pages}", f"Difficulty: {settings.get('difficulty', 'Standard')}",
            f"Cover direction: {settings.get('palette', '').replace('-', ' ').title()} / {settings.get('style', '')}", "",
            "OPEN THESE FIRST", "[ ] buyer_thumbnail.png - title and badge are clear at a small size",
            "[ ] reader_preview_3_puzzles.pdf - grid, word list, and solution pages are readable",
            "[ ] KDP_LISTING_PREVIEW.txt - title, description, keywords, and price direction match the book", "",
            "This is a fast human review. The full package still includes the complete interior and KDP wrap.",
        ]
        if (proof / "full_wrap_preview.png").exists():
            proof_text.insert(-2, "[ ] full_wrap_preview.png - back cover, spine treatment, and front cover look balanced")
        (proof / "PROOF_REVIEW.txt").write_text("\n".join(proof_text) + "\n", encoding="utf-8")

    def _create_proof_bundle_only(self) -> None:
        """Make a lightweight visual proof before committing to a final package."""
        settings = self._studio_cover_settings()
        if not settings:
            return
        seed = self._automatic_seed()
        if seed is None:
            return
        folder = OUTPUT_DIR / "proof_packages" / f"{self._safe_filename(settings['title'])}_{datetime.now():%Y%m%d_%H%M%S}"
        self.status.set("Creating a proof bundle: cover, listing preview, and three sample puzzles…")
        def run() -> None:
            try:
                folder.mkdir(parents=True, exist_ok=False)
                initialize_package_layout(folder)
                python = WINDOWS_VENV_PYTHON if WINDOWS_VENV_PYTHON.exists() else Path(sys.executable)
                front = package_file(folder, "front_cover.png", for_write=True)
                cover = [str(python), str(COVER_ENGINE), "--title", settings["title"], "--subtitle", settings["subtitle"], "--author", settings["author"], "--badge", settings["badge"], "--puzzle-count", str(settings.get("puzzle_count", 0)), "--difficulty", settings["difficulty"], "--format-label", settings.get("format_label", "WORD SEARCH"), "--palette", settings["palette"], "--style", settings["style"], "--theme-file", settings["theme"], "--out", str(front)]
                if settings.get("art"):
                    cover.extend(["--art", settings["art"], "--art-focus", settings.get("art_focus", "center")])
                result = subprocess.run(cover, cwd=APP_DIR, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
                if result.returncode: raise RuntimeError(result.stderr.strip() or result.stdout.strip())
                data = json.loads(Path(settings["theme"]).read_text(encoding="utf-8-sig"))
                package_data = package_data_from_settings(data, settings)
                package_file(folder, "KDP_LISTING_KIT.txt", for_write=True).write_text(listing_kit_text(package_data), encoding="utf-8")
                thumbnail = package_file(folder, "front_cover_thumbnail.png", for_write=True)
                with Image.open(front) as image:
                    image.thumbnail((510, 660), Image.LANCZOS); image.save(thumbnail)
                (folder / "START_HERE.txt").write_text(package_layout_readme(settings["title"]), encoding="utf-8")
                self._write_proof_bundle(folder, settings, seed, 0, package_data)
                self.after(0, lambda: (self.status.set("Proof bundle ready: review it before making the full package."), os.startfile(folder)))
            except Exception as exc:
                log_plain_error("Proof bundle", settings.get("title", ""), exc, "Check the selected cover picture and theme, then try the proof bundle again.")
                self.after(0, lambda: messagebox.showerror("Proof bundle problem", str(exc), parent=self))
        threading.Thread(target=run, daemon=True).start()

    def _run_studio_package(self, settings: dict[str, str], seed: int, folder: Path, quality_warnings: list[str] | None = None, autopilot=None, autopilot_facts: dict | None = None, job_queue=None, job_id: str = "") -> None:
        try:
            current_stage = "generate"
            def phase(message: str) -> None:
                self.after(0, lambda: self.status.set(message))
            from pypdf import PdfReader
            selected_art = Path(settings["art"]) if settings.get("art") else None
            if not selected_art or not selected_art.exists() or not BackgroundAssetIndex().ledger_details(selected_art):
                raise RuntimeError("COVER ART REQUIRED — choose an approved matching picture or review pending artwork before creating a production package.")
            # A verified generated interior can be resumed in its original
            # package folder. New builds still receive a fresh timestamped one.
            folder.mkdir(parents=True, exist_ok=True)
            initialize_package_layout(folder)
            python = WINDOWS_VENV_PYTHON if WINDOWS_VENV_PYTHON.exists() else Path(sys.executable)
            interior = package_file(folder, "interior.pdf", for_write=True)
            front = package_file(folder, "front_cover.png", for_write=True)
            wrap = package_file(folder, "kdp_full_wrap.pdf", for_write=True)
            commands = [
                [str(python), str(ENGINE), "--themes", settings["theme"], "--out", str(interior), "--title", settings["title"], "--subtitle", settings["subtitle"], "--author", settings["author"], "--seed", str(seed)],
                [str(python), str(COVER_ENGINE), "--title", settings["title"], "--subtitle", settings["subtitle"], "--author", settings["author"], "--badge", settings["badge"], "--puzzle-count", str(settings.get("puzzle_count", 0)), "--difficulty", settings["difficulty"], "--format-label", settings.get("format_label", "WORD SEARCH"), "--palette", settings["palette"], "--style", settings["style"], "--theme-file", settings["theme"], "--out", str(front)],
            ]
            if signature_requested(settings):
                commands[0].append("--signature-edition")
            if settings["art"]:
                commands[1].extend(["--art", settings["art"], "--art-focus", settings.get("art_focus", "center")])
            generated = autopilot.current_artifact("generate", autopilot.stage_fingerprint(autopilot_facts, "generate")) if autopilot and autopilot_facts else None
            covered = autopilot.current_artifact("cover", autopilot.stage_fingerprint(autopilot_facts, "cover")) if autopilot and autopilot_facts else None
            phase("Reusing the checked interior PDF…" if generated and interior.is_file() else "Building the interior PDF with every puzzle and answer page…")
            for number, command in enumerate(commands):
                if number == 0 and generated and interior.is_file():
                    current_stage = "cover"; phase("Interior reused. Creating the front cover with your selected design…")
                    continue
                if number == 1 and covered and front.is_file():
                    phase("Checked interior and cover reused. Finishing the wrap, listing, and proof checks…")
                    continue
                result = subprocess.run(command, cwd=APP_DIR, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
                if result.returncode:
                    raise RuntimeError(result.stderr.strip() or result.stdout.strip())
                if number == 0:
                    if autopilot and autopilot_facts:
                        autopilot.complete("generate", autopilot.stage_fingerprint(autopilot_facts, "generate"), "Interior PDF was generated from the selected theme and seed.", artifact=str(interior))
                    current_stage = "cover"
                    phase("Interior complete. Creating the front cover with your selected design…")
                elif autopilot and autopilot_facts:
                    autopilot.complete("cover", autopilot.stage_fingerprint(autopilot_facts, "cover"), "Front cover was rendered with the verified title, badge, and selected approved art.", artifact=str(front))
            pages = len(PdfReader(str(interior)).pages)
            data = json.loads(Path(settings["theme"]).read_text(encoding="utf-8-sig"))
            package_data = package_data_from_settings(data, settings)
            blurb = package_blurb(data, package_data)
            phase("Writing the listing copy, upload checklist, and package guide…")
            package_file(folder, "KDP_UPLOAD_CHECKLIST.txt", for_write=True).write_text(kdp_upload_checklist_text(package_data, pages), encoding="utf-8")
            package_file(folder, "KDP_LISTING_KIT.txt", for_write=True).write_text(listing_kit_text(package_data), encoding="utf-8")
            if autopilot and autopilot_facts:
                autopilot.complete("listing", autopilot.stage_fingerprint(autopilot_facts, "listing"), "Listing kit and upload checklist were generated from package facts.")
            (folder / "START_HERE.txt").write_text(package_layout_readme(settings["title"]), encoding="utf-8")
            if settings.get("art"):
                record = asset_record(Path(settings["art"]), COVER_ASSETS_DIR)
                if record:
                    package_file(folder, "COVER_ART_LICENSE.txt", for_write=True).write_text(
                        "COVER ART RECORD\n\n"
                        f"Title: {record.get('title', '')}\nArtist: {record.get('artist_name', '')}\n"
                        f"License: {record.get('license', 'CC0-1.0')}\nSource dataset: {record.get('source_dataset', '')}\n"
                        f"Original page: {record.get('page_url', '')}\nLocal selected asset: {record.get('local_file', '')}\n",
                        encoding="utf-8",
                    )
            preview = package_file(folder, "kdp_full_wrap_preview.png", for_write=True)
            phase("Building the full print wrap from the final interior page count…")
            current_stage = "preflight"
            result = subprocess.run([str(python), str(WRAP_ENGINE), "--front", str(front), "--pages", str(pages), "--palette", settings["palette"], "--title", settings["title"], "--author", settings["author"], "--back", blurb, "--out", str(wrap), "--preview-out", str(preview)], cwd=APP_DIR, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode:
                raise RuntimeError(result.stderr.strip() or result.stdout.strip())
            matches = cross_book_similarity_report(Path(settings["theme"]), data)
            originality = ["ORIGINALITY CHECK", "=" * 48, "This compares this theme with saved books. It is a production similarity signal, not a copyright clearance.", ""]
            originality.extend(f"• {item['title']}: {float(item['overlap']):.0%} shared vocabulary ({item['level']})" for item in matches[:5])
            if not matches: originality.append("PASS - no meaningful overlap with other saved books was found.")
            package_file(folder, "ORIGINALITY_CHECK.txt", for_write=True).write_text("\n".join(originality) + "\n", encoding="utf-8")
            phase("Creating the reader proof and running print-safety checks…")
            self._write_proof_bundle(folder, settings, seed, pages, package_data)
            from publishing.review import build_proof_contact_sheet
            build_proof_contact_sheet(folder)
            write_kdp_compliance_report(folder, package_data, pages)
            preflight_ok, preflight_lines = preflight(folder)
            package_file(folder, "PUBLISHER_PREFLIGHT.txt", for_write=True).write_text(package_preflight_text(folder), encoding="utf-8")
            if not preflight_ok:
                raise RuntimeError("The package was created, but its print preflight needs attention:\n" + "\n".join(preflight_lines))
            if autopilot and autopilot_facts:
                autopilot.complete("preflight", autopilot.stage_fingerprint(autopilot_facts, "preflight"), "Print preflight passed using the final interior page count.")
            cover_score, cover_label, cover_notes = cover_quality_report(
                settings["title"], settings["subtitle"], settings["badge"], settings.get("puzzle_count", 0),
                settings.get("format_label", "WORD SEARCH"), settings["style"], settings.get("art", ""),
            )
            package_file(folder, "COVER_QUALITY_REPORT.txt", for_write=True).write_text(
                "COVER QUALITY REPORT\n" + "=" * 48 + f"\nScore: {cover_score}/100 — {cover_label}\n\n" +
                "\n".join(f"• {note}" for note in cover_notes) + "\n",
                encoding="utf-8",
            )
            release_blockers = write_release_safety_files(folder, Path(settings["theme"]), data, settings, pages)
            if release_blockers:
                raise RuntimeError("The package files were created, but the release safety check stopped the handoff:\n" + "\n".join(release_blockers))
            phase("Inspecting the rendered interior, cover, solutions, and package…")
            from publishing.product_qa import inspect_product, write_product_qa_report
            product_qa = inspect_product(APP_DIR, folder, package_data)
            write_product_qa_report(package_file(folder, "PRODUCT_QA.txt", for_write=True), product_qa)
            if product_qa.blockers:
                raise RuntimeError("Product QA stopped the handoff:\n" + "\n".join(item.message for item in product_qa.blockers))
            if autopilot and autopilot_facts:
                autopilot.complete("qa", autopilot.stage_fingerprint(autopilot_facts, "qa"), product_qa.status)
            phase("Running the final package inspection and syncing Publishing Center…")
            from publishing.production_intelligence import finalize_package
            intelligence = finalize_package(APP_DIR, folder, package_data, settings["title"], settings["subtitle"], pages)
            if not intelligence["ready"]:
                raise RuntimeError("Final package intelligence stopped the handoff:\n" + "\n".join(intelligence["blockers"]))
            if autopilot and autopilot_facts:
                autopilot.complete("package", autopilot.stage_fingerprint(autopilot_facts, "package"), "Final local package inspection passed and master release files were created.", artifact=str(folder))
            quality_warnings = list(quality_warnings or []) + list(publisher_safety_report(package_data)["warnings"])
            package_file(folder, "PACKAGE_SCORECARD.txt", for_write=True).write_text(package_scorecard_text(package_data, folder, pages, quality_warnings), encoding="utf-8")
            self.last_output = interior
            self.last_wrap_preview = preview
            source_bytes = Path(settings["theme"]).read_bytes()
            save_production_history({
                "title": settings["title"], "theme": Path(settings["theme"]).name,
                "theme_path": str(Path(settings["theme"]).resolve()),
                "created": datetime.now().isoformat(timespec="seconds"), "package": str(folder),
                "approval": "Complete package and local preflight passed",
                "pages": pages, "source_checksum": hashlib.sha256(source_bytes).hexdigest(),
                "settings": {key: settings.get(key, "") for key in ("title", "subtitle", "author", "palette", "style", "badge", "difficulty", "format_label", "art", "art_focus", "signature_edition")},
                "marketplaces": {"Amazon KDP": "Ready to prepare", "Etsy": "Not prepared", "Direct/other": "Not prepared"},
            })
            record_package_created(Path(settings["theme"]), settings["title"], folder, pages)
            record_launch_batch_package(settings["title"], folder)
            # Publishing Manager is the production record.  Register the new
            # package immediately so it is ready for KDP preparation as soon
            # as the user returns to the dashboard.
            payhip_note = ""
            try:
                from publishing import PublishingService
                publishing_service = PublishingService(APP_DIR)
                book_id = publishing_service.sync_theme(Path(settings["theme"]), folder)
                publishing_service.db.set_approval_status(book_id, "Completed", "Complete package and proof checks passed.")
                # A completed book already has the verified interior and front
                # cover that Payhip needs.  Build its local customer-download
                # handoff now, rather than making the publisher remember a
                # second preparation step in Publishing Center.
                payhip_folder, payhip_issues = publishing_service.prepare(book_id, "payhip")
                if payhip_issues:
                    payhip_note = " KDP package is ready; Payhip preparation needs attention in Publishing Center."
                else:
                    payhip_note = " Payhip upload files and publishing sheet are included."
                if autopilot and autopilot_facts:
                    autopilot.complete("register", autopilot.stage_fingerprint(autopilot_facts, "register"), "Finished package was registered in Publishing Center and its Payhip handoff was prepared.")
            except Exception as sync_exc:
                log_plain_error("Publishing catalog sync", settings["title"], sync_exc, "The book package is safe. Open Publishing Manager and choose Sync catalog.")
            if settings.get("art"):
                record_cover_art_use(Path(settings["art"]), settings["title"], settings["theme"])
            if job_queue:
                job_queue.release(job_id, "complete")
            message = "Complete package created: interior, front cover, full wrap, and thumbnail." + payhip_note
            if settings.get("archive_after_package"):
                try:
                    archived = archive_used_theme(Path(settings["theme"]))
                    message += f" Theme moved to Used Themes: {archived.name}."
                    self.after(0, self._load_theme_list)
                except OSError as exc:
                    message += f" Package is ready, but the theme was not moved: {exc}"
            self.after(0, self._studio_package_finished, True, folder, message)
        except Exception as exc:
            if job_queue:
                job_queue.release(job_id, "needs_attention")
            if autopilot:
                autopilot.fail(locals().get("current_stage", "generate"), str(exc), human_review=any(term in str(exc).casefold() for term in ("author", "insufficient", "protected", "trademark", "no-repeat", "rights")))
            try:
                from publishing import PublishingService
                PublishingService(APP_DIR).db.set_approval_status_for_source(str(Path(settings.get("theme") or "").resolve()), "Needs attention", str(exc)[:300])
            except Exception:
                pass
            log_plain_error("Complete package", settings.get("title", ""), exc, "Open Error Log for the details, then use Check Book before trying again.")
            self.after(0, self._studio_package_finished, False, None, str(exc))

    def _studio_package_finished(self, success: bool, target: Path | None, message: str) -> None:
        self._package_in_progress = False
        self.generate_button.configure(state="normal")
        if success:
            self.open_button.configure(state="normal")
            self.status.set(message)
            if target and target.is_dir():
                os.startfile(target)
            elif target:
                os.startfile(target)
        else:
            self.status.set("The requested files could not be created.")
            messagebox.showerror("Generation problem", message)

    def _preview_wrap(self) -> None:
        if not self.last_wrap_preview or not self.last_wrap_preview.exists():
            return
        window = tk.Toplevel(self); window.title("KDP Full-Wrap Preview")
        preview_width = min(1100, max(760, window.winfo_screenwidth() - 70))
        preview_height = min(720, max(500, window.winfo_screenheight() - 110))
        window.geometry(f"{preview_width}x{preview_height}"); window.configure(background="#1f2933")
        image = Image.open(self.last_wrap_preview); image.thumbnail((1050, 650), Image.LANCZOS)
        photo = ImageTk.PhotoImage(image)
        label = tk.Label(window, image=photo, background="#1f2933"); label.image = photo; label.pack(padx=18, pady=(18, 8))
        tk.Label(window, text="Back cover  •  Spine  •  Front cover — preview only; use the PDF for KDP upload.", foreground="#ffffff", background="#1f2933", font=("Segoe UI", 10)).pack(pady=(0, 14))

    def _check_quality(self) -> None:
        if not self.selected_theme:
            messagebox.showwarning("Choose a theme", "Choose a theme file before checking the book.")
            return
        seed = self._automatic_seed()
        if seed is None:
            return
        self.quality_button.configure(state="disabled")
        self.status.set("Checking every puzzle and word placement…")
        threading.Thread(target=self._run_quality_check, args=(self.selected_theme, seed), daemon=True).start()

    def _run_quality_check(self, path: Path, seed: int) -> None:
        errors, warnings, notes = quality_gate(path, seed)
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            warnings.extend(series_consistency_notes(path, data)); warnings.extend(puzzle_variety_notes(data))
        except (OSError, json.JSONDecodeError):
            pass
        try:
            record_theme_health(THEME_HEALTH_CACHE_FILE, path, errors, warnings)
        except OSError:
            pass
        self.after(0, self._quality_finished, errors, warnings, notes)

    def _quality_finished(self, errors: list[str], warnings: list[str], notes: list[str]) -> None:
        self.quality_button.configure(state="normal")
        if errors:
            self.status.set(f"Quality check found {len(errors)} issue(s) to fix.")
        else:
            self.status.set("Quality check passed. Your selected theme is ready to generate.")
        QualityReportDialog(self, "Book Quality Check", errors, warnings, notes)

    def _run_engine(self, seed: int) -> None:
        python = WINDOWS_VENV_PYTHON if WINDOWS_VENV_PYTHON.exists() else Path(sys.executable)
        command = [
            str(python), str(ENGINE), "--themes", str(self.selected_theme), "--out", str(self.last_output),
            "--title", self.book_title.get().strip(), "--subtitle", self.subtitle.get().strip(),
            "--author", self.author.get().strip(), "--seed", str(seed),
        ]
        if self.signature_edition.get():
            command.append("--signature-edition")
        try:
            result = subprocess.run(
                command, cwd=APP_DIR, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "The generator stopped unexpectedly.")
            self.after(0, self._generation_finished, True, result.stdout.strip())
        except Exception as exc:  # surfaced to the beginner-friendly window
            log_plain_error("Interior PDF", self.book_title.get(), exc, "Use Check Book, confirm the word bank, then try again.")
            self.after(0, self._generation_finished, False, str(exc))

    def _generation_finished(self, success: bool, details: str) -> None:
        self.generate_button.configure(state="normal")
        if success and self.last_output and self.last_output.exists():
            self.open_button.configure(state="normal")
            self.status.set(f"Done! Your PDF is ready: {self.last_output.name}")
            messagebox.showinfo("Book created", f"Your print-ready PDF is ready.\n\n{self.last_output}")
        else:
            self.status.set("The PDF could not be created.")
            messagebox.showerror("Generation problem", details)

    def _open_pdf(self) -> None:
        if self.last_output and self.last_output.exists():
            os.startfile(self.last_output)  # Windows-only app

    def _open_output_folder(self) -> None:
        OUTPUT_DIR.mkdir(exist_ok=True)
        os.startfile(OUTPUT_DIR)  # Windows-only app

    def _open_batch_generator(self) -> None:
        BatchGenerationDialog(self)

    def _open_theme_builder(self) -> None:
        ThemeBuilderDialog(self)

    def _open_theme_dashboard(self) -> None:
        ThemeDashboardDialog(self)

    def _open_publisher_safety(self) -> None:
        if not self.selected_theme:
            messagebox.showwarning("Choose a theme", "Choose a saved theme first.", parent=self)
            return
        PublisherSafetyDialog(self)

    def _open_edition_designer(self) -> None:
        if not self.selected_theme:
            messagebox.showwarning("Choose a theme", "Choose a saved theme first.", parent=self)
            return
        EditionDesignerDialog(self)

    def _open_market_pulse(self) -> None:
        MarketPulseDialog(self)

    def _open_word_bank_health(self) -> None:
        WordBankHealthDialog(self)

    def _open_word_intelligence(self) -> None:
        WordIntelligenceCenterDialog(self)

    def _refresh_library_summary(self) -> None:
        """Update the compact home-screen library note after a safe refresh."""
        if not hasattr(self, "library_summary"):
            return
        library = load_master_word_bank()
        words = int(library.get("total_unique_words", 0)) if isinstance(library, dict) else 0
        topics = len(library.get("topics", {})) if isinstance(library, dict) else 0
        intelligence = library_intelligence_summary()
        self.library_summary.set(f"Library: {words:,} words across {topics} topics | {intelligence['ready_48']} ready now | {intelligence['needs_expansion']} safely being expanded")

    def _refresh_library_intelligence(self) -> None:
        """Offer the same safe refresh from the main Library menu."""
        self.status.set("Refreshing library intelligence. Your themes will not be changed…")
        def worker() -> None:
            ok, message = refresh_library_intelligence()
            self.after(0, lambda: self._library_refresh_finished(ok, message))
        threading.Thread(target=worker, daemon=True).start()

    def _library_refresh_finished(self, ok: bool, message: str) -> None:
        if ok:
            self._refresh_library_summary()
            self.status.set(message)
            return
        log_plain_error("Refresh Library Intelligence", "", message, "Open the Error Log, then run the project check before trying again.")
        self.status.set("Library refresh needs attention. Open Error Log for the plain-English fix.")
        messagebox.showerror("Library refresh could not finish", message, parent=self)

    def _move_theme_to_folder(self) -> None:
        if not self.selected_theme: messagebox.showinfo("Choose a theme", "Choose a theme first.", parent=self); return
        name=simpledialog.askstring("Theme Folder", "Folder or group name (example: Holidays, Nature, Best Sellers):", parent=self)
        if not name or not name.strip(): return
        folder=THEMES_DIR / "Groups" / self._safe_filename(name.strip()); folder.mkdir(parents=True,exist_ok=True); target=folder / self.selected_theme.name
        if target.exists(): messagebox.showwarning("Already exists", f"A file named {target.name} is already in that folder.", parent=self); return
        shutil.move(str(self.selected_theme),str(target)); self._load_theme_list(); self._set_theme(target); self.status.set(f"Moved theme into Groups\\{folder.name}.")

    def _archive_current_theme(self) -> None:
        """Move an old or experimental theme out of production views safely."""
        if not self.selected_theme:
            messagebox.showinfo("Choose a theme", "Choose a theme first.", parent=self); return
        choice = messagebox.askyesnocancel(
            "Archive or research?",
            "Yes: move this theme to _Archive (finished, duplicate, or retired).\n\n"
            "No: move it to _Research (experimental or needs future content work).\n\n"
            "Cancel: keep it in the active library.", parent=self)
        if choice is None:
            return
        folder = ARCHIVE_THEMES_DIR if choice else RESEARCH_THEMES_DIR
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / self.selected_theme.name
        if target.exists():
            target = folder / f"{self.selected_theme.stem}_{datetime.now():%Y%m%d_%H%M%S}{self.selected_theme.suffix}"
        source = self.selected_theme
        shutil.move(str(source), str(target))
        self.selected_theme = None
        self._load_theme_list()
        self.status.set(f"Moved {source.name} to Themes\\{folder.name}. It is preserved on disk but no longer appears in production views.")

    def _rebuild_current_theme(self) -> None:
        """Start a clean replacement instead of altering an old mixed word bank."""
        if not self.selected_theme:
            messagebox.showinfo("Choose a theme", "Choose a theme first.", parent=self); return
        try:
            data = json.loads(self.selected_theme.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            messagebox.showerror("Cannot read theme", str(exc), parent=self); return
        review = data.get("quality_review") if isinstance(data.get("quality_review"), dict) else {}
        topic = str(data.get("detected_topic") or data.get("theme") or data.get("series") or "").strip()
        if not topic:
            messagebox.showinfo("Topic needed", "This older theme has no clear saved topic. Choose Build a Book from a Topic Pack and select the closest topic first.", parent=self); return
        if not messagebox.askyesno(
            "Build a clean replacement?",
            f"Create a new no-repeat theme from the checked '{topic}' topic pool?\n\n"
            "Your original file will stay unchanged. When the replacement passes its checks, you can archive the older source.", parent=self):
            return
        self.status.set(f"Opening a clean rebuild for {topic}. The old theme remains safely preserved.")
        GuidedBookBuilderDialog(self, initial_topic=topic, initial_pack=topic)

    def _open_series_builder(self) -> None:
        SeriesBuilderDialog(self)

    def _open_series_expansion(self) -> None:
        SeriesExpansionDialog(self)

    def _open_proofing_center(self) -> None:
        VisualProofingDialog(self)

    def _toggle_fullscreen(self, _event: object = None) -> str:
        """F11 offers true borderless full screen while the default stays maximized."""
        enabled = bool(self.attributes("-fullscreen"))
        self.attributes("-fullscreen", not enabled)
        return "break"

    def _open_release_manager(self) -> None:
        ReleaseManagerDialog(self)

    def _open_publishing_manager(self, open_dashboard: bool = False) -> None:
        """Open the separate marketplace workspace without changing book creation."""
        try:
            from publishing import PublishingService
            from publishing.ui import PublishingManagerDialog
            service = PublishingService(APP_DIR)
            PublishingManagerDialog(
                self, service, lambda: self._sync_publishing_catalog(service),
                self._open_publishing_recommendation, self._create_publishing_package,
                self._start_publishing_new_book, open_dashboard=open_dashboard,
            )
        except Exception as exc:
            log_plain_error("Publishing Manager", "", exc, "Restart the app, then open Publishing Manager again. If it continues, open Error Log for the details.")
            messagebox.showerror("Publishing Manager problem", str(exc), parent=self)

    def _open_production_dashboard(self) -> None:
        """Open the useful readiness view directly, with Publishing Center behind it."""
        self._open_publishing_manager(open_dashboard=True)

    def _open_book_readiness(self) -> None:
        """Open the shared Phase 5 feasibility and attention front door."""
        try:
            from publishing import PublishingService
            from publishing.operator_ui import OperatorWorkflowDialog
            service = PublishingService(APP_DIR)
            initial = self.book_title.get().strip() if getattr(self, "book_title", None) else ""
            OperatorWorkflowDialog(self, APP_DIR, service.db, initial_topic=initial)
        except Exception as exc:
            log_plain_error("Book Readiness", "", exc, "Open Publishing Center and try again. Your book files and word library were not changed.")
            messagebox.showerror("Book Readiness problem", "Book Readiness could not open. Your saved content was not changed.\n\n" + str(exc), parent=self)

    def _open_production_history(self) -> None:
        """Open the local approval trail without creating or changing a book."""
        ProductionHistoryDialog(self)

    @staticmethod
    def _sync_publishing_catalog(service) -> int:
        themes = service.sync_catalog(all_book_theme_files(), load_release_catalog())
        packages = service.sync_output_packages()
        return themes + packages

    def _open_publishing_recommendation(self, book: dict) -> None:
        """Send a recommended theme from Publishing Manager back to the creator."""
        source = Path(str(book.get("source_key") or ""))
        if not source.is_file():
            messagebox.showinfo("Package already created", "This recommendation already has a completed package. Select it in Publishing Manager and choose Prepare KDP when you are ready.", parent=self)
            return
        self._set_theme(source)
        if not self.workspace.winfo_ismapped():
            self._toggle_word_search_workspace()
        self.deiconify(); self.lift(); self.focus_force()
        self.status.set(f"Opened recommended book: {self.book_title.get()}. Review the cover, then choose Review & Create Package.")

    def _start_publishing_new_book(self, capacity_plan: dict | None = None) -> None:
        """Send the production dashboard's New book button into the guided creator."""
        self.deiconify(); self.lift(); self.focus_force()
        topic = str((capacity_plan or {}).get("topic") or "")
        if topic:
            GuidedBookBuilderDialog(self, initial_topic=topic, initial_pack=topic)
            self.status.set(f"Opened a ready-only blueprint for {topic}. The focused words and recommended 48-puzzle setup are already loaded.")
            return
        self._open_create_new_book()

    def _create_publishing_package(self, book: dict) -> None:
        """Create one selected catalog theme with its saved automatic settings.

        The same quality gate and package builder used by Book Studio are used
        here; Publishing Manager only removes the unnecessary navigation step.
        """
        source = Path(str(book.get("source_key") or ""))
        if not source.is_file():
            messagebox.showinfo("Package already created", "This catalog entry is a completed package instead of a saved Word Search theme. Select it in Publishing Manager and choose Prepare KDP when you are ready.", parent=self)
            return
        self._set_theme(source)
        if not self._confirm_unique_title():
            self.status.set("Package creation paused so you can choose a distinct title.")
            return
        settings = self._studio_cover_settings()
        if not settings:
            return
        seed = self._automatic_seed()
        if seed is None:
            return
        title = settings["title"]
        if not messagebox.askyesno(
            "Create complete package",
            f"Create the complete KDP package for:\n\n{title}\n\nThe studio will use this theme's saved title, cover direction, artwork choice, and automatic quality checks. A new dated package folder will be created; the theme itself will not be changed.",
            parent=self,
        ):
            return
        self.deiconify(); self.lift(); self.focus_force()
        self.status.set(f"Creating {title} from Publishing Manager with its automatic book and cover settings…")
        self._generate_studio_package(skip_buyer_preview=True, prepared_settings=settings, prepared_seed=seed)

    def _create_marketing_copy(self) -> None:
        if not self.selected_theme: messagebox.showwarning("Choose a theme", "Choose a theme first.", parent=self); return
        data = json.loads(self.selected_theme.read_text(encoding="utf-8-sig")); folder = OUTPUT_DIR / "listing_kits" / self._safe_filename(str(data.get("title") or self.selected_theme.stem)); folder.mkdir(parents=True, exist_ok=True)
        target = folder / "marketing_descriptions.txt"; target.write_text(marketing_descriptions(data), encoding="utf-8"); os.startfile(target); self.status.set("Created three KDP description options.")

    def _show_theme_preview_card(self) -> None:
        if not self.selected_theme: return
        data = json.loads(self.selected_theme.read_text(encoding="utf-8-sig")); freshness, quality = word_bank_freshness(data)
        package_data = package_data_from_settings(data, {"signature_edition": self.signature_edition.get()})
        pages = estimated_page_count(package_data); price, _royalty = recommended_us_paperback_price(pages, self.signature_edition.get()); edition = "Signature Edition — premium recommendation" if self.signature_edition.get() else "Standard Edition"
        messagebox.showinfo("Theme Preview Card", f"{data.get('title')}\n\nBuyer: {data.get('audience', 'Adults & Teens')}\nPuzzles: {len(data.get('puzzles', []))}\nDifficulty: {puzzle_difficulty_label(data)}\nFormat: {book_format_label(data).title()}\nFreshness: {freshness}% ({quality})\nSuggested price: ${price:.2f} ({edition})\n{spine_safety_note(pages)}\nTheme: {data.get('detected_topic', 'General Interest')}", parent=self)

    def _edit_brand_kit(self) -> None:
        kit = load_brand_kit(); author = simpledialog.askstring("Brand Kit", "Default author name:", initialvalue=str(kit.get("author") or "Jordan M. Slade"), parent=self)
        if author is None: return
        kit["author"] = author.strip() or "Jordan M. Slade"; BRAND_KIT_FILE.write_text(json.dumps(kit, indent=2) + "\n", encoding="utf-8"); self.author.set(kit["author"]); self.cover_imprint.set(kit["author"]); self.status.set("Saved your Brand Kit.")

    def _edit_theme_notes(self) -> None:
        if not self.selected_theme: return
        data = json.loads(self.selected_theme.read_text(encoding="utf-8-sig")); value = simpledialog.askstring("Theme Notes & Research", "Buyer angle, research, and future-series notes:", initialvalue=str(data.get("notes_and_research") or ""), parent=self)
        if value is None: return
        data["notes_and_research"] = value.strip(); self.selected_theme.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"); self.status.set("Saved notes with this theme.")

    def _create_backup(self) -> None:
        stamp=datetime.now().strftime("%Y%m%d_%H%M%S"); folder=OUTPUT_DIR / "backups"; folder.mkdir(parents=True, exist_ok=True); base=folder / f"word_search_creator_backup_{stamp}"
        archive=shutil.make_archive(str(base), "zip", APP_DIR, "themes")
        self.status.set(f"Created theme backup: {Path(archive).name}"); os.startfile(folder)

    def _create_production_lock(self) -> None:
        try:
            archive, tracker = create_production_lock()
            self.status.set(f"Production lock created: {archive.name}. Your first five packages will be added to the review tracker.")
            os.startfile(tracker)
        except OSError as exc:
            log_plain_error("Production lock", "", exc, "Check that the out/backups folder is available, then try again.")
            messagebox.showerror("Could not create production lock", str(exc), parent=self)

    def _open_launch_batch_tracker(self) -> None:
        folder = OUTPUT_DIR / "backups"
        report = folder / "FIRST_FIVE_BOOKS_REVIEW.txt"
        if not report.exists():
            messagebox.showinfo("First Five Books", "Create a Production Lock first. It makes the backup and the first-five review tracker.", parent=self)
            return
        os.startfile(report)

    def _restore_backup(self) -> None:
        archive=filedialog.askopenfilename(title="Choose a Word Search Creator backup",initialdir=OUTPUT_DIR / "backups",filetypes=[("ZIP backups","*.zip")],parent=self)
        if not archive:return
        destination=THEMES_DIR / "Restored" / datetime.now().strftime("%Y%m%d_%H%M%S")
        try:
            shutil.unpack_archive(archive,destination); self._load_theme_list(); self.status.set(f"Restored safely into {destination.relative_to(APP_DIR)}. Existing themes were not overwritten."); os.startfile(destination)
        except (OSError,shutil.ReadError) as exc:
            log_plain_error("Safe backup restore","",exc,"Choose a backup created by this app and try again."); messagebox.showerror("Could not restore backup",str(exc),parent=self)

    def _open_help_center(self) -> None:
        HelpCenterDialog(self)

    def _show_first_book_walkthrough(self) -> None:
        """A short, reopenable orientation for a new family member."""
        messagebox.showinfo(
            "Your first book — the simple path",
            "1. On the home page, choose Start a new book.\n\n"
            "2. Pick a focused topic pack. The app loads matching words and recommends the title, cover, and puzzle size.\n\n"
            "3. Read the final plan. The capacity line tells you whether the words support one or two complete no-repeat books.\n\n"
            "4. Approve the plan only when it looks right. The app creates the interior, cover, KDP wrap, listing copy, and proof files together.\n\n"
            "5. Open the completed package, review the proof files, then use Publishing Center to prepare the marketplace files.\n\n"
            "Nothing is published automatically. You remain in control at every approval step.",
            parent=self,
        )

    def _open_error_log(self) -> None:
        ErrorLogDialog(self)

    def _refresh_smart_theme_scan(self) -> None:
        scanned, changed = refresh_all_theme_intelligence()
        self._load_theme_list()
        self.status.set(f"Smart Theme Scan read {scanned} theme file(s) and updated {changed} missing recommendation record(s).")

    def _open_cover_gallery(self) -> None:
        CoverVariantGallery(self)

    def _run_project_check(self) -> None:
        problems, notes = run_project_check(THEMES_DIR)
        QualityReportDialog(self, "Project Check", problems, [], notes)

    def _open_word_bank_importer(self) -> None:
        WordBankImportDialog(self)

    def _open_book_blueprint(self) -> None:
        BookBlueprintDialog(self)

    def _open_create_new_book(self) -> None:
        """Open the one normal creation path; detailed creators stay intact."""
        CreateNewBookDialog(self)

    def _open_guided_book_builder(self) -> None:
        GuidedBookBuilderDialog(self)

    def _open_niche_research(self) -> None:
        NicheResearchDialog(self)

    def _open_topic_pack_builder(self) -> None:
        TopicPackBuilderDialog(self)

    def _show_version(self) -> None:
        """Show a plain-English record of the installed release."""
        try:
            history = CHANGELOG_FILE.read_text(encoding="utf-8-sig").strip()
            latest = history.split("\n## ", 2)[1] if "\n## " in history else history
            history = "## " + latest[:1800]
        except OSError:
            history = "No local change notes were found."
        messagebox.showinfo("What changed in this version", f"Word Search Creator {APP_VERSION}\n\n{history}\n\nFor older notes, open CHANGELOG.md in the app folder.", parent=self)

    def _open_publication_pipeline(self) -> None:
        PublicationPipelineDialog(self)

    def _open_seasonal_calendar(self) -> None:
        SeasonalCalendarDialog(self)

    def _open_cover_creator(self) -> None:
        CoverCreatorDialog(self)

    def _open_other_puzzle_studio(self, initial_kind: str = "Sudoku", initial_theme: str = "General Starter", initial_format: str = "Standard") -> None:
        from puzzle_book_studio import PuzzleBookStudio
        PuzzleBookStudio(self, initial_kind=initial_kind, initial_theme=initial_theme, initial_format=initial_format)

    def _open_cover_choices(self) -> None:
        CoverChoicesDialog(self)

    def _open_publish_ready(self) -> None:
        PublishReadyDialog(self)

    def _open_publish_ready_dashboard(self) -> None:
        PublishReadyDashboard(self)

    def _open_production_queue(self) -> None:
        ProductionQueueDialog(self)


class BackgroundGeneratorDialog(tk.Toplevel):
    """Compact review surface for approved, project-generated backgrounds."""

    def __init__(self, parent, *, topic: str, palette: str) -> None:
        super().__init__(parent); self.parent_app = parent
        self.title("Approved cover backgrounds"); self.geometry("720x490"); self.minsize(610, 410)
        self.configure(background="#1f1f1f"); self.transient(parent)
        self.topic = tk.StringVar(value=topic); self.palette = tk.StringVar(value=palette or "nature")
        self.quantity = tk.StringVar(value="1"); self.note = tk.StringVar()
        root = ttk.Frame(self, padding=20, style="App.TFrame"); root.pack(fill="both", expand=True); root.columnconfigure(1, weight=1)
        ttk.Label(root, text="Approved cover backgrounds", font=("Segoe UI", 16, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(root, text="Automatic production covers only use art made for this project and recorded in the approved library. Existing approved art is matched first; generate only when you need more variety.", wraplength=650, foreground="#9fcfc4").grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 14))
        ttk.Label(root, text="Topic").grid(row=2, column=0, sticky="w", pady=6); ttk.Entry(root, textvariable=self.topic).grid(row=2, column=1, sticky="ew", pady=6)
        ttk.Label(root, text="Color direction").grid(row=3, column=0, sticky="w", pady=6); ttk.Entry(root, textvariable=self.palette).grid(row=3, column=1, sticky="ew", pady=6)
        ttk.Label(root, text="How many concepts").grid(row=4, column=0, sticky="w", pady=6); ttk.Combobox(root, textvariable=self.quantity, values=("1", "2", "3"), state="readonly").grid(row=4, column=1, sticky="w", pady=6)
        self.status_box = ScrolledText(root, height=10, wrap="word", state="disabled", background="#292929", foreground="#d9f5ee", relief="flat", padx=10, pady=8)
        self.status_box.grid(row=5, column=0, columnspan=2, sticky="nsew", pady=(12, 0)); root.rowconfigure(5, weight=1)
        buttons = ttk.Frame(root, style="App.TFrame"); buttons.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        ttk.Button(buttons, text="Show matching approved art", command=self.refresh, style="Action.TButton").pack(side="left")
        ttk.Button(buttons, text="Queue new concepts", command=self.queue, style="Action.TButton").pack(side="left", padx=7)
        ttk.Button(buttons, text="Generate next queued concept", command=self.generate, style="Primary.TButton").pack(side="left")
        ttk.Button(buttons, text="Open pending", command=self.open_pending, style="Action.TButton").pack(side="left", padx=7)
        ttk.Button(buttons, text="Approve", command=lambda: self.review_pending("approved"), style="Action.TButton").pack(side="left")
        ttk.Button(buttons, text="Reject", command=lambda: self.review_pending("rejected"), style="Action.TButton").pack(side="left", padx=7)
        ttk.Button(buttons, text="Close", command=self.destroy, style="Action.TButton").pack(side="right")
        self.refresh()

    def _show(self, text: str) -> None:
        self.status_box.configure(state="normal"); self.status_box.delete("1.0", "end"); self.status_box.insert("end", text); self.status_box.configure(state="disabled")

    def refresh(self) -> None:
        index = BackgroundAssetIndex()
        if not index.assets(): index.audit_legacy_library()
        self.pending = [row for row in index.assets() if str(row.get("approval_state") or "").casefold() == "awaiting_review"]
        choices = index.approved_choices(self.topic.get(), limit=8)
        if choices:
            lines = [f"{len(choices)} matching approved background(s) are available now:", ""]
            lines += [f"• {item.get('name')} — {item.get('palette') or 'theme-matched colors'}" for item in choices]
            lines.append("\nThese are eligible for automatic production covers.")
        else:
            lines = ["No approved project background matches this topic yet.", "", "Production will stop at Cover Art Required until you explicitly approve a matching background."]
        if self.pending:
            lines += ["", f"{len(self.pending)} generated background(s) await review.", "Open the newest image, inspect it, then approve or reject that individual asset."]
        self._show("\n".join(lines))

    def open_pending(self) -> None:
        if not getattr(self, "pending", []):
            messagebox.showinfo("Nothing waiting", "There is no generated background awaiting review.", parent=self); return
        path = APP_DIR / str(self.pending[-1].get("path") or "")
        if path.is_file(): os.startfile(path)
        else: messagebox.showwarning("Image missing", "The pending image file could not be found.", parent=self)

    def review_pending(self, decision: str) -> None:
        if not getattr(self, "pending", []):
            messagebox.showinfo("Nothing waiting", "There is no generated background awaiting review.", parent=self); return
        row = self.pending[-1]
        verb = "approve for production" if decision == "approved" else "reject"
        if not messagebox.askyesno("Review background", f"Do you want to {verb} this specific background?\n\n{row.get('name', row.get('asset_id', 'Background'))}", parent=self): return
        from background_generation.service import BackgroundGenerationService
        result = BackgroundGenerationService().review(str(row.get("asset_id") or ""), decision)
        self.refresh(); self.parent_app.status.set(result.message)

    def queue(self) -> None:
        from background_generation.service import BackgroundGenerationService
        jobs = BackgroundGenerationService().enqueue(topic=self.topic.get().strip() or "general puzzle books", palette=self.palette.get().strip(), quantity=int(self.quantity.get()))
        self._show(f"Queued {len(jobs)} original background concept(s). They will stay paused safely until the optional Cloudflare connection is configured.\n\nUse Generate next queued concept when you are ready.")

    def generate(self) -> None:
        from background_generation.service import BackgroundGenerationService
        self._show("Generating and validating the next queued concept…")
        def work():
            result = BackgroundGenerationService().process_next()
            def done():
                self.refresh()
                if result.status == "AWAITING_REVIEW":
                    self.parent_app.status.set("A new background is awaiting your approval before production can use it.")
                elif result.status == "PAUSED":
                    messagebox.showinfo("Background generation paused", result.message + "\n\nYou can connect it in Marketplace connections when ready.", parent=self)
            self.after(0, done)
        threading.Thread(target=work, daemon=True).start()


class CoverChoicesDialog(tk.Toplevel):
    """Focused cover-direction picker used by the main Book Assistant."""

    def __init__(self, app: WordSearchCreator) -> None:
        super().__init__(app)
        self.app = app
        self.title("Choose a Cover Direction")
        self.geometry("760x585")
        self.minsize(640, 500)
        self.transient(app)
        self.grab_set()
        self.note = tk.StringVar(value="Preparing three cover directions from your selected theme…")
        self.preview_specs: list[dict[str, str]] = []
        self.preview_images: list[ImageTk.PhotoImage] = []
        self.preview_folder: Path | None = None
        self._build()
        self._show_cover_options("")

    def _build(self) -> None:
        root = ttk.Frame(self, padding=18, style="App.TFrame")
        root.pack(fill="both", expand=True)
        ttk.Label(root, text="CHOOSE A COVER DIRECTION", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(root, text="These previews use your real title, subtitle, selected theme, and matching artwork. Pick the one that best fits this book.", wraplength=700).pack(anchor="w", pady=(3, 8))
        ttk.Label(root, textvariable=self.note, wraplength=700).pack(anchor="w", pady=(0, 10))
        self.preview_frame = ttk.Frame(root, style="App.TFrame")
        self.preview_frame.pack(fill="both", expand=True)

    def _say(self, text: str) -> None:
        self.note.set(text.replace("\n", " "))

    def _show_cover_options(self, request: str) -> None:
        settings = self.app._studio_cover_settings()
        if not settings:
            self._say("Choose a Word Search theme first so I know what to place on the cover.")
            return
        variants = [
            ("Best Match", settings["palette"], settings["style"], "Uses the recommended topic picture and colors."),
            ("More Playful", "tropical-pop", "playful", "Brighter color and a friendlier illustrated layout."),
            ("More Premium", "midnight-gold", "bold", "A cleaner, higher-contrast collector-style direction."),
        ]
        if any(term in request for term in ("brighter", "colorful", "more")):
            variants[0] = ("Bright Choice", "candy-pop", "sunburst", "A bright, high-energy cover direction.")
        elif any(term in request for term in ("clean", "premium", "minimal")):
            variants[0] = ("Clean Choice", "midnight-gold", "minimal", "A calm, premium, less-busy direction.")
        self._say("Creating three cover previews from your actual title, subtitle, and selected topic. This takes a moment.")
        stamp=datetime.now().strftime("%Y%m%d_%H%M%S")
        self.preview_folder=OUTPUT_DIR / "assistant_cover_choices" / f"{WordSearchCreator._safe_filename(settings['title'])}_{stamp}"
        self.preview_folder.mkdir(parents=True, exist_ok=True)
        self.preview_specs=[]
        for label,palette,style,note in variants:
            option={**settings,"label":label,"palette":palette,"style":style,"note":note,"out":str(self.preview_folder / f"{WordSearchCreator._safe_filename(label)}.png")}
            self.preview_specs.append(option)
        threading.Thread(target=self._render_cover_options, daemon=True).start()

    def _render_cover_options(self) -> None:
        try:
            python = WINDOWS_VENV_PYTHON if WINDOWS_VENV_PYTHON.exists() else Path(sys.executable)
            for option in self.preview_specs:
                command=[str(python),str(COVER_ENGINE),"--title",option["title"],"--subtitle",option["subtitle"],"--author",option["author"],"--badge",option["badge"],"--puzzle-count",str(option.get("puzzle_count", 0)),"--difficulty",option["difficulty"],"--format-label",option.get("format_label","WORD SEARCH"),"--palette",option["palette"],"--style",option["style"],"--theme-file",option["theme"],"--out",option["out"],"--preview"]
                if option.get("art"):
                    command.extend(["--art",option["art"],"--art-focus",option.get("art_focus","center")])
                result=subprocess.run(command,cwd=APP_DIR,capture_output=True,text=True,creationflags=subprocess.CREATE_NO_WINDOW)
                if result.returncode:
                    raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "Cover preview could not be created.")
            self.after(0, self._display_cover_options)
        except Exception as exc:
            self.after(0, lambda: self._say(f"I could not create those cover choices: {exc}"))

    def _display_cover_options(self) -> None:
        for child in self.preview_frame.winfo_children():
            child.destroy()
        self.preview_images=[]
        row=ttk.Frame(self.preview_frame); row.pack(fill="x")
        for option in self.preview_specs:
            card=ttk.Frame(row); card.pack(side="left", fill="both", expand=True, padx=5)
            try:
                image=Image.open(option["out"]); image.thumbnail((180,235),Image.LANCZOS)
                photo=ImageTk.PhotoImage(image); self.preview_images.append(photo)
                ttk.Label(card,image=photo).pack()
            except OSError:
                ttk.Label(card,text="Preview unavailable").pack(pady=50)
            ttk.Label(card,text=option["label"],font=("Segoe UI",10,"bold")).pack(pady=(6,0))
            ttk.Label(card,text=option["note"],wraplength=175,justify="center").pack(pady=(2,6))
            ttk.Button(card,text="Use This Cover",command=lambda value=option:self._choose_cover_option(value),style="Primary.TButton").pack(fill="x")
        actions = ttk.Frame(self.preview_frame, style="App.TFrame"); actions.pack(fill="x", pady=(10, 0))
        ttk.Button(actions, text="Create Reader Preview", command=self._reader_preview, style="Action.TButton").pack(side="left", fill="x", expand=True, padx=(0, 5))
        ttk.Button(actions, text="Close", command=self.destroy, style="Action.TButton").pack(side="left", fill="x", expand=True, padx=(5, 0))
        self._say("Your cover choices are ready. Select the direction you want, then create a reader preview or return to the main assistant to create the package.")

    def _choose_cover_option(self, option: dict[str, str]) -> None:
        self.app.cover_palette.set(option["palette"])
        label=next((name for name,value in PublishReadyDialog.STYLE_MAP.items() if value==option["style"]), "Classic")
        self.app.cover_style.set(label)
        self.app.status.set(f"Book Assistant selected the {option['label']} cover direction.")
        self._say(f"Selected: {option['label']}. You can ask for a reader preview, say “create the full package,” or ask for another direction.")

    def _reader_preview(self) -> None:
        self._say("I’m creating your three-puzzle reader preview now. It will open when it is ready.")
        self.app._generate_reader_preview()


if __name__ == "__main__":
    WordSearchCreator().mainloop()
