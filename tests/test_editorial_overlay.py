import json

from word_intelligence.editorial_overlay import apply_store_overlay, merge_master_bank
from word_intelligence.store import WordIntelligenceStore
from word_intelligence.taxonomy import TopicTaxonomy
from tools.promote_editorial_wordsearch_rebuilds import clean_page_name, presentation_order


def _write_overlay(tmp_path, status="APPROVED_FOR_LOCAL_PRODUCTION"):
    folder = tmp_path / "word_banks"
    folder.mkdir()
    (folder / "editorial_wordsearch_topic_overlay.json").write_text(json.dumps({
        "status": status,
        "topics": {"Vehicles & Automotive": ["CLUTCHPEDAL", "ROADATLAS"]},
        "word_profiles": {"CLUTCHPEDAL": {"topics": ["Vehicles & Automotive"], "sources": ["editorial_wordsearch_rebuild_v2"]}},
    }), encoding="utf-8")


def test_approved_overlay_merges_without_rewriting_source_bank(tmp_path):
    _write_overlay(tmp_path)
    bank = {"topics": {"Vehicles & Automotive": ["ENGINE"]}, "word_profiles": {}, "words": ["ENGINE"]}
    merged = merge_master_bank(bank, tmp_path)
    assert set(merged["topics"]["Vehicles & Automotive"]) == {"ENGINE", "CLUTCHPEDAL", "ROADATLAS"}
    assert "Vehicles & Automotive" in merged["word_profiles"]["CLUTCHPEDAL"]["topics"]


def test_unapproved_overlay_is_ignored(tmp_path):
    _write_overlay(tmp_path, "REVIEW_REQUIRED")
    bank = {"topics": {"Vehicles & Automotive": ["ENGINE"]}, "word_profiles": {}, "words": ["ENGINE"]}
    assert merge_master_bank(bank, tmp_path)["topics"]["Vehicles & Automotive"] == ["ENGINE"]


def test_approved_overlay_is_visible_to_word_intelligence_store(tmp_path):
    _write_overlay(tmp_path)
    bank = {"topics": {"Vehicles & Automotive": ["ENGINE"]}}
    taxonomy = TopicTaxonomy.from_master_bank(bank)
    store = WordIntelligenceStore(); store.ingest_master_bank(bank, taxonomy)
    result = apply_store_overlay(store, taxonomy, tmp_path)
    topic = taxonomy.resolve("Vehicles & Automotive")
    assert result["added"] == 2
    assert store.get("CLUTCHPEDAL").link_for(topic).status == "approved"
    assert "CLUTCHPEDAL" in store.topic_lexicon[topic]


def test_presentation_order_mixes_alphabetical_lists_deterministically():
    words = ["ALPHA", "BRAVO", "CHARLIE", "DELTA", "ECHO", "FOXTROT", "GOLF", "HOTEL"]
    first = presentation_order("sample", 1, words)
    second = presentation_order("sample", 1, words)
    assert first == second
    assert first != words
    assert sorted(first) == sorted(words)


def test_presentation_order_preserves_existing_editorial_order():
    words = ["GOLF", "ALPHA", "HOTEL", "BRAVO", "ECHO", "CHARLIE", "FOXTROT", "DELTA"]
    assert presentation_order("sample", 1, words) == words


def test_clean_page_name_removes_provider_bookkeeping():
    assert clean_page_name("Page 58: The Sower and the Seed") == "The Sower and the Seed"
    assert clean_page_name("Page 18 - Roadside Stops") == "Roadside Stops"
    assert clean_page_name("Forest Ecosystems") == "Forest Ecosystems"
