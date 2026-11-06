"""Read-only editorial triage of active word-search packages and their peers."""
from __future__ import annotations

import json
import hashlib
import re
import sys
from datetime import datetime
from pathlib import Path
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from publishing.editorial_readiness import (
    MAX_CROSS_BOOK_SHARE, education_review, intentional_standard_signature_pair, overlap_report,
)
from word_intelligence.pipeline import load_or_build_store, load_taxonomy
from word_intelligence.theme_audit import audit_theme
from publishing.editorial_readiness import normalized_word
from publishing.package_layout import package_file


def pdf_source_check(folder: Path, source: dict) -> dict:
    """Compare printed word-list entries, not incidental grid letters."""
    interior = package_file(folder, "interior.pdf")
    if not interior.is_file():
        return {"matched": False, "checked": 0, "mismatched_puzzles": [], "error": "interior PDF missing"}
    puzzles = source.get("puzzles") or []
    found: dict[int, list[str]] = {}
    for page in PdfReader(str(interior)).pages:
        text = page.extract_text() or ""
        if "FIND THESE WORDS" not in text:
            continue
        number = re.search(r"\bPUZZLE\s+(\d+)\b", text, flags=re.I)
        if not number:
            continue
        index = int(number.group(1))
        if not 1 <= index <= len(puzzles):
            continue
        expected_count = len(puzzles[index - 1].get("words") or [])
        after = text.split("FIND THESE WORDS", 1)[1]
        raw = [line.strip() for line in after.splitlines() if line.strip()]
        found[index] = [normalized_word(value) for value in raw[:expected_count]]
    mismatches = []
    for index, puzzle in enumerate(puzzles, 1):
        expected = {normalized_word(word) for word in puzzle.get("words") or []}
        actual = set(found.get(index, []))
        if not expected or actual != expected:
            mismatches.append(index)
    return {"matched": len(found) == len(puzzles) and not mismatches,
            "checked": len(found), "expected": len(puzzles),
            "mismatched_puzzles": mismatches[:30]}


def active_sources(out: Path) -> list[tuple[Path, Path, dict]]:
    found = []
    for folder in sorted(out.iterdir()):
        if not folder.is_dir() or folder.name.startswith("_"):
            continue
        record_path = next(iter(folder.glob("**/PACKAGE_SOURCE_RECORD.json")), None)
        if not record_path:
            continue
        record = json.loads(record_path.read_text(encoding="utf-8"))
        if record.get("puzzle_type") != "Word Search":
            continue
        source_path = Path(str(record.get("source_theme") or ""))
        if source_path.is_file():
            found.append((folder, source_path, record))
    return found


def legacy_samples(out: Path) -> list[dict]:
    """Inventory standalone samples without pretending they have a source manifest."""
    sample_root = out / "3_6 Complete Product Audit Samples"
    rows = []
    if not sample_root.is_dir():
        return rows
    for folder in sorted(sample_root.iterdir()):
        interior = folder / "interior.pdf"
        if not folder.is_dir() or not interior.is_file():
            continue
        reader = PdfReader(str(interior))
        first = reader.pages[0].extract_text() or ""
        puzzle_count = sum("FIND THESE WORDS" in (page.extract_text() or "") for page in reader.pages)
        claims = [int(number) for number in re.findall(r"\b(\d+)\s+(?:festive\s+holiday\s+word\s+search\s+)?puzzles\b", first, re.I)]
        issues = ["No source manifest or current editorial sign-off; treat this as an archival sample."]
        if any(claim != puzzle_count for claim in claims):
            issues.append(f"Title page claims {claims} puzzles but the interior contains {puzzle_count} puzzle pages.")
        rows.append({"folder": str(folder), "title_page": first[:300], "interior_pages": len(reader.pages),
                     "puzzle_pages": puzzle_count, "title_page_count_claims": claims,
                     "issues": issues, "status": "EDITORIAL HOLD", "sale_ready": False})
    return rows


