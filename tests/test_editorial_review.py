"""Editorial assistance ranks work but never auto-approves it."""
from __future__ import annotations

from word_intelligence.book_planning import BookPlanner, PlanRequest
from word_intelligence.capacity import ContentCapacityEngine
from word_intelligence.content_contracts import ContentRecord, FormatRules, Provenance, QualityStatus, TopicReference, deterministic_content_id, normalized_value
from word_intelligence.content_registry import ContentRegistry
from word_intelligence.editorial_review import EditorialPriorityEngine
from word_intelligence.taxonomy import TopicTaxonomy


def _record(value: str, *, editorial="legacy_unreviewed"):
    return ContentRecord(deterministic_content_id("word", value, source_id="fixture:" + value), "word", value, normalized_value(value),
                         (TopicReference("gardening", "primary", 100, "legacy_unreviewed"),), format_rules=FormatRules(),
                         quality=QualityStatus(editorial, "verified", False, False), provenance=Provenance("curated", "fixture:" + value))


def _engine(records):
    taxonomy = TopicTaxonomy.from_master_bank({"topics": {"Gardening": ["TROWEL"]}})
    registry = ContentRegistry()
    for record in records: registry.add(record)
    capacity = ContentCapacityEngine(".", taxonomy, registry, cache_state={"state": "fresh"})
    capacity.reservation_evidence = []
    return BookPlanner(capacity), taxonomy.resolve("Gardening")


def test_candidate_ranking_is_explainable_and_never_changes_editorial_state():
    valid, long = _record("TROWEL"), _record("X" * 22)
    planner, topic = _engine([valid, long])
    review = EditorialPriorityEngine(planner)
    candidates = review.candidates(PlanRequest(topic, "word_search", 1, 1))
    assert candidates[0].tier == "Strong Candidate"
    assert any(row.tier == "Poor Candidate" and "word_search_too_long" in row.reasons for row in candidates)
    assert valid.quality.editorial_status == "legacy_unreviewed"


def test_priority_is_based_on_unlock_gap_not_market_claims():
    planner, topic = _engine([_record("TROWEL")])
    priority = EditorialPriorityEngine(planner).priority(PlanRequest(topic, "word_search", 1, 1))
    assert priority.approvals_needed == 1
    assert priority.priority == "HIGH PRIORITY"
    assert "unlock" in priority.reason.casefold()
