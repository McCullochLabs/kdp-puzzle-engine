import json

from PIL import Image
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from publishing.package_layout import initialize_package_layout, package_file
from publishing.product_qa import BLOCKER, WARNING, inspect_product, write_product_qa_report
from publishing.title_pages import TitlePageSpec, render_title_page
from background_generation.index import BackgroundAssetIndex, file_sha256, write_cover_approval_proof


def _approve_front(tmp_path, front):
    art = tmp_path / "approved_art.png"; Image.new("RGB", (900, 900), "#285a73").save(art)
    row = {"asset_id": "approved-fixture", "path": str(art), "topics": ["test"],
           "classification": "APPROVED_PROJECT_GENERATED", "approval_state": "approved",
           "production_approved": True, "project_generated": True, "sha256": file_sha256(art),
           "provenance": {"provider": "SladePuzzleCo project generation"}}
    BackgroundAssetIndex().save({"assets": [row]}); write_cover_approval_proof(front, row)


import pytest
@pytest.fixture(autouse=True)
def isolated_cover_registry(tmp_path, monkeypatch):
    monkeypatch.setenv("SLADE_COVER_ASSET_REGISTRY", str(tmp_path / "cover_registry.json"))


def make_pdf(path, pages, size=letter, font_size=12, edge=False):
    pdf = canvas.Canvas(str(path), pagesize=size)
    for text in pages:
        if text:
            pdf.setFont("Helvetica", font_size)
            pdf.drawString(2 if edge else 54, 54, text)
        pdf.showPage()
    pdf.save()


def package(tmp_path, interior_pages=None, size=letter, font_size=12, edge=False):
    root = tmp_path / "book"; initialize_package_layout(root)
    make_pdf(package_file(root, "interior.pdf", for_write=True), interior_pages or ["PUZZLE 1 ALPHA BETA", "SOLUTION 1 ALPHA BETA"], size, font_size, edge)
    make_pdf(package_file(root, "kdp_full_wrap.pdf", for_write=True), ["FRONT BACK SPINE"])
    Image.new("RGB", (2550, 3300), "#276b65").save(package_file(root, "front_cover.png", for_write=True))
    _approve_front(tmp_path, package_file(root, "front_cover.png"))
    package_file(root, "KDP_LISTING_KIT.txt", for_write=True).write_text("Listing", encoding="utf-8")
    package_file(root, "PUBLISHER_PREFLIGHT.txt", for_write=True).write_text("PASS", encoding="utf-8")
    package_file(root, "PACKAGE_SOURCE_RECORD.json", for_write=True).write_text(json.dumps({
        "title": "Test Puzzle Book", "subtitle": "A local QA fixture", "puzzle_type": "word_search",
        "cover_puzzle_type": "word_search", "puzzle_count": 1, "difficulty": "standard",
        "cover_art": str(tmp_path / "approved_art.png"),
    }), encoding="utf-8")
    package_file(root, "COVER_ART_RIGHTS_LEDGER.txt", for_write=True).write_text("Local fixture", encoding="utf-8")
    package_file(root, "PRODUCTION_PROOF_GATE.txt", for_write=True).write_text("PASS", encoding="utf-8")
    return root


def failed(report, check_id):
    return next(row for row in report.findings if row.check_id == check_id and not row.passed)


def test_good_structure_has_no_structural_blocker(tmp_path):
    report = inspect_product(tmp_path, package(tmp_path), {"trim_size": "8.5x11", "puzzle_type_id": "word_search"})
    assert not [row for row in report.blockers if row.area in {"Interior", "Puzzle", "Package"}]
    assert report.status in {"QA Needs Review", "QA Passed Locally"}, [(row.check_id, row.message) for row in report.blockers]


def test_incorrect_trim_is_blocker(tmp_path):
    report = inspect_product(tmp_path, package(tmp_path, size=(432, 648)), {"trim_size": "8.5x11"})
    assert failed(report, "interior.trim").severity == BLOCKER


def test_missing_solution_is_blocker(tmp_path):
    report = inspect_product(tmp_path, package(tmp_path, ["PUZZLE 1 ALPHA BETA", "PUZZLE 2 GAMMA DELTA"]), {"trim_size": "8.5x11"})
    assert failed(report, "puzzle.solutions").severity == BLOCKER


def test_unexpected_blank_page_is_warning_but_intentional_blank_is_allowed(tmp_path):
    root = package(tmp_path, ["PUZZLE 1", "", "SOLUTION 1"])
    first = inspect_product(tmp_path, root, {"trim_size": "8.5x11"})
    assert failed(first, "interior.blank_pages").severity == WARNING
    second = inspect_product(tmp_path, root, {"trim_size": "8.5x11", "intentional_blank_pages": [2]})
    assert next(row for row in second.findings if row.check_id == "interior.blank_pages").passed


def test_tiny_text_and_trim_edge_are_format_specific_findings(tmp_path):
    report = inspect_product(tmp_path, package(tmp_path, font_size=5, edge=True), {"trim_size": "8.5x11", "puzzle_type_id": "sudoku"})
    assert failed(report, "puzzle.type_legibility").severity == WARNING
    assert failed(report, "interior.safe_area").severity == BLOCKER


