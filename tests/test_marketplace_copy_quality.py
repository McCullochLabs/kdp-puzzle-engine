from publishing.metadata_service import marketplace_content, marketplace_copy_quality, refresh_marketplace_content


def _space_source():
    return {
        "title": "Planet Explorer Word Search",
        "subtitle": "48 astronomy puzzles for curious minds",
        "detected_topic": "Space & Astronomy",
        "puzzle_count": 48,
        "difficulty_label": "Standard",
        "audience": "adults and teens",
        "puzzle_type": "Word Search",
    }


def test_generated_marketplace_copy_uses_topic_specific_discovery_terms():
    content = marketplace_content(_space_source())
    assert len(content["amazon_keywords"]) == 7
    assert len(content["etsy_tags"]) == 13
    assert "screen free activity" not in content["amazon_keywords"]
    assert any("planet" in item or "astronomy" in item or "constellation" in item for item in content["amazon_keywords"])
    assert "digital download" in content["platform_descriptions"]["etsy"].casefold()


def test_marketplace_copy_quality_reports_specific_copy_without_sales_claims():
    report = marketplace_copy_quality(_space_source(), "amazon")
    assert report["score"] >= 75
    assert report["description_words"] > 0
    assert report["terms"]


def test_refresh_replaces_only_old_auto_generated_blurbs_not_custom_copy():
    old = {**_space_source(), "description": "This makes a satisfying screen-free break.", "platform_descriptions": {"amazon": "A ready-to-enjoy collection for your own puzzle shelf."}}
    refreshed = refresh_marketplace_content(old)
    assert "satisfying screen-free break" not in refreshed["platform_descriptions"]["amazon"].casefold()
    custom = refresh_marketplace_content({**_space_source(), "description": "A carefully written custom description about planets."})
    assert custom["description"] == "A carefully written custom description about planets."
