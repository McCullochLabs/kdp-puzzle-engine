from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from background_generation.index import BackgroundAssetIndex, file_sha256
from background_generation.routing import CoverRequest, select_cover_asset


def _asset(tmp_path: Path, asset_id: str, topics: list[str], *, photo: bool = False, uses: int = 0) -> dict:
    path = tmp_path / f"{asset_id}.png"
    Image.new("RGB", (900, 1200), (40 + uses, 80, 120)).save(path)
    base = {
        "asset_id": asset_id, "path": str(path), "name": asset_id,
        "topics": topics, "palette": "nature", "focus": "center",
        "approval_state": "approved", "production_approved": True,
        "sha256": file_sha256(path), "usage": [{"title": str(i)} for i in range(uses)],
    }
    if photo:
        base.update({
            "classification": "APPROVED_LOCAL_PHOTO", "project_generated": False,
            "source_type": "owned_photo", "rights_verified": True,
            "provenance": {"provider": "local library", "rights_basis": "Publisher-owned photograph"},
        })
    else:
        base.update({
            "classification": "APPROVED_PROJECT_GENERATED", "project_generated": True,
            "provenance": {"provider": "SladePuzzleCo project generation"},
        })
    return base


def _index(tmp_path: Path, rows: list[dict]) -> BackgroundAssetIndex:
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({"schema_version": 1, "assets": rows}), encoding="utf-8")
    return BackgroundAssetIndex(registry)


def test_relevant_generated_beats_unrelated_approved_photo(tmp_path):
    generated = _asset(tmp_path, "summer_generated", ["summer activities", "beach"])
    unrelated = _asset(tmp_path, "office_photo", ["office", "business"], photo=True)
    decision = select_cover_asset(
        CoverRequest(route="Guided Builder", title="Summer Activities", topic="Summer Activities"),
        index=_index(tmp_path, [unrelated, generated]),
    )
    assert decision.asset["asset_id"] == "summer_generated"


def test_strong_approved_photo_can_beat_weak_generated_art(tmp_path):
    photo = _asset(tmp_path, "garden_photo", ["gardening", "garden lovers"], photo=True)
    generated = _asset(tmp_path, "generic_generated", ["home", "hobbies"])
    decision = select_cover_asset(
        CoverRequest(route="Book Assistant", title="Garden Lovers", topic="Gardening"),
        index=_index(tmp_path, [generated, photo]),
    )
    assert decision.asset["asset_id"] == "garden_photo"
    assert decision.diagnostics()["source"] == "Approved Photo"


def test_cross_workflow_reuse_and_restart(tmp_path):
    shared = _asset(tmp_path, "space_shared", ["space", "astronomy", "planets"])
    first_index = _index(tmp_path, [shared])
    word_search = select_cover_asset(
        CoverRequest(route="Word Search", title="Space Search", topic="Space"), index=first_index)
    restarted = BackgroundAssetIndex(first_index.registry_file)
    sudoku = select_cover_asset(
        CoverRequest(route="Puzzle Studio — Sudoku", title="Space Sudoku", topic="Space", puzzle_type="Sudoku"),
        index=restarted,
    )
    assert word_search.asset["asset_id"] == sudoku.asset["asset_id"] == "space_shared"


def test_selection_never_calls_generation_when_strong_asset_exists(tmp_path):
    approved = _asset(tmp_path, "pets_ready", ["pets", "cats", "dogs"])
    with patch("background_generation.service.BackgroundGenerationService.process_next") as generate:
        decision = select_cover_asset(
            CoverRequest(route="Series Builder", title="Cozy Pets", topic="Pets", generation_allowed=True),
            index=_index(tmp_path, [approved]),
        )
    assert decision.asset["asset_id"] == "pets_ready"
    generate.assert_not_called()
    assert decision.diagnostics()["generation_requested"] is False


def test_provider_failure_does_not_affect_existing_approved_assets(tmp_path):
    approved = _asset(tmp_path, "history_ready", ["history", "heritage"])
    with patch("background_generation.service.BackgroundGenerationService.process_next", side_effect=RuntimeError("offline")):
        decision = select_cover_asset(
            CoverRequest(route="Publishing Center", title="History", topic="History"),
            index=_index(tmp_path, [approved]),
        )
    assert decision.asset["asset_id"] == "history_ready"
    assert decision.fallback_reason == ""


def test_ineligible_saved_asset_is_not_forced(tmp_path):
    stale = _asset(tmp_path, "stale_saved", ["travel"])
    stale["approval_state"] = "rejected"
    ready = _asset(tmp_path, "travel_ready", ["travel", "adventure"])
    decision = select_cover_asset(
        CoverRequest(route="Quick Create", title="Travel", topic="Travel", preferred_asset=stale["path"]),
        index=_index(tmp_path, [stale, ready]),
    )
    assert decision.asset["asset_id"] == "travel_ready"
    assert "saved asset" in decision.fallback_reason


def test_shared_route_reads_theme_preferences_and_niche_direction(tmp_path, monkeypatch):
    import background_generation.routing as routing

    monkeypatch.setattr(routing, "ROOT", tmp_path)
    theme = tmp_path / "themes" / "garden.json"
    theme.parent.mkdir()
    theme.write_text("{}", encoding="utf-8")
    preferred = _asset(tmp_path, "garden_preferred", ["gardening"])
    (tmp_path / "cover_preferences.json").write_text(json.dumps({
        str(theme.relative_to(tmp_path)): {
            "style": "photo", "palette": "spring-meadow", "art": preferred["path"]
        }
    }), encoding="utf-8")
    (tmp_path / "niche_cover_memory.json").write_text(json.dumps({
        "Gardening": {"style": "gallery", "palette": "nature"}
    }), encoding="utf-8")
    decision = select_cover_asset(
        CoverRequest(route="Guided Builder", title="Garden", topic="Gardening", theme_path=str(theme)),
        index=_index(tmp_path, [preferred]),
    )
    assert decision.asset["asset_id"] == "garden_preferred"
    assert decision.style == "photo"
    assert decision.palette == "spring-meadow"
