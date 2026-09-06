"""Local-first, non-approving content expansion campaign contracts."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from math import ceil
from pathlib import Path

from .book_planning import PlanRequest
from .capacity import CapacityRequest, REVIEW_STRICT
from .content_contracts import normalized_value
from .editorial_review import EditorialPriorityEngine

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ExpansionCampaign:
    campaign_id: str
    topic_id: str
    content_type: str
    puzzle_type: str
    target_format: dict[str, int]
    required_capacity: int
    verified_capacity_before: int
    minimum_deficit: int
    recommended_capacity_target: int
    review_pool_estimate: int
    candidate_sources: tuple[str, ...] = ()
    candidate_ids: tuple[str, ...] = ()
    mini_theme_gaps: tuple[str, ...] = ()
    status: str = "candidate_generation_complete"
    created_at: str = ""
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, object]:
        value = asdict(self); value["candidate_sources"] = list(self.candidate_sources); value["candidate_ids"] = list(self.candidate_ids); value["mini_theme_gaps"] = list(self.mini_theme_gaps)
        return value


@dataclass(frozen=True)
class ExpansionCandidate:
    candidate_id: str
    campaign_id: str
    source_content_id: str
    display: str
    normalized: str
    topic_id: str
    puzzle_type: str
    tier: str
    reasons: tuple[str, ...]
    provenance: str = "existing_content_registry"
    status: str = "generated_unreviewed"

    def to_dict(self) -> dict[str, object]:
        data = asdict(self); data["reasons"] = list(self.reasons); return data


class ExpansionCampaignService:
    """Build campaign records from the current registry only.

    Candidate generation and approval deliberately remain separate future
    actions. A campaign can be opened repeatedly without source mutations.
    """
    def __init__(self, planner, root: Path | str) -> None:
        self.planner, self.root = planner, Path(root)

    @property
    def directory(self) -> Path:
        return self.root / "data" / "content_expansion_campaigns"

    @property
    def candidate_store_path(self) -> Path:
        return self.root / "data" / "content_expansion_candidates.json"

    def create(self, request: PlanRequest, *, target_type: str = "unlock_format", buffer: int = 48, max_candidates: int = 120) -> ExpansionCampaign:
        capacity = self.planner.engine.evaluate(CapacityRequest(request.topic_id, request.puzzle_type, request.puzzle_count, request.items_per_puzzle, review_policy=REVIEW_STRICT, freshness_policy=request.freshness_policy, series_scope=request.series_scope, allow_related_topics=request.allow_related_topics))
        priority = EditorialPriorityEngine(self.planner)
        candidates = priority.candidates(request, limit=max_candidates)
        deficit = max(0, capacity.required_count - capacity.verified_capacity)
        # A review-pool estimate, never a promised approval result.
        estimate = min(max_candidates, max(deficit, ceil(deficit / 0.70))) if deficit else 0
        mini = sorted({row.mini_theme for row in candidates if row.mini_theme})
        digest = hashlib.sha256(json.dumps({"topic": request.topic_id, "type": request.puzzle_type, "format": request.format_id, "revision": self.planner.engine.source_revision, "goal": target_type}, sort_keys=True).encode("utf-8")).hexdigest()[:20]
        content_type = {"word_search": "word_or_phrase", "cryptogram": "cryptogram_prompt", "scramble_trivia": "trivia", "mixed": "mixed"}.get(request.puzzle_type, "algorithmic")
        return ExpansionCampaign(digest, request.topic_id, content_type, request.puzzle_type,
            {"puzzle_count": request.puzzle_count, "items_per_puzzle": request.items_per_puzzle}, capacity.required_count,
            capacity.verified_capacity, deficit, capacity.required_count + max(0, buffer), estimate,
            ("existing_content_registry",), tuple(row.content_id for row in candidates[:estimate or max_candidates]), tuple(mini),
            "candidate_generation_complete" if candidates or not deficit else "needs_candidate_discovery",
            datetime.now(timezone.utc).isoformat(timespec="seconds"))

    def save(self, campaign: ExpansionCampaign) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        target = self.directory / f"{campaign.campaign_id}.json"
        target.write_text(json.dumps(campaign.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return target

    def gather_existing(self, campaign: ExpansionCampaign, request: PlanRequest) -> list[ExpansionCandidate]:
        """Persist screened existing candidates; never generate or approve new content."""
        ranked = EditorialPriorityEngine(self.planner).candidates(request, limit=max(1, len(campaign.candidate_ids) or 120))
        rows = []
        for item in ranked:
            identity = hashlib.sha256(f"existing|{item.content_id}|{campaign.topic_id}|{campaign.puzzle_type}".encode("utf-8")).hexdigest()[:24]
            record = self.planner.engine.registry.get(item.content_id)
            if not record:
                continue
            rows.append(ExpansionCandidate(identity, campaign.campaign_id, item.content_id, item.display, record.normalized,
                                           campaign.topic_id, campaign.puzzle_type, item.tier, item.reasons))
        prior = {str(row.get("candidate_id") or ""): row for row in self.load_candidates()}
        for row in rows:
            prior.setdefault(row.candidate_id, row.to_dict())
        self.candidate_store_path.parent.mkdir(parents=True, exist_ok=True)
        self.candidate_store_path.write_text(json.dumps({"schema_version": 1, "candidates": list(prior.values())}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return rows

    def load_candidates(self) -> list[dict[str, object]]:
        try:
            payload = json.loads(self.candidate_store_path.read_text(encoding="utf-8-sig"))
            return [row for row in payload.get("candidates") or [] if isinstance(row, dict)]
        except (OSError, json.JSONDecodeError):
            return []

    def store_generated(self, campaign: ExpansionCampaign, items) -> int:
        """Store provider output as review-only candidates; approval is separate."""
        from .candidate_generation import CandidateGenerationService, GenerationRequest
        request = GenerationRequest(campaign.campaign_id, campaign.topic_id, campaign.puzzle_type, len(items), explicit_provider_action=True)
        prior = {str(row.get("candidate_id") or ""): row for row in self.load_candidates()}
        for item in items:
            candidate_id = CandidateGenerationService.stable_generated_id(request, item)
            normal = normalized_value(item.display)
            prior.setdefault(candidate_id, ExpansionCandidate(candidate_id, campaign.campaign_id, "", item.display, normal,
                campaign.topic_id, campaign.puzzle_type, "Review Carefully", ("Generated candidate — human review required",),
                f"generated:{item.source_reference or 'provider'}", "generated_unreviewed").to_dict())
        self.candidate_store_path.parent.mkdir(parents=True, exist_ok=True)
        self.candidate_store_path.write_text(json.dumps({"schema_version": 1, "candidates": list(prior.values())}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return len(items)
