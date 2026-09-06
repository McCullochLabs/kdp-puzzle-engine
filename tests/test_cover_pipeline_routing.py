"""Test that cover routing is consistent across all book-creation paths.

This suite verifies that the discussed-books builder (which was previously a
broken route that bypassed the approved-asset pipeline) now routes through the
same cover-orchestration as the GUI and other batch builders.
"""
from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

from build_discussed_book_packages import build as discussed_build
from build_discussed_book_packages import OUT_DIR


def _theme(path, topic, style="photo"):
    data = {
        "title": "Test Book " + topic.replace(" ", "_"),
        "subtitle": "A test subtitle for " + topic,
        "author": "Slade Puzzles",
        "series": "Test Series",
        "audience": "Adults and Teens",
        "palette": "nature",
        "cover_style": style,
        "cover_badge": "48 LARGE-PRINT PUZZLES",
        "cover_imprint": "Slade Puzzles",
        "detected_topic": topic,
        "difficulty_label": "Standard",
        "clipart_search_terms": topic.lower(),
        "puzzles": [{"name": "Puzzle %d" % i, "words": ["TEST", "WORD", "P%d" % i]} for i in range(1, 49)],
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def _run_build(theme, series_name, fake_choice):
    captured_commands = []
    cover_commands = []
    fake_pdf = MagicMock()
    fake_pdf.pages = [MagicMock()] * 48
    preflight_module = type("M", (), {"preflight": lambda _path: (True, [])})()
    import build_discussed_book_packages as mod

    def fake_run(args):
        captured_commands.append(list(args))
        if args[0] == "cover.py":
            cover_commands.append(list(args))

    with patch.object(mod, "run", side_effect=fake_run) as mock_run:
        with patch.object(mod.studio, "recommend_background_photo", return_value=fake_choice) as mock_recommend:
            with patch.object(mod, "PdfReader", return_value=fake_pdf):
                with patch.dict("sys.modules", {"preflight": preflight_module}):
                    discussed_build(theme, series_name, 1)
    return mock_recommend, cover_commands


def _unique_series():
    return "TestSeries" + uuid.uuid4().hex[:8]
def test_discussed_builder_routes_through_recommend_background_photo(tmp_path):
    """The discussed-books builder must call recommend_background_photo and pass --art."""
    theme = _theme(tmp_path / "test_theme.json", "Gardening")
    series = _unique_series()
    try:
        fake_choice = {
            "file": "cover_assets/background_photos/gardening_greenhouse_v2.png",
            "focus": "center", "name": "Gardening Greenhouse", "palette": "spring-meadow",
        }
        mock_recommend, cover_commands = _run_build(theme, series, fake_choice)

        assert mock_recommend.called, "discussed builder must call recommend_background_photo"
        assert len(cover_commands) == 1, "expected exactly one cover.py invocation"
        cover_cmd = cover_commands[0]

        assert "--art" in cover_cmd, "cover.py must receive --art when a match is found"
        art_index = cover_cmd.index("--art")
        assert "gardening_greenhouse_v2.png" in cover_cmd[art_index + 1]

        assert "--art-focus" in cover_cmd, "cover.py must receive --art-focus"
        style_index = cover_cmd.index("--style")
        assert "photo" in cover_cmd[style_index + 1]
    finally:
        shutil.rmtree(OUT_DIR / series, ignore_errors=True)


def test_discussed_builder_blocks_when_no_matching_art(tmp_path):
    """When no eligible art exists, the builder must fail closed before cover rendering."""
    theme = _theme(tmp_path / "test_theme.json", "Some Obscure Topic", style="gallery")
    series = _unique_series()
    try:
        mock_recommend, cover_commands = _run_build(theme, series, None)

        assert mock_recommend.called, "recommend_background_photo must still be consulted"
        assert cover_commands == [], "cover.py must not run without an approved asset"
        errors = list((OUT_DIR / series).rglob("BUILD_ERROR.txt"))
        assert errors, "the blocked build must leave a plain-English recovery record"
        text = errors[0].read_text(encoding="utf-8")
        assert "COVER ART REQUIRED" in text
    finally:
        shutil.rmtree(OUT_DIR / series, ignore_errors=True)


def test_cross_workflow_generated_asset_reuse():
    """A generated asset approved in one workflow is discoverable in another.

    An asset registered as eligible in the BackgroundAssetIndex (how the
    generator persists it) must be a candidate for a compatible book built
    through another route.
    """
    from background_generation.index import BackgroundAssetIndex
    from word_search_creator import recommend_background_photo

    index = BackgroundAssetIndex()
    matches = index.production_choices({"topic": "Space", "title": "Space and Astronomy Word Search", "puzzle_type": "Word Search"})
    if not matches:
        assert recommend_background_photo({"title": "Space", "detected_topic": "Space"}) is None
        return
    choice = recommend_background_photo({"title": "Space", "detected_topic": "Space"})
    assert choice, "a registered eligible asset must be recommended for a compatible book"
    from build_discussed_book_packages import APP_DIR
    details = index.ledger_details(APP_DIR / str(choice["file"]))
    assert details and index.production_selectable(details), (
        "recommended asset must be a registered, production-eligible background"
    )


def test_puzzle_studio_resolves_registry_path_once():
    """The gallery and package routes must not duplicate the asset directory."""
    from puzzle_book_studio import APP, cover_art_path

    relative = Path("cover_assets/background_photos/space_nebula.png")
    assert cover_art_path(relative) == APP / relative
    assert cover_art_path(APP / relative) == APP / relative


def test_cross_workflow_registry_persistence_with_approved_asset(tmp_path):
    """An approved generated asset remains discoverable after a registry reload."""
    from background_generation.index import BackgroundAssetIndex

    asset = tmp_path / "summer_lake.png"
    # Selection checks paths relative to the application root, so exercise the
    # persistence/provenance contract directly in this isolated registry and
    # leave real production data untouched.
    registry = tmp_path / "index.json"
    payload = {
        "schema_version": 1,
        "assets": [{
            "asset_id": "bg_test_summer",
            "path": str(asset),
            "name": "Summer Lake",
            "topics": ["summer activities", "summer", "outdoors"],
            "palette": "summer",
            "focus": "center",
            "classification": "APPROVED_CHATGPT_GENERATED",
            "production_approved": True,
            "project_generated": True,
            "provenance": {"provider": "ChatGPT project generation"},
            "usage": [],
        }],
    }
    registry.write_text(json.dumps(payload), encoding="utf-8")

    first = BackgroundAssetIndex(registry)
    row = first.assets()[0]
    assert first.production_selectable(row)
    first.save(first.payload())

    reloaded = BackgroundAssetIndex(registry)
    restored = reloaded.assets()[0]
    assert restored["asset_id"] == "bg_test_summer"
    assert reloaded.production_selectable(restored)


def test_publish_ready_route_passes_canonical_art_to_cover_engine():
    """The older one-click dialog must not bypass approved-art selection."""
    source = Path(__file__).resolve().parents[1].joinpath("word_search_creator.py").read_text(encoding="utf-8")
    start = source.index("class PublishReadyDialog")
    end = source.index("class WordBankImportDialog", start)
    route = source[start:end]
    assert "recommend_background_photo(theme_data)" in route
    assert 'cover_command.extend(["--art"' in route
    assert "Cover Art Required" in route
    assert "write_release_safety_files" in route
