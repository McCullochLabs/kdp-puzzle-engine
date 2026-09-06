"""Focused Phase 1 tests for additive canonical content contracts."""
from __future__ import annotations

from pathlib import Path

import pytest

from word_intelligence.cache_manifest import build_manifest, compare_manifest
from word_intelligence.content_contracts import (
    ContentContractError, content_record_from_dict, deterministic_content_id,
    normalized_value,
)
from word_intelligence.content_registry import (
    load_master_bank_legacy, load_puzzle_content_library_legacy, load_theme_legacy,
)
from word_intelligence.pipeline import load_taxonomy


def _record(content_type="word", **extra):
    data = {
        "schema_version": 1, "id": "word_garden_trowel", "type": content_type,
        "display": "Garden Trowel", "normalized": "GARDENTROWEL",
        "topics": [{"topic_id": "gardening", "relationship": "primary", "confidence": 100, "status": "approved"}],
        "quality": {"editorial_status": "approved", "factual_status": "not_applicable"},
        "provenance": {"source_type": "curated", "source_id": "fixture"},
    }
    data.update(extra)
    return data


def test_valid_word_and_phrase_records():
    assert content_record_from_dict(_record()).normalized == "GARDENTROWEL"
    phrase = content_record_from_dict(_record("phrase", id="phrase_garden_trowel"))
    assert phrase.type == "phrase"


def test_valid_cryptogram_and_trivia_records():
    crypto = content_record_from_dict(_record("cryptogram_prompt", id="cryptogram_night_sky", display="Look at the Night Sky"))
    trivia = content_record_from_dict(_record("trivia", id="trivia_mars", display="Mars", payload={"question": "Which planet is red?", "answer": "Mars"}, quality={"editorial_status": "approved", "factual_status": "verified"}))
    assert crypto.type == "cryptogram_prompt" and trivia.payload["answer"] == "Mars"


@pytest.mark.parametrize("patch", [
    {"id": ""}, {"type": "sudoku_grid"}, {"topics": [{"topic_id": "garden", "confidence": 101}]},
    {"quality": {"editorial_status": "maybe"}}, {"provenance": None},
])
def test_invalid_contracts_are_actionable(patch):
    data = _record(); data.update(patch)
    with pytest.raises(ContentContractError): content_record_from_dict(data)


def test_normalization_handles_spaces_punctuation_hyphens_case_and_empty():
    assert normalized_value("  Garden-Trowel! ") == "GARDENTROWEL"
    assert normalized_value("gArDeN tRoWeL") == "GARDENTROWEL"
    assert normalized_value("  --  ") == ""


def test_stable_legacy_ids_are_deterministic_and_distinct():
    first = deterministic_content_id("word", "Garden Trowel", source_id="master:garden")
    assert first == deterministic_content_id("word", "garden-trowel", source_id="master:garden")
    assert first != deterministic_content_id("word", "Garden Trowel", source_id="master:tools")


def test_legacy_loaders_keep_content_unreviewed():
    root = Path(__file__).resolve().parents[1]
    taxonomy = load_taxonomy(root)
    master = load_master_bank_legacy(root / "word_banks" / "Guided_Builder_Master_Word_Bank.json", taxonomy)
    library = load_puzzle_content_library_legacy(root / "word_banks" / "puzzle_content_library.json", taxonomy)
    theme = load_theme_legacy(root / "themes" / "90s_nostalgia.json", taxonomy)
    assert master.records and library.records and theme.records
    assert all(record.quality.editorial_status == "legacy_unreviewed" for record in [next(iter(master.records.values())), next(iter(library.records.values())), next(iter(theme.records.values()))])


def test_cache_manifest_detects_changed_or_missing_sources(tmp_path):
    (tmp_path / "master.json").write_text("a", encoding="utf-8")
    sources = {"master_bank": "master.json"}
    saved = build_manifest(tmp_path, sources=sources, record_count=3)
    assert compare_manifest(saved, build_manifest(tmp_path, sources=sources, record_count=3))["fresh"]
    (tmp_path / "master.json").write_text("b", encoding="utf-8")
    assert compare_manifest(saved, build_manifest(tmp_path, sources=sources))["state"] == "stale"
    assert compare_manifest(saved, build_manifest(tmp_path, sources={"missing": "missing.json"}))["state"] == "stale"