def test_centered_title_parser_origin_is_review_note_not_false_trim_blocker(tmp_path):
    root = package(tmp_path)
    interior = package_file(root, "interior.pdf", for_write=True)
    pdf = canvas.Canvas(str(interior), pagesize=letter)
    render_title_page(pdf, TitlePageSpec(
        "Journeys Near and Far Scramble and Trivia",
        "60 travel word scrambles and quick facts for curious explorers",
        "Jordan M. Slade", puzzle_type="Word Scramble + Trivia",
        topic="Travel & Adventure", puzzle_count=60, style="themed_emblem",
    ))
    pdf.setFont("Helvetica", 12)
    pdf.drawString(54, 700, "PUZZLE 1")
    pdf.drawString(54, 650, "ANSWER KEY")
    pdf.showPage()
    pdf.save()
    report = inspect_product(tmp_path, root, {"trim_size": "8.5x11"})
    assert not [row for row in report.blockers if row.check_id == "interior.safe_area"]
    warning = failed(report, "interior.unresolved_text_positions")
    assert warning.severity == WARNING
    assert "page(s) 1" in warning.message
    assert "print previewer" in warning.message


def test_duplicate_substantial_pages_are_flagged(tmp_path):
    repeated = "PUZZLE 1 " + "ALPHA BETA GAMMA DELTA " * 8
    report = inspect_product(tmp_path, package(tmp_path, [repeated, repeated, "SOLUTION 1"]), {"trim_size": "8.5x11"})
    assert failed(report, "interior.duplicate_pages").severity == WARNING


def test_report_writer_uses_local_not_marketplace_approval_language(tmp_path):
    report = inspect_product(tmp_path, package(tmp_path), {"trim_size": "8.5x11"})
    path = write_product_qa_report(tmp_path / "PRODUCT_QA.txt", report)
    text = path.read_text(encoding="utf-8")
    assert "LOCAL STATUS" in text
    assert "KDP Approved" not in text
    assert path.with_suffix(".json").is_file()


def test_reused_art_is_warning_unless_it_is_intentional_series_consistency(tmp_path):
    root = package(tmp_path)
    ordinary = inspect_product(tmp_path, root, {"trim_size": "8.5x11", "cover_art_use_count": 8})
    assert failed(ordinary, "cover.art_reuse").severity == WARNING
    series = inspect_product(tmp_path, root, {"trim_size": "8.5x11", "cover_art_use_count": 8, "series": "A Real Series"})
    reuse = next(row for row in series.findings if row.check_id == "cover.art_reuse")
    assert reuse.passed


def test_completed_text_inspection_reused_without_normalized_reextraction(tmp_path, monkeypatch):
    import publishing.product_qa as module
    root=package(tmp_path, ['PUZZLE 1  ALPHA BETA', '', 'SOLUTION 1 ALPHA BETA'])
    def unexpected(page):
        pytest.fail('Successful structural inspection text was extracted again')
    monkeypatch.setattr(module, '_normalized_text', unexpected)
    report=inspect_product(tmp_path,root,{'trim_size':'8.5x11','puzzle_type_id':'word_search'})
    assert next(f for f in report.findings if f.check_id=='interior.readable').passed
    assert failed(report,'interior.blank_pages').evidence['pages']==[2]
    assert next(f for f in report.findings if f.check_id=='puzzle.solutions').passed


def test_structural_failure_retains_independent_read_path(tmp_path, monkeypatch):
    import publishing.product_qa as module
    root=package(tmp_path);calls=[];original=module._normalized_text
    monkeypatch.setattr(module,'_pdf_assessment_details',lambda path:({'ok':False,'notes':['fixture structural failure'],'pages':0},None,None))
    monkeypatch.setattr(module,'_normalized_text',lambda page:(calls.append(True),original(page))[1])
    report=inspect_product(tmp_path,root,{'trim_size':'8.5x11','puzzle_type_id':'word_search'})
    assert len(calls)==2
    assert not next(f for f in report.findings if f.check_id=='interior.readable').passed
    assert next(f for f in report.findings if f.check_id=='puzzle.solutions').passed


@pytest.mark.parametrize("drift", [None, "binding", "manifest", "pdf", "config", "source"])
def test_configured_typography_binding_is_explicit_qa_gate(tmp_path, drift):
    from publishing.sudoku_typography import SudokuTypography, bind_typography
    root = package(tmp_path)
    pdf = package_file(root, "interior.pdf")
    source = package_file(root, "PACKAGE_SOURCE_RECORD.json")
    data = json.loads(source.read_text(encoding="utf-8"))
    data.update(puzzle_type="Sudoku", sudoku_typography=SudokuTypography(puzzle_font_pt=34).to_dict())
    source.write_text(json.dumps(data), encoding="utf-8")
    pdf.with_suffix(".puzzles.json").write_text("{}", encoding="utf-8")
    bind_typography(pdf, SudokuTypography(puzzle_font_pt=34))
    if drift == "binding": pdf.with_suffix(".typography.json").unlink()
    if drift == "manifest": pdf.with_suffix(".puzzles.json").write_text('{"changed":true}', encoding="utf-8")
    if drift == "pdf": make_pdf(pdf, ["Changed puzzle", "Changed solution"])
    if drift == "config":
        data["sudoku_typography"]["puzzle_font_pt"] = 33
        source.write_text(json.dumps(data), encoding="utf-8")
    if drift == "source": source.unlink()
    report = inspect_product(tmp_path, root, {"trim_size": "8.5x11"})
    finding = next(row for row in report.findings if row.check_id == "interior.typography_binding")
    assert finding.passed is (drift is None)
    assert finding.severity == BLOCKER


def test_unconfigured_source_note_does_not_enable_typography_gate(tmp_path):
    root = package(tmp_path)
    source = package_file(root, "PACKAGE_SOURCE_RECORD.json")
    data = json.loads(source.read_text(encoding="utf-8"))
    data["note"] = "sudoku_typography"
    source.write_text(json.dumps(data), encoding="utf-8")
    report = inspect_product(tmp_path, root, {"trim_size": "8.5x11"})
    assert not any(row.check_id == "interior.typography_binding" for row in report.findings)