def catalog_report(project: Path, *, use_topic_audit: bool = True) -> dict:
    sources = active_sources(project / "out")
    if use_topic_audit:
        taxonomy = load_taxonomy(project)
        loaded = load_or_build_store(taxonomy, project)
        store = loaded[0] if isinstance(loaded, tuple) else loaded
    else:
        taxonomy = store = None
    rows = []
    for folder, path, record in sources:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        row = {
            "package": str(folder), "source": str(path),
            "title": str(record.get("title") or data.get("title") or folder.name),
            "puzzles": len(data.get("puzzles") or []),
            "education_issues": education_review(data),
            "overlap_issues": [],
            "source_editorial_hold": str((data.get("quality_review") or {}).get("editorial_hold_reason") or "")
            if (data.get("quality_review") or {}).get("production_ready") is False else "",
        }
        current_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        recorded_hash = str(record.get("source_theme_sha256") or "").lower()
        row["source_fingerprint_matches"] = bool(recorded_hash and recorded_hash == current_hash)
        row["pdf_source_check"] = pdf_source_check(folder, data)
        if store is not None:
            audit = audit_theme(data, str(path), store, taxonomy)
            counts: dict[str, int] = {}
            for finding in audit.findings:
                counts[finding.status] = counts.get(finding.status, 0) + 1
            row["topic_audit"] = {"verdict": audit.verdict, "target": audit.target_topics,
                                  "resolution": audit.target_resolution, "counts": counts,
                                  "notes": audit.notes,
                                  "examples_to_review": [f.to_dict() for f in audit.findings
                                                         if f.status in {"flagged", "off_topic", "weak", "unverified"}][:20]}
        rows.append((row, data))
    pairs = []
    for i, (left, a) in enumerate(rows):
        for right, b in rows[i + 1:]:
            comparison = overlap_report(a, b)
            paired_series = intentional_standard_signature_pair(a, b)
            if comparison["shared"]:
                pairs.append({"books": [left["title"], right["title"]],
                              "intentional_standard_signature_pair": paired_series, **comparison})
            if comparison["share_of_smaller"] > MAX_CROSS_BOOK_SHARE and not paired_series:
                note = f"Shares {comparison['shared']} words ({comparison['share_of_smaller']:.0%} of the smaller book) with "
                left["overlap_issues"].append(note + right["title"] + ".")
                right["overlap_issues"].append(note + left["title"] + ".")
    result = []
    for row, _source in rows:
        topic = row.get("topic_audit") or {}
        hard = (row["source_editorial_hold"] or row["education_issues"] or row["overlap_issues"] or
                not row["pdf_source_check"]["matched"] or
                topic.get("verdict") in {"FAIL", "REVIEW_REQUIRED"} or
                (topic.get("counts") or {}).get("flagged", 0) > 0)
        row["status"] = "EDITORIAL HOLD" if hard else "NEEDS HUMAN EDITORIAL SIGN-OFF"
        row["sale_ready"] = False
        result.append(row)
    return {"generated": datetime.now().isoformat(timespec="seconds"),
            "scope": "active word-search packages only; non-word puzzle review remains separate",
            "books": result, "pairs": sorted(pairs, key=lambda pair: pair["share_of_smaller"], reverse=True),
            "standalone_legacy_samples": legacy_samples(project / "out"),
            "editorial_holds": sum(row["status"] == "EDITORIAL HOLD" for row in result),
            "sale_ready": 0,
            "note": "Technical PDF preflight does not certify topic fit, grade level, differentiation, rights, or a printed proof. Master Library topic-audit PASS verifies existing links, not independent editorial relevance."}


def main() -> None:
    report = catalog_report(ROOT)
    target = ROOT / "reports" / "EDITORIAL_SALE_READINESS.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Active word searches: {len(report['books'])}; editorial holds: {report['editorial_holds']}; sale-ready: 0")
    print(f"Standalone legacy samples: {len(report['standalone_legacy_samples'])}; all require reconstruction from a current source.")
    for row in report["books"]:
        counts = (row.get("topic_audit") or {}).get("counts") or {}
        print(f"{row['status']}: {row['title']} | topic {row.get('topic_audit',{}).get('verdict','n/a')} | "
              f"flagged {counts.get('flagged',0)} off-topic {counts.get('off_topic',0)} "
              f"weak {counts.get('weak',0)} unverified {counts.get('unverified',0)} | "
              f"education {len(row['education_issues'])} overlap {len(row['overlap_issues'])} | "
              f"PDF/source {'MATCH' if row['pdf_source_check']['matched'] else 'MISMATCH'} | "
              f"record fingerprint {'MATCH' if row['source_fingerprint_matches'] else 'STALE'}")
    print(target)


if __name__ == "__main__":
    main()
