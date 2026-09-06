from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from background_generation.index import (
    BackgroundAssetIndex, CoverAssetApprovalError, file_sha256,
    require_production_approved_cover_asset, verify_rendered_cover_approval,
    write_cover_approval_proof,
)


def image(path: Path, color="#275a70") -> Path:
    canvas = Image.new("RGB", (900, 900), color)
    ImageDraw.Draw(canvas).ellipse((80, 90, 760, 780), fill="#e6b45c")
    canvas.save(path)
    return path


def row(path: Path, state="approved", *, asset_id="asset-1", provider="SladePuzzleCo project generation"):
    return {"asset_id": asset_id, "path": str(path), "topics": ["space"],
            "approval_state": state, "production_approved": state == "approved",
            "project_generated": True,
            "classification": "APPROVED_PROJECT_GENERATED" if state == "approved" else state.upper(),
            "sha256": file_sha256(path), "provenance": {"provider": provider},
            "approval_revision": "human-review-1"}


@pytest.fixture
def registry(tmp_path, monkeypatch):
    path = tmp_path / "registry.json"
    monkeypatch.setenv("SLADE_COVER_ASSET_REGISTRY", str(path))
    return BackgroundAssetIndex(path)


@pytest.mark.parametrize("state", ["awaiting_review", "rejected", "unknown"])
def test_nonapproved_states_fail_closed(tmp_path, registry, state):
    art = image(tmp_path / f"{state}.png")
    registry.save({"assets": [row(art, state)]})
    with pytest.raises(CoverAssetApprovalError, match="COVER ART REQUIRED"):
        require_production_approved_cover_asset(art, index=registry)


def test_unregistered_legacy_and_missing_assets_fail_closed(tmp_path, registry):
    legacy = image(tmp_path / "legacy-old-background.png")
    registry.save({"assets": []})
    with pytest.raises(CoverAssetApprovalError): require_production_approved_cover_asset(legacy, index=registry)
    with pytest.raises(CoverAssetApprovalError): require_production_approved_cover_asset(tmp_path / "missing.png", index=registry)


def test_approved_asset_allowed_and_survives_registry_restart(tmp_path, registry):
    art = image(tmp_path / "approved.png"); registry.save({"assets": [row(art)]})
    assert require_production_approved_cover_asset(art, index=registry)["asset_id"] == "asset-1"
    reloaded = BackgroundAssetIndex(registry.registry_file)
    assert require_production_approved_cover_asset(art, index=reloaded)["asset_id"] == "asset-1"


def test_file_change_invalidates_approval_and_render_proof(tmp_path, registry):
    art = image(tmp_path / "approved.png"); approved = row(art); registry.save({"assets": [approved]})
    front = image(tmp_path / "front.png", "#18263c"); write_cover_approval_proof(front, approved)
    assert verify_rendered_cover_approval(front, index=registry)[0]
    image(art, "#8b3148")
    with pytest.raises(CoverAssetApprovalError, match="changed after approval"):
        require_production_approved_cover_asset(art, index=registry)
    assert not verify_rendered_cover_approval(front, index=registry)[0]


def test_approval_cache_cannot_outlive_rejection(tmp_path, registry):
    art = image(tmp_path / "approved.png"); approved = row(art); registry.save({"assets": [approved]})
    assert require_production_approved_cover_asset(art, index=registry)
    payload = registry.payload(); payload["assets"][0].update(approval_state="rejected", production_approved=False)
    registry.save(payload)
    with pytest.raises(CoverAssetApprovalError): require_production_approved_cover_asset(art, index=registry)


def test_fifty_mixed_selections_accept_only_explicit_current_approvals(tmp_path, registry):
    rows, expected = [], set()
    formats = ("word-search", "sudoku", "cryptogram", "scramble", "mixed", "signature", "series")
    for number in range(50):
        art = image(tmp_path / f"{formats[number % len(formats)]}-{number}.png", f"#{(number * 9973) % 0xFFFFFF:06x}")
        state = ("approved", "awaiting_review", "rejected", "unknown", "approved")[number % 5]
        item = row(art, state, asset_id=f"asset-{number}")
        if number % 11 == 0: item["sha256"] = "stale"
        if state == "approved" and item["sha256"] != "stale": expected.add(item["asset_id"])
        rows.append(item)
    registry.save({"assets": rows})
    accepted = set()
    for item in rows:
        try: accepted.add(require_production_approved_cover_asset(item["path"], index=registry)["asset_id"])
        except CoverAssetApprovalError: pass
    assert accepted == expected
    assert not any(item["approval_state"] != "approved" for item in rows if item["asset_id"] in accepted)


def test_proof_records_required_audit_fields(tmp_path, registry):
    art = image(tmp_path / "approved.png"); approved = row(art); registry.save({"assets": [approved]})
    front = image(tmp_path / "front.png"); proof_path = write_cover_approval_proof(front, approved)
    proof = json.loads(proof_path.read_text(encoding="utf-8"))
    assert {"asset_id", "asset_sha256", "approval_state", "approval_revision", "provenance", "front_cover_sha256"} <= set(proof)
