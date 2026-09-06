"""Regression coverage for locally cached public-domain topic vocabulary."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import build_master_word_bank as bank
from tools import import_public_domain_bible_terms as bible_import
from tools import import_public_domain_us_history_terms as history_import


def test_bible_import_removes_pre_content_source_boilerplate():
    terms = bible_import._terms(
        "Project Gutenberg license words\nBook 01 Genesis\n"
        "Abraham visited Jerusalem and Abraham prayed in Jerusalem.\n")
    assert "GUTENBERG" not in terms
    assert "ABRAHAM" in terms and "JERUSALEM" in terms


def test_history_import_removes_gutenberg_wrapper():
    text = (
        "Project Gutenberg preliminary text\n*** START OF TEST ***\n"
        "American history chapter\n*** END OF TEST ***\nsource footer")
    content = history_import._content(text)
    assert "preliminary" not in content
    assert "American history chapter" in content
    assert "source footer" not in content


def test_local_public_domain_cache_is_gated_like_other_sources(tmp_path, monkeypatch):
    source_data = tmp_path / "source_data"
    source_data.mkdir()
    (source_data / "terms.json").write_text(
        json.dumps({"terms": ["Jerusalem", "DISNEY", "x", "wellness"]}),
        encoding="utf-8")
    monkeypatch.setattr(bank, "WORD_BANKS_DIR", tmp_path)
    assert bank._local_public_domain_terms("terms.json") == {"JERUSALEM", "WELLNESS"}
