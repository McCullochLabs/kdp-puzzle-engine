import json
import sys
from pathlib import Path
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from publishing.manager import PublishingService
from publishing.listing_copy import recommended_bundle_prices
from publishing.marketplaces import PUBLISHERS
from publishing.master_package import build_master_package
from publishing.production_gate import book_gate, topic_gate
from theme_health import read_theme_health, record_theme_health
from background_generation.index import BackgroundAssetIndex, file_sha256, write_cover_approval_proof


def _theme(tmp_path: Path) -> Path:
    path = tmp_path / "sample.json"
    path.write_text(json.dumps({"title": "Garden Word Search", "subtitle": "48 calming puzzles", "author": "Jordan M. Slade", "series": "Garden Collection", "detected_topic": "Gardening", "puzzles": [{"words": ["ROSE"]}] * 48}), encoding="utf-8")
    return path


def _approve_package(tmp_path: Path, package: Path, monkeypatch) -> None:
    monkeypatch.setenv("SLADE_COVER_ASSET_REGISTRY", str(tmp_path / "cover_registry.json"))
    front = package / "front_cover.png"; Image.new("RGB", (2550, 3300), "#365f58").save(front)
    art = tmp_path / "approved_art.png"; Image.new("RGB", (900, 900), "#527b64").save(art)
    row = {"asset_id":"approved-fixture", "path":str(art), "topics":["gardening"], "approval_state":"approved", "production_approved":True, "project_generated":True, "classification":"APPROVED_PROJECT_GENERATED", "sha256":file_sha256(art), "provenance":{"provider":"SladePuzzleCo project generation"}}
    BackgroundAssetIndex().save({"assets":[row]}); write_cover_approval_proof(front, row)


def test_sync_creates_one_master_record_and_preserves_locked_metadata(tmp_path):
    service = PublishingService(tmp_path)
    theme = _theme(tmp_path)
    book_id = service.sync_theme(theme)
    book = service.db.get_book(book_id)
    assert book["metadata"]["title"] == "Garden Word Search"
    assert book["metadata"]["page_count"] > 0
    book["metadata"]["title"] = "Locked Garden Title"
    service.db.save_metadata(book_id, book["metadata"], locked=True)
    theme.write_text(theme.read_text(encoding="utf-8").replace("Garden Word Search", "Changed Title"), encoding="utf-8")
    service.sync_theme(theme)
    assert service.db.get_book(book_id)["metadata"]["title"] == "Locked Garden Title"


def test_isbn_cannot_be_assigned_to_two_different_books(tmp_path):
    service = PublishingService(tmp_path)
    first = service.sync_theme(_theme(tmp_path))
    other = tmp_path / "other.json"; other.write_text(json.dumps({"title": "Other", "author": "Jordan M. Slade", "puzzles": []}), encoding="utf-8")
    second = service.sync_theme(other)
    service.db.assign_isbn("978-1-234-56789-0", first, "Garden Word Search", "User-owned ISBN")
    try:
        service.db.assign_isbn("9781234567890", second, "Other", "User-owned ISBN")
    except ValueError:
        pass
    else:
        raise AssertionError("ISBN duplicate should have been blocked")


def test_prepare_returns_needs_review_without_required_print_files(tmp_path):
    service = PublishingService(tmp_path)
    book_id = service.sync_theme(_theme(tmp_path))
    _folder, issues = service.prepare(book_id, "amazon")
    assert issues and service.db.statuses(book_id)["amazon"] == "Needs Review"


def test_production_gate_allows_a_clean_source_but_requires_files_before_handoff(tmp_path):
    service = PublishingService(tmp_path)
    book_id = service.sync_theme(_theme(tmp_path))
    gate = service.production_gate(book_id)
    assert gate["ready"] and gate["stage"] == "Ready to create package"
    assert not gate["has_package"]


