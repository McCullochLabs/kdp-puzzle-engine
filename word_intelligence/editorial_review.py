"""Explainable, human-controlled editorial review assistance.

This service ranks and groups review work. It never alters source banks and it
never converts a candidate to approved without an explicit decision overlay.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .book_planning import PlanRequest
from .capacity import CapacityRequest, REVIEW_STRICT
from .qualification import prequalification_reasons


@dataclass(frozen=True)
class ReviewCandidate:
    content_id: str
    display: str
    tier: str
    score: int
    reasons: tuple[str, ...]
    mini_theme: str


@dataclass(frozen=True)
class ReviewPriority:
    topic_id: str
    puzzle_type: str
    format_id: str
    approved: int
    required: int
    qualified_candidates: int
    approvals_needed: int
    priority: str
    reason: str


class EditorialPriorityEngine:
    """Small deterministic ranking layer over the existing capacity engine."""
    def __init__(self, planner) -> None:
        self.planner = planner

    def candidates(self, request: PlanRequest, *, limit: int = 40) -> list[ReviewCandidate]:
        topic = self.planner.engine.taxonomy.resolve(request.topic_id)
        if not topic:
            return []
        seen: set[str] = set(); rows: list[ReviewCandidate] = []
        for record in self.planner.engine._topic_records(topic, request.allow_related_topics):
            decision = self.planner.approvals.get(record.id)
            if record.quality.editorial_status == "approved" or decision and decision.decision in {"approved", "rejected"}:
                continue
            reasons = list(prequalification_reasons(record, topic, request.puzzle_type))
            if record.normalized in seen:
                reasons.append("duplicate_normalized")
            seen.add(record.normalized)
            score = 0
            if not reasons: score += 50
            if record.provenance and record.provenance.source_type in {"curated", "public_domain"}: score += 20
            if any(link.topic_id == topic and link.relationship == "primary" for link in record.topics): score += 15
            if record.payload.get("mini_theme"): score += 8
            if 3 <= len(record.normalized) <= 16: score += 7
            if record.quality.trademark_review or record.quality.safety_review: reasons.append("safety_or_trademark_review")
            if "safety_or_trademark_review" in reasons or "blank_normalized" in reasons:
                tier = "Reject Recommended"
            elif any(flag in reasons for flag in {"word_search_too_long", "wrong_content_type", "mechanically_patterned", "duplicate_normalized", "incomplete_trivia", "invalid_scramble_answer"}):
                tier = "Poor Candidate"
            elif reasons:
                tier = "Review Carefully"
            else:
                tier = "Strong Candidate"
            explanation = []
            if not reasons: explanation.append("Format safe and topic-linked")
            explanation.extend(reasons)
            rows.append(ReviewCandidate(record.id, record.display, tier, score, tuple(explanation), str(record.payload.get("mini_theme") or "")))
        tier_order = {"Strong Candidate": 0, "Review Carefully": 1, "Poor Candidate": 2, "Reject Recommended": 3}
        return sorted(rows, key=lambda row: (tier_order[row.tier], -row.score, row.display.casefold(), row.content_id))[:max(1, limit)]

    def priority(self, request: PlanRequest) -> ReviewPriority:
        capacity = self.planner.engine.evaluate(CapacityRequest(request.topic_id, request.puzzle_type, request.puzzle_count, request.items_per_puzzle, review_policy=REVIEW_STRICT, freshness_policy=request.freshness_policy, series_scope=request.series_scope, allow_related_topics=request.allow_related_topics))
        rows = self.candidates(request, limit=500)
        strong = sum(row.tier == "Strong Candidate" for row in rows)
        gap = max(0, capacity.required_count - capacity.verified_capacity)
        if gap == 0:
            level, reason = "READY", "The exact strict format is already available."
        elif strong >= gap:
            level, reason = "HIGH PRIORITY", f"{gap} approvals could unlock this exact format; {strong} strong candidates are available."
        elif strong:
            level, reason = "MEDIUM PRIORITY", f"{gap} approvals are needed, but only {strong} strong candidates are currently available."
        else:
            level, reason = "LOWER PRIORITY", "No strong candidates are currently available; improve topic mapping or add new unreviewed candidates first."
        return ReviewPriority(request.topic_id, request.puzzle_type, request.format_id, capacity.verified_capacity, capacity.required_count, strong, gap, level, reason)

    def next_best_batch(self, requests: list[PlanRequest], *, batch_size: int = 40) -> tuple[ReviewPriority, list[ReviewCandidate]] | None:
        choices = [self.priority(request) for request in requests]
        actionable = [item for item in choices if item.approvals_needed and item.qualified_candidates]
        if not actionable:
            return None
        chosen = min(actionable, key=lambda item: (item.approvals_needed, -item.qualified_candidates, item.topic_id))
        request = next(item for item in requests if item.topic_id == chosen.topic_id and item.puzzle_type == chosen.puzzle_type and item.format_id == chosen.format_id)
        return chosen, [row for row in self.candidates(request, limit=batch_size) if row.tier == "Strong Candidate"]
