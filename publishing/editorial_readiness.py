"""Conservative, explainable checks for commercial word-search distinctiveness.

This does not pretend to replace a human editor.  It identifies evidence that
must be resolved before a technically printable book is described as ready for
sale: unsupported education claims and near-duplicate word banks.
"""
from __future__ import annotations

import re
import json
import hashlib
from pathlib import Path


# These are examples already found in active grade-school products.  A short
# exception list alone is not an editorial certification; the grade-source
# review requirement below is intentionally independent of this list.
GRADE_REVIEW_TERMS = frozenset({
    "ARNOLD", "TRUMP", "YAHOO", "BELGIUM", "SCOTLAND", "HOWARD",
    "MONTEREY", "COUP", "DEMON", "CONVICTED",
})
MAX_CROSS_BOOK_SHARE = 0.25


def normalized_word(value: object) -> str:
    return re.sub(r"[^A-Z]", "", str(value or "").upper())


def word_set(source: dict) -> set[str]:
    return {clean for puzzle in source.get("puzzles", []) if isinstance(puzzle, dict)
            for value in puzzle.get("words", []) if (clean := normalized_word(value))}


def is_school_vocabulary(source: dict) -> bool:
    identity = " ".join(str(source.get(key) or "") for key in
                        ("title", "subtitle", "series", "detected_topic")).casefold()
    return any(token in identity for token in ("grade school", "grade 5", "grade 6",
                                                "grade 7", "grade 8", "vocabulary", "word quest"))


def education_review(source: dict) -> list[str]:
    """Require evidence for grade claims; never infer it from word count."""
    if not is_school_vocabulary(source):
        return []
    problems: list[str] = []
    reviewed = source.get("educational_editorial_review")
    if not isinstance(reviewed, dict) or reviewed.get("grade_appropriate") is not True:
        problems.append("Grade/vocabulary suitability has not been editorially approved.")
    odd = sorted(word_set(source) & GRADE_REVIEW_TERMS)
    if odd:
        problems.append("Review questionable school-vocabulary entries: " + ", ".join(odd[:10]) + ".")
    return problems


def overlap_report(left: dict, right: dict) -> dict:
    """Compare two final source banks, using the smaller-book share."""
    a, b = word_set(left), word_set(right)
    shared = a & b
    return {"shared": len(shared), "left_words": len(a), "right_words": len(b),
            "share_of_smaller": round(len(shared) / min(len(a), len(b)), 4) if a and b else 0.0,
            "examples": sorted(shared)[:12]}


def _series_family(source: dict) -> str:
    value = str(source.get("series") or source.get("title") or "").casefold()
    value = re.sub(r"\bsignature\s+editions?\b|\bseries\b|\bword\s+search\b|\bfor\s+adults\b", " ", value)
    return re.sub(r"[^a-z0-9]+", "", value)


def intentional_standard_signature_pair(left: dict, right: dict) -> bool:
    """Recognize a declared standard/Signature pair within one series family."""
    left_signature = bool((left.get("signature_edition") or {}).get("enabled")) or "signature" in str(left.get("title") or "").casefold()
    right_signature = bool((right.get("signature_edition") or {}).get("enabled")) or "signature" in str(right.get("title") or "").casefold()
    left_topic = str(left.get("detected_topic") or "").strip().casefold()
    right_topic = str(right.get("detected_topic") or "").strip().casefold()
    return (left_signature != right_signature and bool(left_topic) and left_topic == right_topic and
            bool(_series_family(left)) and _series_family(left) == _series_family(right))


def editorial_source_path(book: dict) -> Path | None:
    source = str(book.get("source_key") or "").strip()
    path = Path(source) if source else None
    return path if path and path.is_file() and path.suffix.lower() == ".json" else None


def source_editorial_issues(book: dict) -> list[str]:
    path = editorial_source_path(book)
    if path is None:
        return []
    try:
        source = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return ["The source theme cannot be read; repair it before release."]
    review = source.get("quality_review") or {}
    if isinstance(review, dict) and review.get("production_ready") is False:
        return [str(review.get("editorial_hold_reason") or
                    "The source theme needs a curated editorial review before release.")]
    return []


def nonword_package_issues(book: dict) -> list[str]:
    """Use a fingerprinted printed-content audit, never an old PASS sheet."""
    package = Path(str(book.get("package_path") or ""))
    if not package.is_dir():
        return []
    record_path = package / "04_REVIEW_AND_RECORDS" / "PACKAGE_SOURCE_RECORD.json"
    if not record_path.is_file():
        return []
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ["Package source record cannot be read; repair it before release."]
    if record.get("puzzle_type") not in {"Cryptogram", "Mixed Brain Games"}:
        return []
    report_path = package.parents[1] / "reports" / "NONWORD_EDITORIAL_SALE_READINESS.json"
    interior = package / "01_PRINT_UPLOADS" / "interior.pdf"
    if not report_path.is_file() or not interior.is_file():
        return ["Run the printed-content editorial audit before releasing this book."]
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        row = next((item for item in report.get("books", [])
                    if Path(str(item.get("folder") or "")) == package), None)
        digest = hashlib.sha256(interior.read_bytes()).hexdigest()
    except (OSError, ValueError):
        return ["Rerun the printed-content editorial audit; its record cannot be verified."]
    if not row or row.get("interior_sha256") != digest:
        return ["Rerun the printed-content editorial audit after this book changed."]
    return [str(issue) for issue in row.get("issues", [])]
