from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from background_generation.index import BackgroundAssetIndex
from background_generation.providers import ProviderNotConfigured
from background_generation.service import BackgroundGenerationService, _approved_classification, build_prompt


def _test_image(path: Path) -> bytes:
    image = Image.new("RGB", (900, 900), "#204d70")
    draw = ImageDraw.Draw(image)
    draw.ellipse((100, 120, 650, 740), fill="#e6b45c")
    image.save(path)
    return path.read_bytes()


def test_legacy_audit_approves_manifest_art_and_selection_is_topic_specific(tmp_path, monkeypatch):
    import background_generation.index as module
    root = tmp_path
    art = root / "cover_assets" / "background_photos" / "space.png"; art.parent.mkdir(parents=True)
    _test_image(art)
    manifest = root / "cover_assets" / "background_photo_library.json"
    manifest.write_text('{"items":[{"name":"Space","file":"cover_assets/background_photos/space.png","match_terms":["space","planet"],"palette":"starlight-indigo"}]}', encoding="utf-8")
    monkeypatch.setattr(module, "ROOT", root); monkeypatch.setattr(module, "COVER_ASSETS", root / "cover_assets"); monkeypatch.setattr(module, "LEGACY_LIBRARY_FILE", manifest)
    index = BackgroundAssetIndex(root / "cover_assets" / "index.json")
    assert index.audit_legacy_library()["approved"] == 1
    choice = index.approved_choices("Space and planets word search")[0]
    assert choice["production_approved"] is True
    assert choice["classification"] == "APPROVED_CHATGPT_GENERATED"


def test_unknown_asset_is_retained_but_never_auto_selected(tmp_path, monkeypatch):
    import background_generation.index as module
    root = tmp_path; art = root / "cover_assets" / "background_photos" / "mystery.png"; art.parent.mkdir(parents=True); _test_image(art)
    manifest = root / "cover_assets" / "background_photo_library.json"; manifest.write_text('{"items":[]}', encoding="utf-8")
    monkeypatch.setattr(module, "ROOT", root); monkeypatch.setattr(module, "COVER_ASSETS", root / "cover_assets"); monkeypatch.setattr(module, "LEGACY_LIBRARY_FILE", manifest)
    index = BackgroundAssetIndex(root / "cover_assets" / "index.json"); stats = index.audit_legacy_library()
    assert stats["quarantined"] == 1
    assert not index.approved_choices("mystery")


def test_production_selection_fails_closed_without_explicit_project_generation(tmp_path):
    art = tmp_path / "approved-looking.png"; _test_image(art)
    index = BackgroundAssetIndex(tmp_path / "index.json")
    index.save({"assets": [{"asset_id": "looks-approved", "path": str(art), "topics": ["space"],
                              "classification": "APPROVED_CHATGPT_GENERATED", "production_approved": True,
                              "provenance": {"provider": "ChatGPT project generation"}}]})
    assert not index.production_choices({"topic": "Space", "title": "Space"})


def test_prompt_has_cover_safety_rules():
    prompt = build_prompt("space and planets", palette="starlight-indigo", adult=True)
    assert "no words" in prompt and "no watermarks" in prompt and "non-explicit" in prompt


def test_human_approved_generated_art_keeps_its_true_provider():
    candidate = {"project_generated": True, "provenance": {"provider": "ChatGPT project generation"}}
    assert _approved_classification(candidate) == "APPROVED_CHATGPT_GENERATED"
    candidate["provenance"]["provider"] = "Cloudflare Workers AI"
    assert _approved_classification(candidate) == "APPROVED_CLOUDFLARE_GENERATED"
    candidate["provenance"]["provider"] = "unknown"
    import pytest
    with pytest.raises(ValueError, match="verified project-generation provider"):
        _approved_classification(candidate)


def test_unconfigured_generation_pauses_safely(tmp_path, monkeypatch):
    import background_generation.service as module
    monkeypatch.setattr(module, "QUEUE_FILE", tmp_path / "queue.json")
    service = BackgroundGenerationService(index=BackgroundAssetIndex(tmp_path / "index.json"), provider=type("Provider", (), {"generate": lambda *_args, **_kwargs: (_ for _ in ()).throw(ProviderNotConfigured("Connect first."))})())
    service.enqueue(topic="Space")
    result = service.process_next()
    assert result.status == "PAUSED"
    assert "Connect first" in result.message


def test_art_reuse_counts_distinct_active_books_not_rebuild_attempts(tmp_path):
    live = tmp_path / "current_package"; live.mkdir()
    row = {"usage": [
        {"title": "Book A", "theme": "Nature", "package": str(live)},
        {"title": "Book A", "theme": "Nature", "package": str(live)},
        {"title": "Book B", "theme": "Nature", "package": str(tmp_path / "removed_draft")},
        {"title": "Book C", "theme": "Travel", "package": ""},
    ]}
    active = BackgroundAssetIndex.active_usage(row)
    assert {use["title"] for use in active} == {"Book A", "Book C"}
