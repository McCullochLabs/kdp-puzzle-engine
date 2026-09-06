from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw

from background_generation.index import BackgroundAssetIndex, file_sha256
from background_generation.routing import CoverRequest, select_cover_gallery


def _asset(folder: Path, number: int, *, topic="sudoku", family="", state="approved", retired=False, uses=0):
    path = folder / f"art-{number}.png"
    image = Image.new("RGB", (900, 1200), (25 + number * 13 % 220, 40 + number * 17 % 200, 70 + number * 19 % 180))
    ImageDraw.Draw(image).polygon(((80, 90), (820, 130 + number), (450, 1080)), fill=(230, 180, 60 + number % 150))
    image.save(path)
    return {"asset_id": f"asset-{number}", "path": str(path), "name": f"Art {number}", "topics": [topic, "logic puzzle"],
            "approval_state": state, "production_approved": state == "approved", "retired_from_new_production": retired,
            "project_generated": True, "classification": "APPROVED_PROJECT_GENERATED", "sha256": file_sha256(path),
            "perceptual_hash": f"{number + 1:016x}", "visual_family_id": family,
            "provenance": {"provider": "SladePuzzleCo project generation"}, "usage": [{"title": "Sudoku"}] * uses}


def _index(tmp_path: Path, rows: list[dict]):
    path = tmp_path / "registry.json"
    path.write_text(json.dumps({"schema_version": 1, "assets": rows}), encoding="utf-8")
    return BackgroundAssetIndex(path)


def _request(route="Puzzle Studio Gallery"):
    return CoverRequest(route=route, title="THE QUIET GRID", topic="General Starter", puzzle_type="Sudoku")


def test_six_distinct_families_produce_six_distinct_gallery_concepts(tmp_path):
    rows = [_asset(tmp_path, n, family=f"family-{n}") for n in range(6)]
    result = select_cover_gallery(_request(), index=_index(tmp_path, rows))
    assert result.metrics["gallery_slot_count"] == 6
    assert result.metrics["distinct_art_assets_shown"] == 6
    assert result.metrics["distinct_visual_families_shown"] == 6
    assert result.metrics["duplicate_asset_count"] == 0
    assert {concept.cover_template_id for concept in result.concepts} == {"photo"}


def test_first_row_uses_distinct_art_before_any_repeat(tmp_path):
    rows = [_asset(tmp_path, n, family=f"family-{n}") for n in range(3)]
    result = select_cover_gallery(_request(), index=_index(tmp_path, rows))
    assert len({item.art_asset_id for item in result.concepts[:3]}) == 3
    assert result.metrics["distinct_art_assets_shown"] == 3
    assert result.metrics["gallery_slot_count"] == 3
    assert result.metrics["duplicate_asset_count"] == 0
    assert result.metrics["diversity_limited"]


def test_visual_family_collapses_near_identical_hashes(tmp_path):
    rows = [_asset(tmp_path, 1), _asset(tmp_path, 2), _asset(tmp_path, 3)]
    rows[0]["perceptual_hash"] = "0000000000000000"
    rows[1]["perceptual_hash"] = "0000000000000001"
    rows[2]["perceptual_hash"] = "ffffffffffffffff"
    result = _index(tmp_path, rows).gallery_choices(_request().selection_data(), 3)
    assert result["metrics"]["eligible_visual_family_count"] == 2


def test_retired_and_unapproved_assets_never_enter_new_gallery(tmp_path):
    rows = [_asset(tmp_path, 1, family="active"), _asset(tmp_path, 2, family="retired", retired=True),
            _asset(tmp_path, 3, family="pending", state="awaiting_review")]
    result = select_cover_gallery(_request(), slots=2, index=_index(tmp_path, rows))
    assert {item.art_asset_id for item in result.concepts} == {"asset-1"}
    assert result.metrics["retired_asset_count_shown"] == 0
    assert result.metrics["unapproved_asset_count_shown"] == 0


def test_new_approval_and_cross_workflow_discovery_survive_restart(tmp_path):
    registry = _index(tmp_path, [_asset(tmp_path, 1, family="shared", state="awaiting_review")])
    assert not select_cover_gallery(_request(), index=registry).concepts
    payload = registry.payload(); payload["assets"][0].update(approval_state="approved", production_approved=True)
    registry.save(payload)
    restarted = BackgroundAssetIndex(registry.registry_file)
    word_route = select_cover_gallery(_request("Word Search Gallery"), index=restarted)
    mixed_route = select_cover_gallery(_request("Mixed Gallery"), index=BackgroundAssetIndex(registry.registry_file))
    assert word_route.concepts[0].art_asset_id == mixed_route.concepts[0].art_asset_id == "asset-1"


def test_refresh_rotates_existing_families_without_generation(tmp_path):
    rows = [_asset(tmp_path, n, family=f"family-{n}") for n in range(6)]
    index = _index(tmp_path, rows)
    first = select_cover_gallery(_request(), index=index)
    second = select_cover_gallery(_request(), refresh_offset=1, index=index)
    assert first.concepts[0].art_asset_id != second.concepts[0].art_asset_id
    assert second.diagnostics()["generation_requested"] is False


def test_one_hundred_gallery_builds_preserve_safety_and_diversity(tmp_path):
    rows = [_asset(tmp_path, n, family=f"family-{n}", uses=n % 3) for n in range(8)]
    rows += [_asset(tmp_path, 90, family="retired", retired=True), _asset(tmp_path, 91, family="pending", state="awaiting_review")]
    index = _index(tmp_path, rows)
    shown = set()
    for run in range(100):
        result = select_cover_gallery(_request(), refresh_offset=run, index=index)
        assert result.metrics["unapproved_asset_count_shown"] == 0
        assert result.metrics["retired_asset_count_shown"] == 0
        assert result.metrics["distinct_visual_families_shown"] == 6
        shown.update(item.art_asset_id for item in result.concepts)
    assert len(shown) == 8
