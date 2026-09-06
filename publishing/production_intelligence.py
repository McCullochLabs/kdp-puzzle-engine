"""Shared production intelligence for every completed local puzzle package.

This module is deliberately local and explainable.  It records what was
checked and never uploads, publishes, edits a finished PDF, or silently
changes a book's creative direction.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageOps, ImageStat
from pypdf import PdfReader
from .package_layout import package_file, proof_folder, release_contract


# The desktop app can run more than one background package task.  Keep its
# tiny shared JSON ledgers serialised in-process and use atomic replacement so
# a stopped task cannot leave a half-written reservations or ledger file.
_STATE_LOCK = threading.RLock()


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(text).casefold())


def _words(source: dict) -> set[str]:
    return {
        re.sub(r"[^A-Z0-9]", "", str(word).upper())
        for puzzle in source.get("puzzles", []) if isinstance(puzzle, dict)
        for word in puzzle.get("words", [])
        if re.sub(r"[^A-Z0-9]", "", str(word).upper())
    }


def _reservation_scope(source: dict) -> dict[str, str]:
    """Return the deliberate no-repeat boundary for a Word Search source.

    A word such as ``TRAIL`` legitimately belongs in a hiking book and a
    national-parks book.  Treating every finished book as one worldwide pool
    made normal, topic-specific production impossible.  We instead protect
    words inside the same declared series; a standalone topic gets its own
    topic-level series automatically.  The source always keeps its own
    within-book no-repeat check elsewhere in the workflow.
    """
    series = " ".join(str(source.get("series") or "").split())
    topic = " ".join(str(source.get("detected_topic") or source.get("topic") or "").split())
    label = series or topic or "Standalone Word Search"
    return {"key": _slug(label), "label": label, "kind": "series" if series else "topic" if topic else "standalone"}


def _read(path: Path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return fallback


def _write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(prefix=f".{path.stem}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def title_assessment(title: str, subtitle: str, topic: str, known_titles: list[str] | None = None) -> dict:
    """A transparent title score - clarity and uniqueness, not sales claims."""
    title = " ".join(str(title).split())
    subtitle = " ".join(str(subtitle).split())
    topic_terms = set(re.findall(r"[a-z0-9]+", str(topic).casefold()))
    title_terms = set(re.findall(r"[a-z0-9]+", title.casefold()))
    notes: list[str] = []
    score = 100
    if not 16 <= len(title) <= 62:
        score -= 18; notes.append("Keep the title between 16 and 62 characters for a cleaner thumbnail.")
    if len(subtitle) > 120:
        score -= 12; notes.append("Shorten the subtitle so it remains readable at storefront size.")
    if topic_terms and not (title_terms & topic_terms):
        score -= 10; notes.append("Add one clear topic word to the title when it improves shopper clarity.")
    known = {_slug(value) for value in (known_titles or []) if value}
    if _slug(title) in known:
        score -= 45; notes.append("This title matches an existing local book title.")
    if not notes:
        notes.append("Title is distinct, concise, and clear enough for a buyer-facing cover.")
    return {"score": max(0, score), "label": "Strong" if score >= 85 else "Review", "notes": notes}


def cover_assessment(front: Path) -> dict:
    """Check real image dimensions and create a small buyer-view thumbnail."""
    if not front.is_file():
        return {"score": 0, "notes": ["Front-cover image is missing."], "thumbnail": ""}
    try:
        with Image.open(front) as raw:
            image = raw.convert("RGB")
            width, height = image.size
            thumb = ImageOps.contain(image, (420, 630), Image.Resampling.LANCZOS)
            target = proof_folder(front.parents[1] if front.parent.name == "03_PREVIEWS" else front.parent, create=True) / "buyer_thumbnail.png"
            target.parent.mkdir(parents=True, exist_ok=True)
            thumb.save(target, "PNG")
    except OSError as exc:
        return {"score": 0, "notes": [f"Front cover could not be inspected: {exc}"], "thumbnail": ""}
    score = 100 if width >= 2550 and height >= 3300 else 55
    notes = [f"Print cover is {width} x {height} pixels.", "Buyer-size thumbnail was refreshed for visual review."]
    if score < 100:
        notes.append("Re-export the cover at print size before handoff.")
    return {"score": score, "notes": notes, "thumbnail": str(target)}


def _cover_type(value: object) -> str:
    """Normalize display labels without treating different puzzle types alike."""
    text = re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()
    aliases = {"word search": "word_search", "wordsearch": "word_search",
               "word scramble trivia": "scramble_trivia", "scramble trivia": "scramble_trivia",
               "mixed brain games": "mixed", "brain games": "mixed"}
    return aliases.get(text, text.replace(" ", "_"))


def _cover_manifest(folder: Path) -> dict:
    value = _read(package_file(folder, "PACKAGE_SOURCE_RECORD.json"), {})
    return value if isinstance(value, dict) else {}


def _image_visual_metrics(path: Path) -> dict:
    """Small explainable image signals. They flag review work, not aesthetics."""
    try:
        with Image.open(path) as raw:
            image = raw.convert("RGB").resize((96, 124), Image.Resampling.LANCZOS)
            variance = sum(ImageStat.Stat(image).var) / 3.0
            pixels = list(image.get_flattened_data())
            bright = sum(1 for red, green, blue in pixels if red >= 245 and green >= 245 and blue >= 245) / max(1, len(pixels))
        return {"variance": round(variance, 2), "bright_fraction": round(bright, 3)}
    except OSError as exc:
        return {"error": type(exc).__name__}


def visual_quality_assessment(project: Path | str, folder: Path | str, source: dict, *, plan=None,
                              asset_index=None) -> dict:
    """Run explainable visual release checks using real cover and source evidence.

    Objective cover/interior mismatches block. Visual signals request review;
    they never edit a cover or pretend to replace a human visual decision.
    """
    project, folder = Path(project), Path(folder)
    manifest = _cover_manifest(folder)
    facts = {**manifest, **{key: value for key, value in (source or {}).items() if value not in (None, "")}}
    title, subtitle = str(facts.get("title") or "").strip(), str(facts.get("subtitle") or "").strip()
    topic = str(facts.get("detected_topic") or facts.get("theme") or "").strip()
    declared_type = _cover_type(manifest.get("cover_puzzle_type") or manifest.get("puzzle_type"))
    source_type = _cover_type(facts.get("puzzle_type"))
    expected_type = _cover_type(getattr(plan, "puzzle_type", "") or source_type)
    expected_count = int((getattr(plan, "format", {}) or {}).get("puzzle_count") or facts.get("puzzle_count") or 0)
    declared_count = int(manifest.get("puzzle_count") or facts.get("puzzle_count") or 0)
    expected_difficulty = str((getattr(plan, "format", {}) or {}).get("difficulty") or facts.get("difficulty") or "").strip().casefold()
    declared_difficulty = str(manifest.get("difficulty") or facts.get("difficulty") or "").strip().casefold()
    checks: list[dict] = []

    def add(check_id: str, severity: str, passed: bool, message: str, **evidence) -> None:
        checks.append({"check_id": check_id, "severity": severity, "passed": bool(passed), "message": message, "evidence": evidence})

    if expected_count:
        if not declared_count:
            add("cover.copy.puzzle_count", "needs_review", False,
                "Cover package does not record its puzzle-count promise; confirm the count badge on the rendered cover manually.",
                expected=expected_count)
        else:
            add("cover.copy.puzzle_count", "hard_fail", declared_count == expected_count,
                "Cover/package puzzle count matches the Book Plan." if declared_count == expected_count else f"Cover/package says {declared_count} puzzles; the Book Plan requires {expected_count}.",
                declared=declared_count, expected=expected_count)
    if expected_type:
        if not declared_type:
            add("cover.visual.puzzle_type", "needs_review", False, "This package does not record the puzzle type used to render its cover. Confirm that the cover graphic matches the interior.", expected=expected_type)
        else:
            add("cover.visual.puzzle_type", "hard_fail", declared_type == expected_type,
                "Recorded cover puzzle type matches the interior." if declared_type == expected_type else f"Recorded cover puzzle type is {declared_type}; interior type is {expected_type}.", declared=declared_type, expected=expected_type)
    if expected_difficulty:
        if not declared_difficulty:
            add("cover.copy.difficulty", "needs_review", False, "Cover package does not record its difficulty promise; confirm any difficulty label on the cover manually.", expected=expected_difficulty)
        else:
            add("cover.copy.difficulty", "hard_fail", declared_difficulty == expected_difficulty,
                "Recorded cover difficulty matches the Book Plan." if declared_difficulty == expected_difficulty else f"Cover/package difficulty is {declared_difficulty}; Book Plan difficulty is {expected_difficulty}.", declared=declared_difficulty, expected=expected_difficulty)
    add("cover.copy.title_hierarchy", "needs_review", len(title) <= 62 and len(subtitle) <= 120,
        "Title and subtitle are within the thumbnail-readability limits." if len(title) <= 62 and len(subtitle) <= 120 else "Title or subtitle is too long for a dependable storefront thumbnail; simplify the hierarchy.",
        title_length=len(title), subtitle_length=len(subtitle))

    front = package_file(folder, "front_cover.png")
    metrics = _image_visual_metrics(front) if front.is_file() else {"error": "missing"}
    if "error" in metrics:
        add("cover.visual.image_health", "hard_fail", False, "Final front-cover image cannot be inspected.", **metrics)
    else:
        sparse = float(metrics["variance"]) < 18
        add("cover.visual.sparse_composition", "needs_review", not sparse,
            "Cover has enough visual variation for an automated sparse-cover screen." if not sparse else "Cover appears unusually flat or sparse. Review it at thumbnail size before release.", **metrics)

    art_raw = str(manifest.get("cover_art") or facts.get("cover_art") or "").strip()
    if art_raw:
        art = Path(art_raw)
        if not art.is_absolute(): art = project / art
        try:
            from background_generation.index import BackgroundAssetIndex, require_production_approved_cover_asset
            index = asset_index or BackgroundAssetIndex()
            asset = require_production_approved_cover_asset(art, index=index)
        except Exception as exc:
            asset = None; index = None; approval_error = str(exc)
        if not asset or index is None:
            add("cover.art.approval", "hard_fail", False, "Cover art is not currently production-approved.", art=str(art), reason=locals().get("approval_error", "unknown approval"))
        else:
            brief = index.cover_brief({"title": title, "subtitle": subtitle, "detected_topic": topic, "puzzle_type": expected_type})
            score = int(index._topic_score(asset, brief))
            add("cover.art.topic_match", "needs_review", score >= 12,
                "Approved background has a recorded topic match." if score >= 12 else "Approved background has no meaningful recorded match to this book topic.",
                asset_id=asset.get("asset_id", ""), score=score, asset_topics=list(asset.get("topics") or []))
            education = {"grade", "school", "student", "education", "classroom", "learning", "vocabulary"}
            context = set(re.findall(r"[a-z0-9]+", f"{title} {topic}".casefold()))
            asset_terms = set(re.findall(r"[a-z0-9]+", " ".join([str(asset.get("name") or ""), *[str(x) for x in asset.get("topics") or []]]).casefold()))
            if context & education:
                educational_art = bool(asset_terms & (education - {"vocabulary"}))
                add("cover.art.audience_context", "needs_review", educational_art,
                    "Background includes recorded school/learning context." if educational_art else "This school/grade-focused book uses art without a recorded school or learning context. Review the subject fit.",
                    requested_context=sorted(context & education), asset_terms=sorted(asset_terms & education))
    else:
        add("cover.art.approval", "hard_fail", False, "No production-approved background-art record is attached to this package.")

    theme_path = Path(str(manifest.get("source_theme") or ""))
    theme_data = _read(theme_path, {}) if theme_path.is_file() else {}
    series_source = {**facts, **(theme_data if isinstance(theme_data, dict) else {})}
    if str(series_source.get("series") or "").strip():
        direction = series_direction(project, series_source)
        expected_palette, expected_style = str(direction.get("palette") or "").casefold(), str(direction.get("style") or "").casefold()
        actual_palette = str(manifest.get("palette") or facts.get("palette") or "").casefold()
        actual_style = str(manifest.get("cover_layout") or manifest.get("cover_style") or facts.get("cover_style") or "").casefold()
        matches = (not expected_palette or actual_palette == expected_palette) and (not expected_style or actual_style == expected_style)
        add("cover.series.direction", "needs_review", matches,
            "Cover direction matches the current local series family." if matches else "Cover palette or layout differs from the established local series direction. Confirm that this is intentional.",
            expected_palette=expected_palette, expected_style=expected_style, actual_palette=actual_palette, actual_style=actual_style)

    preview = folder / "03_PREVIEWS" / "kdp_full_wrap_preview.png"
    if preview.is_file():
        wrap_metrics = _image_visual_metrics(preview)
        prominent = float(wrap_metrics.get("bright_fraction") or 0) > .22
        add("wrap.barcode_balance", "needs_review", not prominent,
            "Full-wrap preview does not show an unusually large bright safe area." if not prominent else "Full-wrap preview has a large bright safe area. Check that the barcode area does not make the back look unfinished.", **wrap_metrics)
    else:
        add("wrap.barcode_balance", "warning", False, "No full-wrap preview image is available for the automated barcode-balance screen.")
    hard = [row["message"] for row in checks if not row["passed"] and row["severity"] == "hard_fail"]
    review = [row["message"] for row in checks if not row["passed"] and row["severity"] == "needs_review"]
    return {"checks": checks, "hard_failures": hard, "needs_review": review,
            "warnings": [row["message"] for row in checks if not row["passed"] and row["severity"] == "warning"], "ready": not hard and not review}


def cover_concept_score(title: str, palette: str, layout: str) -> dict:
    """Rank saved directions for clarity before committing them to a cover."""
    score = 70
    notes: list[str] = []
    if 16 <= len(" ".join(str(title).split())) <= 62:
        score += 15
    else:
        notes.append("A shorter title will be easier to read at thumbnail size.")
    if str(palette).strip() and str(palette).casefold() != "automatic":
        score += 8
    else:
        notes.append("Choose a palette before treating this as a final direction.")
    if str(layout).strip() and str(layout).casefold() != "automatic":
        score += 7
    else:
        notes.append("Choose a layout before treating this as a final direction.")
    return {"score": min(100, score), "notes": notes or ["Clear, complete direction ready for a visual cover test."]}


def pdf_assessment(pdf: Path, expected_pages: int | None = None) -> dict:
    """Structural PDF review: readable file, consistent trim, and blank-page signal."""
    if not pdf.is_file():
        return {"ok": False, "notes": [f"Missing {pdf.name}."], "pages": 0}
    try:
        reader = PdfReader(str(pdf))
        pages = len(reader.pages)
        sizes = {(round(float(page.mediabox.width), 1), round(float(page.mediabox.height), 1)) for page in reader.pages}
        blank = sum(1 for page in reader.pages if not (page.extract_text() or "").strip())
    except Exception as exc:
        return {"ok": False, "notes": [f"Could not read {pdf.name}: {exc}"], "pages": 0}
    notes = [f"{pdf.name} opens with {pages} page(s).", f"{len(sizes)} page size(s) detected."]
    if expected_pages is not None and pages != int(expected_pages):
        notes.append(f"Expected {expected_pages} pages but found {pages}.")
    if blank:
        notes.append(f"{blank} page(s) have no extractable text; visually confirm intentional art-only pages.")
    ok = len(sizes) == 1 and (expected_pages is None or pages == int(expected_pages))
    return {"ok": ok, "notes": notes, "pages": pages, "sizes": sorted(sizes), "blank_pages": blank}


def marketplace_assets(front: Path) -> list[str]:
    """Create local listing visuals from the already approved front cover."""
    if not front.is_file():
        return []
    target = front.parent / "marketplace_assets"
    target.mkdir(exist_ok=True)
    specs = {
        "amazon_listing_cover.png": (1600, 2560),
        "etsy_listing_cover.png": (2000, 2000),
        "social_square.png": (1200, 1200),
        "pinterest_pin.png": (1000, 1500),
    }
    made: list[str] = []
    with Image.open(front) as raw:
        image = raw.convert("RGB")
        for name, size in specs.items():
            canvas = Image.new("RGB", size, "#f4f1ea")
            fitted = ImageOps.contain(image, size, Image.Resampling.LANCZOS)
            canvas.paste(fitted, ((size[0] - fitted.width) // 2, (size[1] - fitted.height) // 2))
            output = target / name
            canvas.save(output, "PNG", optimize=True)
            made.append(str(output))
    return made


def mark_cover_dependents_stale(folder: Path, reason: str) -> Path:
    """Record the cover-only follow-up without touching puzzle content.

    Marketplace copies of a cover are deliberately not silently overwritten:
    some may have been human-reviewed.  This small, visible marker tells the
    Publishing Manager which cover-dependent artifacts need a refresh.
    """
    folder = Path(folder)
    target = folder / "04_REVIEW_AND_RECORDS" / "COVER_DEPENDENCY_REFRESH_NEEDED.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "COVER DEPENDENCY REFRESH NEEDED\n" + "=" * 48 + "\n\n" +
        f"Reason: {reason}\n\n"
        "Refresh these cover-dependent deliverables before a new marketplace handoff:\n"
        "• KDP / print full-wrap cover\n• Barnes & Noble, Lulu, IngramSpark, and BookVault cover references\n"
        "• Payhip, Etsy, website, and marketing listing images\n"
        "• A+ Content and any human-approved product images\n\n"
        "Interior PDFs, puzzle source, solutions, and listing copy were not changed.\n",
        encoding="utf-8",
    )
    return target


def _reservations_path(project: Path) -> Path:
    target = project / "data" / "word_reservations.json"
    target.parent.mkdir(exist_ok=True)
    return target


def _ledger_path(project: Path) -> Path:
    target = project / "data" / "production_ledger.json"
    target.parent.mkdir(exist_ok=True)
    return target


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _record_ledger(project: Path, folder: Path, report: dict) -> None:
    with _STATE_LOCK:
        path = _ledger_path(project)
        data = _read(path, {"packages": []})
        rows = [item for item in data.get("packages", []) if isinstance(item, dict) and item.get("package") != str(folder)]
        files = {}
        for name in ("interior.pdf", "kdp_full_wrap.pdf", "front_cover.png"):
            item = package_file(folder, name)
            if item.is_file():
                files[name] = _sha256(item)
        rows.insert(0, {"created": report["created"], "title": report["title"], "package": str(folder), "ready": report["ready"], "files": files, "marketplace_assets": report["marketplace_assets"], "reserved_words": report["word_reservation"].get("words", 0)})
        _write_json_atomic(path, {"packages": rows[:500]})


def reservation_check(project: Path, title: str, source: dict) -> dict:
    """Find exact word reuse inside the same intentional series boundary."""
    reservations = _read(_reservations_path(project), {"books": []})
    books = reservations.get("books", []) if isinstance(reservations, dict) else []
    own = _words(source)
    scope = _reservation_scope(source)
    conflicts: list[dict] = []
    for record in books:
        if not isinstance(record, dict) or _slug(record.get("title", "")) == _slug(title):
            continue
        # Older ledgers did not store a scope, and therefore cannot safely be
        # treated as a global ban on ordinary vocabulary.  They remain in the
        # audit file, while all new reservations explicitly declare their
        # protected series/topic boundary.
        if str(record.get("scope_key") or "") != scope["key"]:
            continue
        other = set(record.get("words", []))
        shared = sorted(own & other)
        if shared:
            conflicts.append({"title": str(record.get("title") or "Previous book"), "count": len(shared), "examples": shared[:8]})
    return {"words": len(own), "scope": scope, "conflicts": conflicts, "ready": not conflicts}


def reserve_words(project: Path, title: str, source: dict, package: Path) -> dict:
    with _STATE_LOCK:
        check = reservation_check(project, title, source)
        if not check["ready"]:
            return check
        path = _reservations_path(project)
        data = _read(path, {"books": []})
        books = [item for item in data.get("books", []) if isinstance(item, dict) and _slug(item.get("title", "")) != _slug(title)]
        scope = _reservation_scope(source)
        books.append({"title": title, "package": str(package), "reserved_at": datetime.now().isoformat(timespec="seconds"), "words": sorted(_words(source)), "scope_key": scope["key"], "scope_label": scope["label"], "scope_kind": scope["kind"]})
        _write_json_atomic(path, {"books": books})
        return check


def remaining_capacity(project: Path, source: dict) -> dict:
    """Report known unused words in the selected source topic when available."""
    bank = _read(Path(project) / "word_banks" / "Guided_Builder_Master_Word_Bank.json", {})
    topics = bank.get("topics", {}) if isinstance(bank, dict) else {}
    topic = str(source.get("detected_topic") or "")
    # Use the exact same normalisation as the no-repeat reservation store.
    # Without this, phrases such as "OLD FASHIONED" were counted as available
    # after "OLDFASHIONED" had already been reserved in another book.
    base = _words({"puzzles": [{"words": topics.get(topic, [])}]})
    if not base:
        return {"available": None, "message": "This source is not mapped to one exact Master Library topic yet."}
    reservations = _read(_reservations_path(Path(project)), {"books": []})
    scope = _reservation_scope(source)
    consumed = {
        word for record in reservations.get("books", []) if isinstance(record, dict)
        and str(record.get("scope_key") or "") == scope["key"]
        for word in record.get("words", [])
    }
    available = len(base - {str(word) for word in consumed})
    return {"available": available, "scope": scope, "message": f"{available} unused linked words remain in the {scope['label']} {scope['kind']} pool."}


def series_direction(project: Path, source: dict) -> dict:
    """Suggest continuity from existing local series without changing a theme."""
    series = str(source.get("series") or "").strip()
    if not series:
        return {"message": "No series is set; this book may use its own matched cover direction."}
    palettes: list[str] = []; styles: list[str] = []
    for path in (Path(project) / "themes").rglob("*.json"):
        data = _read(path, {})
        if str(data.get("series") or "").casefold() == series.casefold():
            if data.get("palette"): palettes.append(str(data["palette"]))
            if data.get("cover_style"): styles.append(str(data["cover_style"]))
    palette = max(set(palettes), key=palettes.count) if palettes else ""
    style = max(set(styles), key=styles.count) if styles else ""
    return {"palette": palette, "style": style, "message": f"Series continuity: {palette or 'automatic palette'} / {style or 'automatic layout'}."}


def finalize_package(project: Path, folder: Path, source: dict, title: str, subtitle: str = "", expected_pages: int | None = None) -> dict:
    """Run final local checks and make marketplace assets after PDFs exist."""
    project, folder = Path(project), Path(folder)
    known_titles = [str(item.get("title") or "") for item in _read(_reservations_path(project), {"books": []}).get("books", []) if isinstance(item, dict)]
    title_report = title_assessment(title, subtitle, str(source.get("detected_topic") or source.get("theme") or ""), known_titles)
    interior = pdf_assessment(package_file(folder, "interior.pdf"), expected_pages)
    wrap = pdf_assessment(package_file(folder, "kdp_full_wrap.pdf"), 1)
    cover = cover_assessment(package_file(folder, "front_cover.png"))
    visual = visual_quality_assessment(project, folder, source)
    contract = release_contract(folder)
    reservation = reservation_check(project, title, source) if source.get("puzzles") else {"ready": True, "words": 0, "conflicts": []}
    assets = marketplace_assets(package_file(folder, "front_cover.png"))
    capacity = remaining_capacity(project, source)
    series = series_direction(project, source)
    blockers: list[str] = []
    if not interior["ok"]: blockers.append("Interior PDF inspection needs attention.")
    if not wrap["ok"]: blockers.append("Full-wrap PDF inspection needs attention.")
    if cover["score"] < 100: blockers.append("Front cover does not meet the expected print dimensions.")
    blockers.extend(visual["hard_failures"])
    if not contract["ready"]: blockers.append("Package release contract is incomplete: " + ", ".join(contract["missing"]))
    if not reservation["ready"]: blockers.append("This book reuses reserved words from a finalized book.")
    report = {"created": datetime.now().isoformat(timespec="seconds"), "title": title, "title_assessment": title_report,
              "interior": interior, "wrap": wrap, "cover": cover, "release_contract": contract, "word_reservation": reservation,
              "remaining_capacity": capacity, "series_direction": series, "marketplace_assets": assets,
              "visual_quality": visual, "ready": not blockers, "blockers": blockers,
              "attention_required": visual["needs_review"] + visual["warnings"]}
    package_file(folder, "PRODUCTION_INTELLIGENCE.json", for_write=True).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    package_file(folder, "COVER_VISUAL_QUALITY_REPORT.json", for_write=True).write_text(json.dumps(visual, indent=2) + "\n", encoding="utf-8")
    if report["ready"] and source.get("puzzles"):
        reserve_words(project, title, source, folder)
    if report["ready"]:
        _record_ledger(project, folder, report)
        # Every passing package gets the same clear master handoff.  The
        # builder only copies/links verified final files; it never modifies
        # the interior or cover that just passed validation.
        from .master_package import build_master_package
        build_master_package(folder, {
            "title": title, "subtitle": subtitle, "author": str(source.get("author") or "Jordan M. Slade"),
            "trim_size": str(source.get("trim_size") or "8.5x11"), "page_count": interior["pages"],
            "puzzle_count": int(source.get("puzzle_count") or len(source.get("puzzles") or [])),
        })
    return report
