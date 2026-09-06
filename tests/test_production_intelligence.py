from pathlib import Path
from types import SimpleNamespace

from pypdf import PdfWriter
from PIL import Image

from publishing.design import automatic_bonus_pages
from publishing.production_intelligence import finalize_package, pdf_assessment, remaining_capacity, reservation_check, reserve_words, title_assessment, visual_quality_assessment
from background_generation.index import BackgroundAssetIndex, file_sha256, write_cover_approval_proof


def _source(words):
    return {"detected_topic": "Gardening", "puzzles": [{"words": words}]}


def test_reservations_stop_exact_word_reuse_between_finalized_books(tmp_path):
    first = _source(["ROSE", "TULIP", "HERB"])
    assert reserve_words(tmp_path, "Garden Book One", first, tmp_path / "one")["ready"]
    second = _source(["ROSE", "LILY"])
    report = reservation_check(tmp_path, "Garden Book Two", second)
    assert not report["ready"]
    assert report["conflicts"][0]["count"] == 1


def test_reservations_allow_legitimate_cross_topic_overlap_but_protect_a_series(tmp_path):
    hiking = {"detected_topic": "Hiking", "series": "Trail Adventures", "puzzles": [{"words": ["TRAIL", "SUMMIT"]}]}
    parks = {"detected_topic": "National Parks", "series": "National Parks Collection", "puzzles": [{"words": ["TRAIL", "RANGER"]}]}
    sibling = {"detected_topic": "Hiking", "series": "Trail Adventures", "puzzles": [{"words": ["TRAIL", "CREEK"]}]}
    assert reserve_words(tmp_path, "Hiking Book One", hiking, tmp_path / "one")["ready"]
    assert reservation_check(tmp_path, "National Parks Book One", parks)["ready"]
    report = reservation_check(tmp_path, "Hiking Book Two", sibling)
    assert not report["ready"]
    assert report["scope"]["label"] == "Trail Adventures"


def test_title_assessment_flags_exact_catalog_duplicate():
    report = title_assessment("Garden Word Search", "48 calm puzzles", "Gardening", ["Garden Word Search"])
    assert report["score"] < 85
    assert any("matches" in item for item in report["notes"])


def test_pdf_assessment_checks_openable_page_count(tmp_path):
    path = Path(tmp_path) / "interior.pdf"
    writer = PdfWriter(); writer.add_blank_page(612, 792); writer.add_blank_page(612, 792)
    with path.open("wb") as stream:
        writer.write(stream)
    report = pdf_assessment(path, 2)
    assert report["ok"] and report["pages"] == 2


def test_automatic_bonus_matching_stays_with_existing_bonus_options():
    bonuses = automatic_bonus_pages("Cryptogram", "Space & Astronomy", False)
    assert "About this topic facts" in bonuses
    assert "Extra challenge page" in bonuses


def test_final_intelligence_writes_assets_ledger_and_word_reservation(tmp_path, monkeypatch):
    monkeypatch.setenv("SLADE_COVER_ASSET_REGISTRY", str(tmp_path / "cover_registry.json"))
    folder = Path(tmp_path) / "package"; folder.mkdir()
    for name, pages in (("interior.pdf", 2), ("kdp_full_wrap.pdf", 1)):
        writer = PdfWriter()
        for _ in range(pages): writer.add_blank_page(612, 792)
        with (folder / name).open("wb") as stream: writer.write(stream)
    Image.new("RGB", (2550, 3300), "#224466").save(folder / "front_cover.png")
    art = tmp_path / "approved_art.png"; Image.new("RGB", (900, 900), "#527b64").save(art)
    approved = {"asset_id":"garden-approved", "path":str(art), "topics":["gardening"], "approval_state":"approved", "production_approved":True, "project_generated":True, "classification":"APPROVED_PROJECT_GENERATED", "sha256":file_sha256(art), "provenance":{"provider":"SladePuzzleCo project generation"}}
    BackgroundAssetIndex().save({"assets":[approved]}); write_cover_approval_proof(folder / "front_cover.png", approved)
    for name in ("KDP_LISTING_KIT.txt", "PUBLISHER_PREFLIGHT.txt", "PACKAGE_SOURCE_RECORD.json"):
        (folder / name).write_text(__import__("json").dumps({"cover_art":str(art)}) if name == "PACKAGE_SOURCE_RECORD.json" else "ready", encoding="utf-8")
    (folder / "PRODUCTION_PROOF_GATE.txt").write_text("PASS", encoding="utf-8")
    report = finalize_package(tmp_path, folder, _source(["ROSE", "TULIP"]), "Fresh Garden Word Search", "48 calm puzzles", 2)
    assert report["ready"]
    assert report["release_contract"]["ready"]
    assert (folder / "PRODUCTION_INTELLIGENCE.json").is_file()
    assert (folder / "COVER_VISUAL_QUALITY_REPORT.json").is_file()
    assert (folder / "marketplace_assets" / "etsy_listing_cover.png").is_file()
    assert (Path(tmp_path) / "data" / "production_ledger.json").is_file()


