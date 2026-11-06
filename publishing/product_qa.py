"""Unified local prepress inspection over the existing proof and QA helpers."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import re
import math
from pathlib import Path
from time import perf_counter

from pypdf import PdfReader
from PIL import Image

from .package_layout import package_file, release_contract
from .production_intelligence import pdf_assessment, visual_quality_assessment, _pdf_assessment_details

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
    def visitor(text, cm, tm, _font, size):
        if str(text).strip():
            from pypdf import mult
            matrix = mult(tm, cm)
            sizes.append(float(size or 0)*math.hypot(matrix[2],matrix[3]))
            positions.append((float(matrix[4]),float(matrix[5]),str(text).strip()[:80]))
    try:
        page.extract_text(visitor_text=visitor)
    except Exception:
        return {"font_sizes": [], "positions": [], "error": "text geometry unavailable"}
    return {"font_sizes": sizes, "positions": positions}


def _format_minimum(puzzle_type: str) -> float:
    return {"word_search": 8.0, "sudoku": 9.0, "cryptogram": 8.0,
            "scramble_trivia": 8.0, "mixed": 8.0}.get(puzzle_type, 7.0)


def rendered_page_metrics(pdf):
    """PDFium glyph bounds include transformations and actual text extents."""
    import pypdfium2 as pdfium
    document = pdfium.PdfDocument(str(pdf))
    result = []
    try:
        for page in document:
            text = page.get_textpage()
            boxes = []
            try:
                for index in range(text.count_chars()):
                    char = text.get_text_range(index,1)
                    if char.strip():
                        box = text.get_charbox(index)
                        if box[2]>box[0] and box[3]>box[1]:
                            boxes.append((char,*box))
                result.append(dict(width=page.get_width(),height=page.get_height(),glyphs=boxes))
            finally:
                text.close(); page.close()
    finally:
        document.close()
    return result


def inspect_product(project: Path | str, package: Path | str, metadata: dict | None = None, *, plan=None,
                    asset_index=None) -> ProductQAReport:
    """Inspect existing rendered artifacts without editing or approving them."""
    started = perf_counter(); project, root, metadata = Path(project), Path(package), dict(metadata or {})
    findings: list[ProductQAFinding] = []
    def add(check_id, area, severity, passed, message, page=0, **evidence):
        findings.append(ProductQAFinding(check_id, area, severity, bool(passed), message, int(page), evidence))

    coverage = metadata.get('vocabulary_coverage')
    if isinstance(coverage,dict):
        fraction=float(coverage.get('reviewed_library_coverage',0))
        scoped_complete=False
        if coverage.get('editorial_reference_path'):
            review_errors=[]
            try:
                from .grade7_editorial import validate_review
                review_path=Path(coverage['editorial_reference_path'])
                if hashlib.sha256(review_path.read_bytes()).hexdigest()!=coverage.get('editorial_reference_sha256'):
                    review_errors.append('Editorial evidence fingerprint is stale.')
                source_path=Path(metadata['editorial_source_path'])
                source=json.loads(source_path.read_text(encoding='utf-8'))
                review=json.loads(review_path.read_text(encoding='utf-8'))
                review_errors.extend(validate_review(review,source,source_path))
                scoped_complete=not review_errors
            except Exception as exc:
                review_errors.append(f'Editorial evidence could not be verified: {type(exc).__name__}.')
            add('content.provisional_reference_review','Content',BLOCKER,scoped_complete,
                'All 300 targets and 25 prompts have source-bound provisional editorial evidence.' if scoped_complete else '; '.join(review_errors))
        message=(f'Existing-library coverage is {fraction:.1%}; its gaps have book-specific provisional review and glossary support.' if scoped_complete else
                 f'Existing-library vocabulary review covers {fraction:.1%}; unknown or unreviewed terms need editorial review.')
        add('content.reviewed_coverage','Content',INFO if scoped_complete else WARNING,fraction>=.95 or scoped_complete,
            message,
            unknown_words=coverage.get('unknown_words',[]),unreviewed_words=coverage.get('unreviewed_words',[]),
            basis=coverage.get('basis',''))
        if scoped_complete:
            add('content.teacher_review','Content',WARNING,False,
                'Teacher approval remains pending; provisional reference review does not grant human signoff.')

    structural_start = perf_counter(); contract = release_contract(root)
    add("package.contract", "Package", BLOCKER, bool(contract.get("ready")),
        "Required package files are present." if contract.get("ready") else "Required package files are missing: " + ", ".join(contract.get("missing") or []), **contract)
    rights = package_file(root, "COVER_ART_RIGHTS_LEDGER.txt")
    add("package.provenance", "Package", BLOCKER, rights.is_file(),
        "Cover provenance record is present." if rights.is_file() else "Cover art rights/provenance record is missing.")
    source_record = package_file(root, "PACKAGE_SOURCE_RECORD.json")
    add("package.source_record", "Package", BLOCKER, source_record.is_file(),
        "Package source record is present." if source_record.is_file() else "Package source record is missing.")

    interior = package_file(root, "interior.pdf"); pdf, inspected_reader, extracted_texts = _pdf_assessment_details(interior)
    add("interior.readable", "Interior", BLOCKER, bool(pdf.get("ok")), "; ".join(pdf.get("notes") or []), **{key: pdf.get(key) for key in ("pages", "sizes", "blank_pages")})
    from .sudoku_typography import configured_package_typography
    try:
        typography=configured_package_typography(root)
    except (OSError,ValueError) as exc:
        add('interior.typography_binding','Interior',BLOCKER,False,str(exc))
    else:
        if typography is not None:
            add('interior.typography_binding','Interior',BLOCKER,True,
                'Configured puzzle typography matches its saved PDF and puzzle-manifest binding.',
                configuration=typography.to_dict())
    texts, sampled, intentional_blanks = [], [], {int(value) for value in metadata.get("intentional_blank_pages", []) if str(value).isdigit()}
    if interior.is_file():
        try:
            # Reuse only this invocation's completed structural inspection.
            # On failure retain the independent legacy read/error path below.
            reader = inspected_reader if inspected_reader is not None else PdfReader(str(interior))
            texts = [" ".join(text.split()) for text in extracted_texts] if extracted_texts is not None else [_normalized_text(page) for page in reader.pages]
            sampled = _sample_pages(texts)
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
            tiny, near_edge, unresolved_positions = [], [], []
            for index in sampled:
                page = reader.pages[index]; metrics = _text_metrics(page)
                sizes_on_page = [value for value in metrics.get("font_sizes", []) if value > 0]
                if sizes_on_page and min(sizes_on_page) < threshold:
                    tiny.append({"page": index + 1, "minimum": round(min(sizes_on_page), 1), "recommended": threshold})
                width, height = float(page.mediabox.width), float(page.mediabox.height)
                for x, y, text in metrics.get("positions", []):
                    # pypdf occasionally reports (0, 0) for centered ReportLab
                    # text even though the glyphs are inside the page. Keep this
                    # visible for manual review; do not call it a proven edge hit.
                    if x == 0 and y == 0:
                        unresolved_positions.append({"page": index + 1, "text": text})
                        continue
                    if x < 9 or y < 9 or x > width - 9 or y > height - 9:
                        near_edge.append({"page": index + 1, "x": round(x, 1), "y": round(y, 1), "text": text}); break
            add("puzzle.type_legibility", "Puzzle", WARNING, not tiny,
                "Sampled text meets the puzzle-type size screen." if not tiny else "Some sampled text is smaller than the format-specific review threshold.", samples=tiny)
            add("interior.safe_area", "Interior", BLOCKER, not near_edge,
                "Sampled text remains outside the critical trim-edge zone." if not near_edge else "Sampled text enters the critical trim-edge zone.", samples=near_edge)
            uncertain_pages = sorted({item["page"] for item in unresolved_positions})
            uncertain_text = ", ".join(repr(item["text"][:30]) for item in unresolved_positions[:2])
            position_message = (
                "All sampled text positions could be measured." if not unresolved_positions else
                f"PDF text coordinates are unavailable on page(s) {', '.join(map(str, uncertain_pages))} "
                f"for {uncertain_text}. Visually inspect those pages and use the print previewer; "
                "this is not a confirmed margin defect."
            )
            add("interior.unresolved_text_positions", "Interior", WARNING, not unresolved_positions,
                position_message, samples=unresolved_positions[:20])
            # Legacy files remain reviewable; new builds can require mathematical proof.
            manifest_path = interior.with_suffix('.puzzles.json')
            if not manifest_path.is_file():
                manifest_path = package_file(root,'PUZZLE_MANIFEST.json')
            required_manifest = bool(metadata.get('require_puzzle_manifest'))
            manifest_errors = []
            manifest = None
            if manifest_path.is_file():
                try:
                    from .puzzle_integrity import verify_manifest
                    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
                    manifest_errors = verify_manifest(interior,manifest,len(reader.pages))
                    expected_count = metadata.get('puzzle_count')
                    if expected_count is not None and int(expected_count)!=manifest.get('puzzle_count'):
                        manifest_errors.append('Declared puzzle count differs from the recorded count.')
                    for row in manifest.get('puzzles',[]):
                        for field in ('puzzle_page','solution_page'):
                            page_number = row.get(field,0)
                            heading = row.get('puzzle_heading' if field=='puzzle_page' else 'solution_heading')
                            matched = (' '.join(heading.split()).casefold() in texts[page_number-1].casefold()) if heading and 1<=page_number<=len(texts) else (1<=page_number<=len(texts) and re.search(r'\b(?:PUZZLE|SOLUTION)\s+'+str(row['number'])+r'\b',texts[page_number-1],re.I))
                            if not matched:
                                manifest_errors.append(f"Puzzle {row['number']}: numbered heading missing on {field}.")
                        # Text-based games need their actual answers checked too.
                        if row['type'] in ('cryptogram','scramble_trivia'):
                            puzzle_text=''.join(texts[row['puzzle_page']-1].split()).casefold()
                            solution_text=''.join(texts[row['solution_page']-1].split()).casefold()
                            if row['type']=='cryptogram':
                                question,answer=row['ciphertext'],row['plaintext']
                            else:
                                question,answer=row['scrambled'],row['solution_word']
                                fact=''.join(row['solution_fact_answer'].split()).casefold()
                                same_answer = re.sub(r'[^a-z0-9]', '', fact) == re.sub(r'[^a-z0-9]', '', answer.casefold())
                                if not same_answer and fact not in solution_text:
                                    manifest_errors.append(f"Puzzle {row['number']}: printed fact answer differs from its record.")
                            if ''.join(question.split()).casefold() not in puzzle_text or ''.join(answer.split()).casefold() not in solution_text:
                                manifest_errors.append(f"Puzzle {row['number']}: printed question or answer differs from its record.")
                except Exception as exc:
                    manifest_errors.append(f'Puzzle verification failed: {exc}')
            else:
                manifest_errors.append('Puzzle-by-puzzle evidence is missing; an answer-section heading does not prove completeness.')
            add('puzzle.answer_integrity','Puzzle',BLOCKER if manifest_path.is_file() or required_manifest else WARNING,
                not manifest_errors,'Every puzzle and answer was independently verified.' if not manifest_errors else '; '.join(manifest_errors[:12]))
            from .pdf_print_screen import scan_pdf
            print_screen = scan_pdf(interior)
            thin = [row for row in print_screen['strokes'] if row['status'] == 'BELOW_MINIMUM']
            unresolved = print_screen['unsupported'] + [row for row in print_screen['strokes'] if row['status'] == 'ORIENTATION_DEPENDENT']
            add('interior.print_strokes', 'Interior', BLOCKER, not thin,
                'Painted vector strokes meet the 0.75pt print minimum.' if not thin else f'{len(thin)} painted vector strokes are below the 0.75pt print minimum.',
                samples=thin[:20], pages=sorted({row['page'] for row in thin}))
            add('interior.minimum_font', 'Interior', BLOCKER, not print_screen['font_below_7pt_samples'],
                'Actual text meets the 7pt print minimum.' if not print_screen['font_below_7pt_samples'] else 'Actual text below the 7pt print minimum needs repair.',
                samples=print_screen['font_below_7pt_samples'][:20])
            add('interior.print_screen_coverage', 'Interior', WARNING, not unresolved and not print_screen['font_extraction_errors'],
                'Vector/text print screen completed; raster and physical-proof review remain separate.' if not unresolved else 'Some graphics transforms or visibility cases require manual print review.',
                unresolved=unresolved[:20], font_errors=print_screen['font_extraction_errors'])
            geometry = rendered_page_metrics(interior)
            if manifest:
                from .puzzle_integrity import verify_rendered_grids
                rendered=verify_rendered_grids(manifest,geometry)
                add('puzzle.rendered_correspondence','Puzzle',BLOCKER,not rendered['errors'],
                    'Actual PDF cell glyphs match their verified puzzle and solution records.' if not rendered['errors'] else '; '.join(rendered['errors'][:12]),**rendered)
                if rendered['unmeasured_symbol_puzzles']:
                    add('puzzle.symbol_correspondence','Puzzle',WARNING,False,
                        'Vector-only Sudoku symbols require visual correspondence review.',puzzles=rendered['unmeasured_symbol_puzzles'])
            glyph_edge, gutter_hits, profile_small = [], [], []
            # Project's established conservative interior margins; no new printer dimensions.
            margin = float(metadata.get('content_margin_pt',54))
            profile = str(metadata.get('reader_profile') or metadata.get('interior_profile') or 'standard')
            profile_min = {'ages_6_8':16, 'ages_9_12':14, 'grade_7':14, 'memories_large_print_v1':18}.get(profile,12 if metadata.get('large_print') else 0)
            page_roles = {}
            if manifest:
                for row in manifest.get('puzzles',[]):
                    page_roles.setdefault(row.get('puzzle_page'),[]).append(('puzzle',row))
                    page_roles.setdefault(row.get('solution_page'),[]).append(('solution',row))
            for index, page_metrics in enumerate(geometry,1):
                width,height=page_metrics['width'],page_metrics['height']
                for char,left,bottom,right,top in page_metrics['glyphs']:
                    if left<9 or bottom<9 or right>width-9 or top>height-9:
                        glyph_edge.append(index); break
                # Headers/footers are excluded vertically, but body glyph extents are checked in full.
                for char,left,bottom,right,top in page_metrics['glyphs']:
                    if 54 <= bottom <= height-54 and (left < margin-1 or right>width-margin+1):
                        gutter_hits.append(index); break
                for region in (manifest or {}).get('layout_regions',[]):
                    if region['page']!=index: continue
                    role=region['role']
                    from .studio_reader_profiles import READER_PROFILES
                    reader_rules=READER_PROFILES.get(profile,{})
                    required = 9 if role=='solution' else max(reader_rules.get('minimum_word_font_pt',12) if role=='word_list' else reader_rules.get('minimum_grid_font_pt',14),profile_min)
                    left,bottom,right,top=region['bounds']
                    glyphs=[g for g in page_metrics['glyphs'] if g[0].isalnum() and
                            left<=g[1]<=right and bottom<=g[2] and g[4]<=top]
                    # Glyph height is measured independently of declared font size.
                    # Half the font size is a conservative screen for normal Latin glyphs.
                    if not glyphs or float(region['font_pt'])<required or any(g[4]-g[2]<required*.5 for g in glyphs):
                        profile_small.append(dict(page=index,role=role,declared_pt=region['font_pt'],required_pt=required))
            if manifest and not manifest.get('layout_regions'):
                profile_small.append(dict(reason='No role-specific layout regions were recorded.'))
            add('interior.glyph_safe_area','Interior',BLOCKER,not glyph_edge,
                'All pages checked for glyphs crossing the critical edge zone.', pages=sorted(set(glyph_edge)))
            add('interior.body_margins','Interior',WARNING,not gutter_hits,
                'All-page body text bounds checked against declared content margins.',pages=sorted(set(gutter_hits)),margin_pt=margin)
            add('puzzle.reader_legibility','Puzzle',WARNING,not profile_small,
                'Reader-specific puzzle and solution font sizes checked.',samples=profile_small)
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
