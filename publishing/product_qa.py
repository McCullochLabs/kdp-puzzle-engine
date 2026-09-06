"""Unified local prepress inspection over the existing proof and QA helpers."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import re
from pathlib import Path
from time import perf_counter

from pypdf import PdfReader
from PIL import Image

from .package_layout import package_file, release_contract
from .production_intelligence import pdf_assessment, visual_quality_assessment

BLOCKER = "BLOCKER"
WARNING = "WARNING"
INFO = "INFO"


@dataclass(frozen=True)
class ProductQAFinding:
    check_id: str
    area: str
    severity: str
    passed: bool
    message: str
    page: int = 0
    evidence: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ProductQAReport:
    package: str
    status: str
    generated_at: str
    findings: tuple[ProductQAFinding, ...]
    sampled_pages: tuple[int, ...]
    timing_ms: dict[str, float]

    @property
    def blockers(self) -> tuple[ProductQAFinding, ...]:
        return tuple(row for row in self.findings if not row.passed and row.severity == BLOCKER)

    @property
    def warnings(self) -> tuple[ProductQAFinding, ...]:
        return tuple(row for row in self.findings if not row.passed and row.severity == WARNING)

    def to_dict(self) -> dict:
        return {"package": self.package, "status": self.status, "generated_at": self.generated_at,
                "findings": [row.to_dict() for row in self.findings], "sampled_pages": list(self.sampled_pages),
                "summary": {"blockers": len(self.blockers), "warnings": len(self.warnings),
                            "passed": sum(row.passed for row in self.findings)}, "timing_ms": self.timing_ms}


def _normalized_text(page) -> str:
    return " ".join((page.extract_text() or "").split())


def _sample_pages(texts: list[str]) -> list[int]:
    total = len(texts)
    if not total:
        return []
    puzzle = [index for index, text in enumerate(texts) if any(term in text.upper() for term in ("PUZZLE", "SUDOKU", "CRYPTOGRAM", "UNSCRAMBLE", "TRIVIA")) and "SOLUTION" not in text.upper()]
    solutions = [index for index, text in enumerate(texts) if "SOLUTION" in text.upper() or "ANSWER KEY" in text.upper()]
    dividers = [index for index, text in enumerate(texts) if len(text.split()) <= 18 and any(term in text.upper() for term in ("SECTION", "PART ", "PUZZLES", "SOLUTIONS"))]
    def three(values):
        return [] if not values else [values[0], values[len(values) // 2], values[-1]]
    return sorted(set([0, total // 2, total - 1, *three(puzzle), *three(solutions), *dividers[:6]]))


def _text_metrics(page) -> dict:
    sizes, positions = [], []
    def visitor(text, _cm, tm, _font, size):
        if str(text).strip():
            sizes.append(float(size or 0)); positions.append((float(tm[4]), float(tm[5]), str(text).strip()[:80]))
    try:
        page.extract_text(visitor_text=visitor)
    except Exception:
        return {"font_sizes": [], "positions": [], "error": "text geometry unavailable"}
    return {"font_sizes": sizes, "positions": positions}


def _format_minimum(puzzle_type: str) -> float:
    return {"word_search": 8.0, "sudoku": 9.0, "cryptogram": 8.0,
            "scramble_trivia": 8.0, "mixed": 8.0}.get(puzzle_type, 7.0)


def inspect_product(project: Path | str, package: Path | str, metadata: dict | None = None, *, plan=None,
                    asset_index=None) -> ProductQAReport:
    """Inspect existing rendered artifacts without editing or approving them."""
    started = perf_counter(); project, root, metadata = Path(project), Path(package), dict(metadata or {})
    findings: list[ProductQAFinding] = []
    def add(check_id, area, severity, passed, message, page=0, **evidence):
        findings.append(ProductQAFinding(check_id, area, severity, bool(passed), message, int(page), evidence))

    structural_start = perf_counter(); contract = release_contract(root)
    add("package.contract", "Package", BLOCKER, bool(contract.get("ready")),
        "Required package files are present." if contract.get("ready") else "Required package files are missing: " + ", ".join(contract.get("missing") or []), **contract)
    rights = package_file(root, "COVER_ART_RIGHTS_LEDGER.txt")
    add("package.provenance", "Package", BLOCKER, rights.is_file(),
        "Cover provenance record is present." if rights.is_file() else "Cover art rights/provenance record is missing.")
    source_record = package_file(root, "PACKAGE_SOURCE_RECORD.json")
    add("package.source_record", "Package", BLOCKER, source_record.is_file(),
        "Package source record is present." if source_record.is_file() else "Package source record is missing.")

    interior = package_file(root, "interior.pdf"); pdf = pdf_assessment(interior)
    add("interior.readable", "Interior", BLOCKER, bool(pdf.get("ok")), "; ".join(pdf.get("notes") or []), **{key: pdf.get(key) for key in ("pages", "sizes", "blank_pages")})
    texts, sampled, intentional_blanks = [], [], {int(value) for value in metadata.get("intentional_blank_pages", []) if str(value).isdigit()}
    if interior.is_file():
        try:
            reader = PdfReader(str(interior)); texts = [_normalized_text(page) for page in reader.pages]; sampled = _sample_pages(texts)
            expected_trim = str(metadata.get("trim_size") or "8.5x11").replace(" ", "").lower()
            expected = {"8.5x11": (612, 792), "8x10": (576, 720), "6x9": (432, 648)}.get(expected_trim)
            sizes = {(round(float(page.mediabox.width)), round(float(page.mediabox.height))) for page in reader.pages}
            add("interior.trim", "Interior", BLOCKER, expected is None or sizes == {expected},
                "Interior trim dimensions are consistent." if expected is None or sizes == {expected} else f"Interior dimensions {sorted(sizes)} do not match declared trim {expected_trim}.", expected=expected, actual=sorted(sizes))
            unexpected_blank = [index + 1 for index, text in enumerate(texts) if not text and (index + 1) not in intentional_blanks]
            add("interior.blank_pages", "Interior", WARNING, not unexpected_blank,
                "No unexpected text-empty pages were found." if not unexpected_blank else f"Review {len(unexpected_blank)} text-empty page(s); art-only pages may be intentional.", pages=unexpected_blank[:30])
            digest_pages = {}
            for index, text in enumerate(texts):
                if len(text) >= 80:
                    digest_pages.setdefault(hashlib.sha256(text.casefold().encode()).hexdigest(), []).append(index + 1)
            duplicates = [pages for pages in digest_pages.values() if len(pages) > 1]
            add("interior.duplicate_pages", "Interior", WARNING, not duplicates,
                "No duplicate substantial page text was found." if not duplicates else "Substantial page text repeats exactly; confirm these are intentional recurring instructions.", groups=duplicates[:20])
            has_solution = any("SOLUTION" in text.upper() or "ANSWER KEY" in text.upper() for text in texts)
            add("puzzle.solutions", "Puzzle", BLOCKER, has_solution,
                "A solution/answer section was detected." if has_solution else "No solution or answer-key section was detected.")
            threshold = _format_minimum(str(metadata.get("puzzle_type_id") or metadata.get("puzzle_type") or "word_search"))
            tiny, near_edge = [], []
            for index in sampled:
                page = reader.pages[index]; metrics = _text_metrics(page)
                sizes_on_page = [value for value in metrics.get("font_sizes", []) if value > 0]
                if sizes_on_page and min(sizes_on_page) < threshold:
                    tiny.append({"page": index + 1, "minimum": round(min(sizes_on_page), 1), "recommended": threshold})
                width, height = float(page.mediabox.width), float(page.mediabox.height)
                for x, y, text in metrics.get("positions", []):
                    if x < 9 or y < 9 or x > width - 9 or y > height - 9:
                        near_edge.append({"page": index + 1, "x": round(x, 1), "y": round(y, 1), "text": text}); break
            add("puzzle.type_legibility", "Puzzle", WARNING, not tiny,
                "Sampled text meets the puzzle-type size screen." if not tiny else "Some sampled text is smaller than the format-specific review threshold.", samples=tiny)
            add("interior.safe_area", "Interior", BLOCKER, not near_edge,
                "Sampled text remains outside the critical trim-edge zone." if not near_edge else "Sampled text enters the critical trim-edge zone.", samples=near_edge)
        except Exception as exc:
            add("interior.sample_inspection", "Interior", BLOCKER, False, f"Rendered-page sampling failed: {exc}")
    structural_ms = (perf_counter() - structural_start) * 1000

    cover_start = perf_counter(); front = package_file(root, "front_cover.png")
    try:
        with Image.open(front) as image:
            width, height = image.size; image.verify()
        cover_ok = width >= 2550 and height >= 3300
        cover_message = f"Front cover is {width} × {height} pixels."
    except Exception as exc:
        cover_ok, cover_message, width, height = False, f"Front cover could not be inspected: {exc}", 0, 0
    add("cover.print_dimensions", "Cover", BLOCKER, cover_ok, cover_message, width=width, height=height)
    try:
        from background_generation.index import verify_rendered_cover_approval
        approval_ok, approval_reason, approval_proof = verify_rendered_cover_approval(front, index=asset_index)
    except Exception as exc:
        approval_ok, approval_reason, approval_proof = False, f"cover approval could not be verified ({type(exc).__name__})", {}
    add("cover.production_approval", "Cover", BLOCKER, approval_ok,
        "Cover uses a current production-approved asset." if approval_ok else "Cover approval is missing or stale: " + approval_reason,
        asset_id=approval_proof.get("asset_id", ""), asset_sha256=approval_proof.get("asset_sha256", ""),
        approval_revision=approval_proof.get("approval_revision", ""), provenance=approval_proof.get("provenance") or {})
    visual = visual_quality_assessment(project, root, metadata, plan=plan, asset_index=asset_index)
    for row in visual.get("checks") or []:
        severity = BLOCKER if row["severity"] == "hard_fail" else WARNING if row["severity"] in {"needs_review", "warning"} else INFO
        add(row["check_id"], "Cover", severity, row["passed"], row["message"], **dict(row.get("evidence") or {}))
    reuse = int(metadata.get("cover_art_use_count") or 0); intentional_series = bool(metadata.get("series"))
    add("cover.art_reuse", "Cover", INFO if intentional_series else WARNING, reuse <= 3 or intentional_series,
        "Artwork reuse is within the normal local range." if reuse <= 3 else "This artwork has been used unusually often; confirm intentional series consistency.", uses=reuse, intentional_series=intentional_series)
    cover_ms = (perf_counter() - cover_start) * 1000

    blockers = [row for row in findings if not row.passed and row.severity == BLOCKER]
    warnings = [row for row in findings if not row.passed and row.severity == WARNING]
    status = "QA Blocked" if blockers else "QA Needs Review" if warnings else "QA Passed Locally"
    return ProductQAReport(str(root), status, datetime.now(timezone.utc).isoformat(timespec="seconds"),
                           tuple(findings), tuple(index + 1 for index in sampled),
                           {"structural_and_pages": round(structural_ms, 2), "cover": round(cover_ms, 2),
                            "total": round((perf_counter() - started) * 1000, 2)})


def write_product_qa_report(path: Path | str, report: ProductQAReport) -> Path:
    target = Path(path); target.parent.mkdir(parents=True, exist_ok=True)
    lines = ["PRODUCT QA", "=" * 56, "", f"LOCAL STATUS: {report.status}",
             f"BLOCKERS: {len(report.blockers)}", f"WARNINGS: {len(report.warnings)}",
             f"Sampled pages: {', '.join(map(str, report.sampled_pages)) or 'none'}", "", "CHECKS"]
    for row in report.findings:
        marker = "PASS" if row.passed else row.severity
        page = f" — page {row.page}" if row.page else ""
        lines.append(f"• {marker} — {row.area}: {row.message}{page}")
    lines += ["", "This is a local prepress review. It does not approve rights or certify acceptance by any marketplace."]
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    json_path = target.with_suffix(".json"); json_path.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target