def test_production_gate_blocks_a_saved_failed_word_quality_review(tmp_path):
    service = PublishingService(tmp_path)
    theme = _theme(tmp_path)
    data = json.loads(theme.read_text(encoding="utf-8"))
    data["quality_review"] = {"production_ready": False, "verdict": "FAIL"}
    theme.write_text(json.dumps(data), encoding="utf-8")
    gate = service.production_gate(service.sync_theme(theme))
    assert not gate["ready"]
    assert any("word-quality" in item for item in gate["blockers"])


def test_topic_gate_never_claims_a_short_library_is_ready(tmp_path):
    bank = tmp_path / "word_banks"; bank.mkdir()
    (bank / "Guided_Builder_Master_Word_Bank.json").write_text(json.dumps({"topics": {"Small": ["ONE"]}, "topic_packs": {}, "production_topic_packs": {}}), encoding="utf-8")
    (bank / "puzzle_content_library.json").write_text("{}", encoding="utf-8")
    gate = topic_gate(tmp_path, "Space & Astronomy")
    assert not gate["ready"] and gate["needed"] == 576


def test_catalog_page_estimate_counts_optional_interior_section_dividers():
    source = {
        "puzzles": [{"name": f"Puzzle {number}", "words": ["ROSE"]} for number in range(1, 7)],
        "interior_sections": {"group_size": 5, "divider_pages": True},
    }
    assert PublishingService._estimate_wordsearch_pages(source) == 20


def test_launch_handoffs_locks_release_before_safe_local_preparation(tmp_path, monkeypatch):
    service = PublishingService(tmp_path)
    package = tmp_path / "finished"; package.mkdir()
    for name in ("interior.pdf", "kdp_full_wrap.pdf"):
        (package / name).write_bytes(b"pdf")
    _approve_package(tmp_path, package, monkeypatch)
    book_id = service.sync_theme(_theme(tmp_path), package)
    result = service.launch_handoffs(book_id)
    assert result["lock"]["revision"] == 1
    assert {market for _book, market, _state in result["report"]} == {"amazon", "etsy", "payhip", "website"}


def test_upload_status_keeps_confirmed_link_and_local_scan_never_overwrites_it(tmp_path):
    service = PublishingService(tmp_path)
    package = tmp_path / "finished"; (package / "kdp").mkdir(parents=True)
    book_id = service.sync_theme(_theme(tmp_path), package)
    assert service.detect_local_marketplace_status() == 1
    assert service.db.statuses(book_id)["amazon"] == "Ready"
    service.db.update_marketplace_record(book_id, "amazon", "Published", "B0TEST123", "https://www.amazon.com/dp/B0TEST123")
    assert service.detect_local_marketplace_status() == 0
    record = service.db.marketplace_records(book_id)["amazon"]
    assert record["status"] == "Published"
    assert record["external_id"] == "B0TEST123"
    assert record["url"].endswith("B0TEST123")


def test_catalog_sync_hides_timestamped_duplicate_theme_copies(tmp_path):
    service = PublishingService(tmp_path)
    first = _theme(tmp_path)
    duplicate = tmp_path / "garden_20260822_174014.json"
    duplicate.write_text(first.read_text(encoding="utf-8"), encoding="utf-8")
    assert service.sync_catalog([first, duplicate], {}) == 1
    assert len(service.db.list_books()) == 1


def test_recommendations_prioritize_a_ready_to_create_evergreen_book(tmp_path):
    service = PublishingService(tmp_path)
    theme = _theme(tmp_path)
    record_theme_health(tmp_path / "data" / "theme_readiness_cache.json", theme, [], [])
    service.sync_theme(theme)
    recommendations = service.recommended_books()
    assert recommendations
    assert recommendations[0]["book"]["metadata"]["title"] == "Garden Word Search"
    assert recommendations[0]["action"] == "Create book"
    assert "series-friendly" in recommendations[0]["reason"]