def test_remaining_capacity_uses_the_same_phrase_normalization_as_reservations(tmp_path):
    bank = {"topics": {"Cocktails": ["OLD FASHIONED", "NEGRONI"]}}
    target = Path(tmp_path) / "word_banks" / "Guided_Builder_Master_Word_Bank.json"
    target.parent.mkdir(); target.write_text(__import__("json").dumps(bank), encoding="utf-8")
    cocktail_source = {"detected_topic": "Cocktails", "puzzles": [{"words": ["OLD FASHIONED"]}]}
    assert reserve_words(tmp_path, "First Cocktail Book", cocktail_source, tmp_path / "one")["ready"]
    report = remaining_capacity(tmp_path, {"detected_topic": "Cocktails"})
    assert report["available"] == 1


class _AssetIndex:
    def ensure_provenance_audited(self): pass

    def eligibility(self, _path):
        return True, "approved for production", self.ledger_details(_path)

    def ledger_details(self, _path):
        return {"asset_id": "books-reading", "name": "Books and Reading", "topics": ["book", "reading", "library", "vocabulary"]}

    def cover_brief(self, value):
        return value

    def _topic_score(self, _asset, _brief):
        return 33


def test_visual_gate_flags_grade_school_art_without_school_context_and_series_drift(tmp_path):
    package = tmp_path / "package"
    for name in ("03_PREVIEWS", "04_REVIEW_AND_RECORDS"):
        (package / name).mkdir(parents=True)
    image = Image.new("RGB", (2550, 3300), "#315a83")
    image.paste(Image.new("RGB", (1000, 1000), "#d9b36c"), (750, 1000))
    image.save(package / "03_PREVIEWS" / "front_cover.png")
    theme = tmp_path / "themes" / "grade_school.json"; theme.parent.mkdir()
    theme.write_text('{"series":"Vocabulary Ladder","palette":"royal-plum","cover_style":"gallery"}', encoding="utf-8")
    manifest = {"title":"Vocabulary Adventures: Grade School", "subtitle":"48 vocabulary searches", "puzzle_count":48,
                "puzzle_type":"Word Search", "cover_puzzle_type":"Word Search", "difficulty":"standard",
                "palette":"library-burgundy", "cover_layout":"photo", "cover_art":str(tmp_path / "books_reading.png"),
                "source_theme":str(theme)}
    (package / "04_REVIEW_AND_RECORDS" / "PACKAGE_SOURCE_RECORD.json").write_text(__import__("json").dumps(manifest), encoding="utf-8")
    report = visual_quality_assessment(tmp_path, package, {"detected_topic":"School & Vocabulary"},
                                       plan=SimpleNamespace(puzzle_type="word_search", format={"puzzle_count":48, "difficulty":"standard"}), asset_index=_AssetIndex())
    failed = {row["check_id"] for row in report["checks"] if not row["passed"]}
    assert "cover.art.audience_context" in failed
    assert "cover.series.direction" in failed
    assert not report["hard_failures"]


def test_visual_gate_hard_blocks_wrong_puzzle_style_record(tmp_path):
    package = tmp_path / "package"
    for name in ("03_PREVIEWS", "04_REVIEW_AND_RECORDS"):
        (package / name).mkdir(parents=True)
    image = Image.new("RGB", (2550, 3300), "#315a83")
    image.paste(Image.new("RGB", (1000, 1000), "#d9b36c"), (750, 1000))
    image.save(package / "03_PREVIEWS" / "front_cover.png")
    manifest = {"title":"Garden Search", "puzzle_count":48, "puzzle_type":"Sudoku", "cover_puzzle_type":"Sudoku", "difficulty":"standard"}
    (package / "04_REVIEW_AND_RECORDS" / "PACKAGE_SOURCE_RECORD.json").write_text(__import__("json").dumps(manifest), encoding="utf-8")
    report = visual_quality_assessment(tmp_path, package, {"puzzle_type":"word_search", "detected_topic":"Gardening"},
                                       plan=SimpleNamespace(puzzle_type="word_search", format={"puzzle_count":48, "difficulty":"standard"}))
    assert any("Recorded cover puzzle type" in item for item in report["hard_failures"])
