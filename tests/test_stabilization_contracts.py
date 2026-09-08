from pathlib import Path

from integrations.etsy.capabilities import ETSY_CAPABILITIES
from integrations.etsy.connection import EtsyIntegration
from integrations.etsy.draft_service import EtsyDraftService
from integrations.registry import get_integration_info
from publishing.ui import draft_action_enabled
from tools.check_runtime import runtime_errors
from project_checks import run_project_check
from tools.validate_themes import validate
from publishing.database import PublishingDatabase


def test_runtime_is_exact_supported_64_bit_cpython():
    assert runtime_errors() == []


def test_full_project_theme_validation_succeeds():
    root = Path(__file__).resolve().parents[1]
    assert validate(root / "themes") == 0


def test_full_project_theme_validation_returns_failure(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.validate_themes.run_project_check",
                        lambda _path: (["bad palette"], []))
    assert validate(tmp_path) == 1


def _minimal_project(tmp_path, theme):
    themes = tmp_path / "themes"
    themes.mkdir()
    (themes / "theme.json").write_text(__import__("json").dumps(theme), encoding="utf-8")
    bank = tmp_path / "word_banks"
    bank.mkdir()
    (bank / "Guided_Builder_Master_Word_Bank.json").write_text(
        '{"topics": {}, "word_profiles": {}, "total_unique_words": 0}', encoding="utf-8")
    assets = tmp_path / "cover_assets"
    assets.mkdir()
    (assets / "background_photo_library.json").write_text('{"items": []}', encoding="utf-8")
    for name in ("Start Word Search Creator.bat", "launch_word_search_creator.py",
                 "word_search_creator.py", "wordsearch.py", "cover.py", "wrap_cover.py"):
        (tmp_path / name).write_text("", encoding="utf-8")
    return themes


def test_bad_palette_fails_canonical_project_validator(tmp_path):
    themes = _minimal_project(tmp_path, {
        "title": "Test", "author": "Slade Puzzles", "palette": "not-real",
        "cover_style": "minimal", "puzzles": [{"name": "One", "words": ["BIRD"]}],
    })
    problems, _notes = run_project_check(themes)
    assert any("unknown cover color family" in item for item in problems)


def test_incomplete_puzzle_fails_canonical_project_validator(tmp_path):
    themes = _minimal_project(tmp_path, {
        "title": "Test", "author": "Slade Puzzles", "palette": "birds",
        "cover_style": "minimal", "puzzles": [{"name": "One", "words": []}],
    })
    problems, _notes = run_project_check(themes)
    assert any("incomplete puzzle data" in item for item in problems)


def test_etsy_capability_contract_agrees_across_registry_and_services():
    declared = get_integration_info("etsy")["capabilities"]
    assert declared == ETSY_CAPABILITIES.capability_dict
    assert EtsyDraftService.capabilities == ETSY_CAPABILITIES
    assert EtsyIntegration.capabilities.can_test_connection is True
    expected = {
        "can_test_connection": True,
        "can_create_draft": True,
        "can_upload_files": True,
        "can_upload_images": True,
        "can_activate": False,
        "can_pull_sales": False,
        "can_sync_orders": False,
        "can_delete_listing": False,
    }
    for name, value in expected.items():
        assert declared[name] is value


def test_etsy_draft_service_exposes_real_operation_path():
    assert callable(EtsyDraftService.create_or_resume)
    assert draft_action_enabled({"key": "etsy", "has_local_folder": True,
                                 "status": "Ready"})


def test_publishing_database_releases_windows_file_handle(tmp_path):
    path = tmp_path / "books.db"
    database = PublishingDatabase(path)
    database.list_books()
    path.unlink()
    assert not path.exists()
