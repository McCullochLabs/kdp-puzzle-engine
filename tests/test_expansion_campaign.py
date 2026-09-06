from __future__ import annotations

from word_intelligence.book_planning import BookPlanner, PlanRequest
from word_intelligence.capacity import ContentCapacityEngine
from word_intelligence.content_contracts import ContentRecord, FormatRules, Provenance, QualityStatus, TopicReference, deterministic_content_id, normalized_value
from word_intelligence.content_registry import ContentRegistry
from word_intelligence.expansion_campaign import ExpansionCampaignService
from word_intelligence.taxonomy import TopicTaxonomy


def test_campaign_is_goal_specific_and_uses_existing_candidates_only(tmp_path):
    taxonomy = TopicTaxonomy.from_master_bank({"topics": {"Gardening": ["TROWEL"]}})
    registry = ContentRegistry()
    record = ContentRecord(deterministic_content_id("word", "TROWEL", source_id="fixture"), "word", "TROWEL", normalized_value("TROWEL"),
                           (TopicReference("gardening", "primary", 100, "legacy_unreviewed"),), format_rules=FormatRules(),
                           quality=QualityStatus("legacy_unreviewed", "verified", False, False), provenance=Provenance("curated", "fixture"))
    registry.add(record)
    engine = ContentCapacityEngine(tmp_path, taxonomy, registry, cache_state={"state": "fresh"})
    planner = BookPlanner(engine)
    request = PlanRequest(taxonomy.resolve("Gardening"), "word_search", 1, 1)
    service = ExpansionCampaignService(planner, tmp_path)
    campaign = service.create(request)
    assert campaign.minimum_deficit == 1
    assert campaign.candidate_ids == (record.id,)
    assert campaign.status == "candidate_generation_complete"
    path = service.save(campaign)
    assert path.is_file() and "candidate_generation_complete" in path.read_text(encoding="utf-8")
    gathered = service.gather_existing(campaign, request)
    assert gathered[0].source_content_id == record.id
    assert gathered[0].status == "generated_unreviewed"
    assert service.load_candidates()[0]["candidate_id"] == gathered[0].candidate_id