def test_ready_now_and_best_version_require_a_current_passed_health_record(tmp_path):
    service = PublishingService(tmp_path)
    theme = _theme(tmp_path)
    record_theme_health(tmp_path / "data" / "theme_readiness_cache.json", theme, [], [])
    service.sync_theme(theme)
    ready = service.ready_now_books()
    assert len(ready) == 1 and ready[0]["book"]["metadata"]["title"] == "Garden Word Search"
    assert service.best_version()["book"]["book_id"] == ready[0]["book"]["book_id"]


def test_approved_queue_and_release_lock_are_stable_revision_records(tmp_path, monkeypatch):
    service = PublishingService(tmp_path)
    package = tmp_path / "finished"; package.mkdir()
    _approve_package(tmp_path, package, monkeypatch)
    book_id = service.sync_theme(_theme(tmp_path), package)
    service.db.approve_for_production(book_id)
    assert service.db.approved_production_queue()[0]["status"] == "Approved"
    service.db.set_approval_status(book_id, "In progress")
    assert service.db.approved_production_queue()[0]["status"] == "In progress"
    first = service.db.lock_release(book_id)
    again = service.db.lock_release(book_id)
    assert first["revision"] == 1 and not first["unchanged"]
    assert again["revision"] == 1 and again["unchanged"]
    book = service.db.get_book(book_id)
    book["metadata"]["subtitle"] = "Revised cover copy"
    service.db.save_metadata(book_id, book["metadata"])
    second = service.db.lock_release(book_id)
    assert second["revision"] == 2


def test_production_plan_cover_concepts_and_file_checksums_are_persisted(tmp_path, monkeypatch):
    service = PublishingService(tmp_path)
    package = tmp_path / "finished"; package.mkdir()
    _approve_package(tmp_path, package, monkeypatch)
    interior = package / "interior.pdf"; interior.write_bytes(b"first interior")
    wrap = package / "kdp_full_wrap.pdf"; wrap.write_bytes(b"first wrap")
    book_id = service.sync_theme(_theme(tmp_path), package)
    service.db.approve_for_production(book_id, marketplaces=["amazon", "etsy"], launch_date="2026-09-15")
    row = service.db.approved_production_queue()[0]
    assert row["target_marketplaces"] == ["amazon", "etsy"] and row["target_launch_date"] == "2026-09-15"
    service.db.save_cover_concept(book_id, "Concept A", {"palette": "nature", "layout": "Photo Hero"}, selected=True)
    assert service.db.cover_concepts(book_id)[0]["selected"] == 1
    locked = service.db.lock_release(book_id)
    snapshot = json.loads((service.db._connect().execute("SELECT snapshot_json FROM release_locks WHERE book_id=?", (book_id,)).fetchone()[0]))
    assert locked["revision"] == 1 and "kdp_full_wrap.pdf" in snapshot["file_checksums"]
    wrap.write_bytes(b"changed wrap")
    assert service.db.lock_release(book_id)["revision"] == 2


def test_changed_theme_cannot_reuse_an_old_passed_content_check(tmp_path):
    theme = _theme(tmp_path); cache = tmp_path / "data" / "theme_readiness_cache.json"
    record_theme_health(cache, theme, [], [])
    assert read_theme_health(cache, theme)["status"] == "Passed"
    theme.write_text(theme.read_text(encoding="utf-8").replace("Garden Word Search", "Changed Garden Word Search"), encoding="utf-8")
    assert read_theme_health(cache, theme) is None


def test_unchecked_theme_is_not_recommended_for_production(tmp_path):
    service = PublishingService(tmp_path)
    service.sync_theme(_theme(tmp_path))
    assert not service.recommended_books()


def test_kdp_validation_rejects_stale_file_paths(tmp_path):
    service = PublishingService(tmp_path)
    book_id = service.sync_theme(_theme(tmp_path))
    book = service.db.get_book(book_id)
    book["metadata"]["files"] = {"print_interior": str(tmp_path / "missing-interior.pdf"), "print_cover": str(tmp_path / "missing-cover.pdf")}
    assert "interior PDF" in " ".join(PUBLISHERS["amazon"].validate(book))
    assert "cover PDF" in " ".join(PUBLISHERS["amazon"].validate(book))


