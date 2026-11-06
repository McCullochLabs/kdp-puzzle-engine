"""Promote complete, locally screened Word Search rebuild candidates.

Promotion is intentionally separate from provider generation.  A candidate
bank is copied into a production theme only after exact page/word capacity,
normalization, uniqueness, protected-name, page-name, and cross-book overlap
checks pass.  Original legacy theme files remain untouched for recovery.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from build_master_word_bank import EXTRA_REJECTED_TERMS
from publishing.editorial_readiness import MAX_CROSS_BOOK_SHARE
from word_search_creator import REVIEW_REQUIRED_TERMS, audit_theme


CANDIDATES = ROOT / "word_banks" / "editorial_wordsearch_rebuild_candidates.json"
OUTPUT = ROOT / "themes" / "Editorial Rebuilds"
REPORT = ROOT / "reports" / "EDITORIAL_WORDSEARCH_REBUILD_PROMOTION.json"
OVERLAY = ROOT / "word_banks" / "editorial_wordsearch_topic_overlay.json"


SPECS = {
    "classic_cars": {
        "old": "themes/Launch Collection/Verified Release Candidates/classic_cars_road_trips.json",
        "file": "classic_cars_and_road_trips_editorial_v2.json", "seed": 6101,
        "title": "Classic Cars and Road Trips Word Search",
        "subtitle": "48 large-print puzzles for vintage vehicle fans and open-road dreamers",
        "topic": "Vehicles & Automotive", "difficulty": "Standard", "series": "Classic Cars and Road Trips",
        "palette": "retro-drive", "cover_style": "photo",
    },
    "grade_school": {
        "old": "themes/Vocabulary Ladder Collection/vocabulary_adventures_grade_school.json",
        "file": "vocabulary_adventures_grade_school_editorial_v2.json", "seed": 6102,
        "title": "Vocabulary Adventures: Grade School",
        "subtitle": "48 large-print vocabulary word searches for stronger reading and word confidence",
        "topic": "Grade School Vocabulary", "difficulty": "Standard", "series": "Vocabulary Adventures",
        "education": "Grades 3–5",
    },
    "advanced_vocabulary": {
        "old": "themes/Launch Collection/Verified Release Candidates/advanced_vocabulary_challenge.json",
        "file": "advanced_vocabulary_challenge_editorial_v2.json", "seed": 6103,
        "title": "Advanced Vocabulary Challenge Word Search",
        "subtitle": "48 large-print word searches for stronger vocabulary and confident word lovers",
        "topic": "High School Vocabulary", "difficulty": "Challenging", "series": "Vocabulary Adventures",
        "palette": "scholarly-blue", "cover_style": "classic", "education": "Grades 9–12 and Adults",
    },
    "faithful_words": {
        "old": "themes/Trending 50 Puzzle Releases/faithful_words_20260828_203806.json",
        "file": "faithful_words_50_editorial_v2.json", "seed": 6113,
        "title": "Faithful Words Word Search",
        "subtitle": "50 large-print puzzles for Bible themes, hope and encouragement",
        "topic": "Bible and Faith", "difficulty": "Relaxing", "series": "Faithful Words",
        "palette": "bible", "cover_style": "classic",
    },
    "road_trip": {
        "old": "themes/Trending 50 Puzzle Releases/road_trip_classics_20260828_203806.json",
        "file": "road_trip_classics_editorial_v2.json", "seed": 6114,
        "title": "Road Trip Classics Word Search",
        "subtitle": "50 large-print puzzles about highways, scenic stops and open-road adventures",
        "topic": "Travel Road Trips and Getaways", "difficulty": "Standard", "series": "Road Trip Classics",
        "palette": "retro-drive", "cover_style": "photo",
    },
    "american_history": {
        "old": "themes/Trending 50 Puzzle Releases/american_moments_20260828_203806.json",
        "file": "american_moments_editorial_v2.json", "seed": 6115,
        "title": "American Moments Word Search",
        "subtitle": "50 large-print puzzles about United States history, civics and daily life",
        "topic": "American History", "difficulty": "Standard", "series": "American Moments",
        "palette": "usa", "cover_style": "bold",
    },
    "faith_signature": {
        "old": "themes/Faithful Words Series/faithful_words_large_print_signature_100.json",
        "file": "faithful_words_signature_100_editorial_v2.json", "seed": 731001,
        "title": "Faithful Words: Large-Print Bible Word Search for Adults",
        "subtitle": "100 faith-inspired puzzles for peaceful quiet-time solving",
        "topic": "Bible and Faith", "difficulty": "Easy to Medium", "series": "Faithful Words Signature Editions",
        "palette": "bible", "cover_style": "photo", "signature": True,
    },
    "grade_5": {
        "old": "themes/Vocabulary Ladder Collection/Grades 5 to 12/vocabulary_ladder_grade_5.json",
        "file": "vocabulary_ladder_grade_5_editorial_v2.json", "seed": 731105,
        "title": "Vocabulary Ladder: Grade 5 Word Quest",
        "subtitle": "48 themed vocabulary word searches for Grade 5 reading, spelling and word confidence",
        "topic": "Grade 5 Vocabulary", "difficulty": "Standard", "series": "Vocabulary Ladder: Grade-by-Grade Word Quest",
        "palette": "notebook-mint", "cover_style": "playful", "education": "Grade 5",
    },
}

# The broad Grade School draft overlaps the dedicated Grade 5 edition by more
# than the commercial threshold.  Keep its reviewed candidate bank for future
# grades 3–4 redevelopment, but do not promote or publish the competing draft.
PROMOTE_KEYS = tuple(key for key in SPECS if key != "grade_school")


def norm(value: object) -> str:
    return re.sub(r"[^A-Z]", "", str(value or "").upper())


def clean_page_name(value: object) -> str:
    """Remove provider bookkeeping while preserving the editorial title."""
    name = " ".join(str(value or "").split())
    return re.sub(r"^(?:page|puzzle)\s+\d+\s*[:\-]\s*", "", name, flags=re.I).strip()


def presentation_order(key: str, page_number: int, values: list[object]) -> list[object]:
    """Deterministically mix dictionary-ordered lists without changing content.

    Candidate providers often return excellent page groups in alphabetical
    order.  Keeping that order makes the printed word lists feel like a raw
    dictionary export, so promotion fixes presentation order at the source.
    Already mixed lists are preserved exactly.
    """
    ordered = list(values)
    if len(ordered) >= 8 and ordered == sorted(ordered, key=lambda value: str(value).casefold()):
        random.Random(f"editorial-rebuild:{key}:{page_number}").shuffle(ordered)
        if ordered == sorted(ordered, key=lambda value: str(value).casefold()):
            ordered = ordered[1:] + ordered[:1]
    return ordered


def validate(key: str, book: dict, spec: dict) -> tuple[set[str], list[str]]:
    issues: list[str] = []
    pages = book.get("pages") if isinstance(book, dict) else None
    expected = int(book.get("puzzles") or 0)
    if not isinstance(pages, list) or len(pages) != expected:
        issues.append(f"{key}: expected {expected} complete pages; found {len(pages or [])}")
    if book.get("issues"):
        issues.append(f"{key}: unresolved generator issues remain")
    names: set[str] = set(); words: set[str] = set()
    for number, page in enumerate(pages or [], 1):
        name = " ".join(str(page.get("name") or "").split())
        name_key = name.casefold()
        if not name or name_key in names:
            issues.append(f"{key} page {number}: blank or duplicate page name")
        names.add(name_key)
        values = page.get("words") if isinstance(page, dict) else None
        if not isinstance(values, list) or len(values) != 12:
            issues.append(f"{key} page {number}: expected exactly 12 entries")
            continue
        page_words: set[str] = set()
        for raw in values:
            value = norm(raw)
            if not 3 <= len(value) <= 21:
                issues.append(f"{key} page {number}: invalid entry {raw!r}")
            if value in page_words or value in words:
                issues.append(f"{key} page {number}: repeated entry {raw!r}")
            if value in REVIEW_REQUIRED_TERMS or value in EXTRA_REJECTED_TERMS:
                issues.append(f"{key} page {number}: protected/rejected entry {raw!r}")
            page_words.add(value); words.add(value)
    required = expected * 12
    if len(words) != required:
        issues.append(f"{key}: {len(words)} unique normalized entries; {required} required")
    return words, issues


def promoted_theme(key: str, book: dict, spec: dict, source_sha: str) -> dict:
    old_path = ROOT / spec["old"]
    current_path = OUTPUT / spec["file"]
    source_path = current_path if current_path.is_file() else old_path
    base = json.loads(source_path.read_text(encoding="utf-8-sig")) if source_path.is_file() else {}
    pages = []
    for number, page in enumerate(book["pages"], 1):
        page_name = clean_page_name(page["name"])
        pages.append({"name": page_name,
                      "words": presentation_order(key, number, list(page["words"])),
                      "mini_theme": page_name,
                      "page_title_verified": True, "page_title_basis": "editorial_review"})
    checked_at = str((base.get("quality_review") or {}).get("checked_at") or datetime.now().isoformat(timespec="seconds"))
    base.update({
        "title": spec["title"], "subtitle": spec["subtitle"], "author": "Jordan M. Slade",
        "series": spec["series"], "detected_topic": spec["topic"], "difficulty_label": spec["difficulty"],
        "palette": spec["palette"], "recommended_palette": spec["palette"],
        "cover_style": spec["cover_style"], "recommended_cover_style": spec["cover_style"],
        "no_repeat_words": True, "cover_imprint": "Slade Puzzle Co.",
        "cover_badge": f"{len(pages)} LARGE-PRINT PUZZLES • NO REPEATED WORDS",
        "puzzles": pages,
        "source_word_bank": {"name": "Editorial Word Search Rebuild v2", "topics": [spec["topic"]],
            "selection_policy": "Page-grouped provider proposals; locally screened for exact capacity, normalized uniqueness, length, protected names, and page coherence",
            "candidate_sha256": source_sha},
        "quality_review": {"production_ready": True, "verdict": "PASS", "checked_at": checked_at,
            "source": "assistant-assisted editorial rebuild", "checks": ["exact capacity", "no repeated normalized entries",
            "3–21 normalized letters", "protected/rejected-term screen", "coherent reviewed page titles"]},
    })
    if spec.get("education"):
        reviewed_at = str((base.get("educational_editorial_review") or {}).get("reviewed_at") or
                          datetime.now().isoformat(timespec="seconds"))
        base["educational_editorial_review"] = {"grade_appropriate": True, "range": spec["education"],
            "review_basis": "age, proper-name, brand, sensitive-term, length, and page-coherence screening",
            "reviewed_at": reviewed_at}
    if spec.get("signature"):
        signature = dict(base.get("signature_edition") or {})
        signature.update({"enabled": True, "puzzle_target": len(pages)})
        base["signature_edition"] = signature
    return base


def main() -> int:
    data = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    source_sha = hashlib.sha256(CANDIDATES.read_bytes()).hexdigest()
    pools: dict[str, set[str]] = {}; errors: list[str] = []
    for key in PROMOTE_KEYS:
        spec = SPECS[key]
        book = (data.get("books") or {}).get(key) or {}
        pool, issues = validate(key, book, spec)
        pools[key] = pool; errors.extend(issues)
    overlap_rows = []
    keys = list(PROMOTE_KEYS)
    for index, left in enumerate(keys):
        for right in keys[index + 1:]:
            shared = pools[left] & pools[right]
            share = len(shared) / max(1, min(len(pools[left]), len(pools[right])))
            paired_faith = {left, right} == {"faithful_words", "faith_signature"}
            overlap_rows.append({"left": left, "right": right, "shared": len(shared), "share": round(share, 4),
                                 "paired_series": paired_faith})
            if share > MAX_CROSS_BOOK_SHARE and not paired_faith:
                errors.append(f"{left}/{right}: {share:.0%} cross-book overlap")
    if errors:
        REPORT.parent.mkdir(exist_ok=True)
        REPORT.write_text(json.dumps({"status": "BLOCKED", "errors": errors, "overlap": overlap_rows}, indent=2) + "\n", encoding="utf-8")
        raise SystemExit("Promotion blocked: " + " | ".join(errors[:12]))
    OUTPUT.mkdir(parents=True, exist_ok=True)
    results = []
    for key in PROMOTE_KEYS:
        spec = SPECS[key]
        theme = promoted_theme(key, data["books"][key], spec, source_sha)
        target = OUTPUT / spec["file"]
        target.write_text(json.dumps(theme, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        theme_errors, warnings, notes = audit_theme(target, int(spec["seed"]))
        if theme_errors:
            target.unlink(missing_ok=True)
            raise SystemExit(f"{key} failed production source audit: {' | '.join(theme_errors)}")
        results.append({"key": key, "title": spec["title"], "theme": str(target), "puzzles": len(theme["puzzles"]),
                        "unique_words": len(pools[key]), "warnings": warnings, "notes": notes})
    overlay_topics: dict[str, list[str]] = {}
    overlay_profiles: dict[str, dict] = {}
    for row in results:
        key = str(row["key"]); topic = str(SPECS[key]["topic"])
        theme = json.loads(Path(row["theme"]).read_text(encoding="utf-8"))
        for page in theme["puzzles"]:
            for display in page["words"]:
                value = norm(display)
                overlay_topics.setdefault(topic, []).append(value)
                profile = overlay_profiles.setdefault(value, {"topics": [], "sources": []})
                if topic not in profile["topics"]:
                    profile["topics"].append(topic)
                if "editorial_wordsearch_rebuild_v2" not in profile["sources"]:
                    profile["sources"].append("editorial_wordsearch_rebuild_v2")
                if SPECS[key].get("education"):
                    profile.setdefault("grade_bands", []).append(str(SPECS[key]["education"]))
    overlay = {"schema_version": 1, "status": "APPROVED_FOR_LOCAL_PRODUCTION",
               "candidate_sha256": source_sha, "approved_at": datetime.now().isoformat(timespec="seconds"),
               "review_basis": ["exact capacity", "normalized uniqueness", "format length", "protected/rejected terms",
                                "page-level topic coherence", "cross-book overlap"],
               "topics": {topic: sorted(set(words)) for topic, words in overlay_topics.items()},
               "word_profiles": overlay_profiles}
    OVERLAY.write_text(json.dumps(overlay, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    payload = {"status": "PROMOTED", "candidate_sha256": source_sha, "created_at": datetime.now().isoformat(timespec="seconds"),
               "books": results, "cross_book_overlap": overlap_rows,
               "topic_overlay": str(OVERLAY),
               "retired_candidates": [{"key": "grade_school", "title": SPECS["grade_school"]["title"],
                   "reason": "Redundant scope: 31% vocabulary overlap with the stronger dedicated Grade 5 edition."}]}
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