def test_ingram_handoff_never_labels_a_kdp_wrap_as_final_upload_cover(tmp_path):
    service = PublishingService(tmp_path)
    package = tmp_path / "finished"; package.mkdir()
    interior = package / "interior.pdf"; interior.write_bytes(b"interior")
    cover = package / "kdp_full_wrap.pdf"; cover.write_bytes(b"kdp wrap")
    front = package / "front_cover.png"; Image.new("RGB", (100, 150), "#476c5e").save(front)
    book_id = service.sync_theme(_theme(tmp_path), package)
    service.db.assign_isbn("9781234567890", book_id, "Garden Word Search", "User-owned ISBN")
    saved = service.db.get_book(book_id)
    saved["metadata"]["isbn"] = "9781234567890"
    service.db.save_metadata(book_id, saved["metadata"])
    target, issues = service.prepare(book_id, "ingram")
    assert not issues
    assert service.db.statuses(book_id)["ingram"] == "Prepared — Final Cover Needed"
    assert (target / "interior_starting_file.pdf").is_file()
    assert (target / "kdp_cover_REFERENCE_ONLY.pdf").is_file()
    assert not (target / "cover.pdf").exists()
    assert "Do not upload" in (target / "START_HERE.txt").read_text(encoding="utf-8")


def test_master_release_package_separates_platform_handoffs(tmp_path):
    (tmp_path / "interior.pdf").write_bytes(b"interior")
    (tmp_path / "kdp_full_wrap.pdf").write_bytes(b"cover")
    (tmp_path / "front_cover.png").write_bytes(b"front")
    master = build_master_package(tmp_path, {"title": "Garden Word Search", "author": "Jordan M. Slade", "trim_size": "8.5x11", "page_count": 100})
    assert master and (master / "01_KDP_UPLOAD" / "interior.pdf").is_file()
    assert (master / "02_ETSY_DIGITAL" / "digital_download.pdf").is_file()
    assert (master / "04_INGRAMSPARK" / "BUILD_PLATFORM_COVER_FIRST.txt").is_file()
    assert not (master / "04_INGRAMSPARK" / "kdp_cover_reference_only.pdf").exists()
    assert not (master / "05_LULU" / "kdp_cover_reference_only.pdf").exists()
    assert not (master / "07_BARNES_NOBLE" / "kdp_cover_reference_only.pdf").exists()


def test_etsy_bundle_creates_buyer_download_and_catalog_record(tmp_path):
    service = PublishingService(tmp_path)
    ids = []
    for number in (1, 2):
        package = tmp_path / f"package_{number}"; package.mkdir()
        for name in ("interior.pdf", "kdp_full_wrap.pdf"):
            (package / name).write_bytes(f"{name}-{number}".encode())
        Image.new("RGB", (100, 150), (30, 120, 100)).save(package / "front_cover.png")
        theme = tmp_path / f"theme_{number}.json"
        theme.write_text(json.dumps({"title": f"Garden Book {number}", "author": "Jordan M. Slade", "detected_topic": "Gardening", "puzzles": [{"words": ["ROSE"]}] * 48}), encoding="utf-8")
        ids.append(service.sync_theme(theme, package))
    folder, details = service.create_etsy_bundle("Garden Puzzle Pack", ids, 12.99)
    assert (folder / "01_ETSY_UPLOAD_FILES").is_dir()
    assert (folder / "ETSY_LISTING_KIT.txt").is_file()
    assert details["upload_files"]
    assert service.db.list_bundles()[0]["title"] == "Garden Puzzle Pack"


def test_bundle_prices_are_visible_and_lower_than_individual_digital_checkout():
    books = [{"metadata": {"page_count": 120, "puzzle_count": 48}}, {"metadata": {"page_count": 180, "puzzle_count": 60}}]
    plan = recommended_bundle_prices(books)
    assert plan["etsy"] > 0 and plan["website"] == plan["etsy"]
    assert plan["savings_percent"] == 15
