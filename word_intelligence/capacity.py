"""Truthful, format-specific capacity intelligence (Phase 2).

This module is deliberately read-only over content sources, themes, packages,
and publishing history.  It answers whether *eligible content* exists for a
requested format; it does not allocate a book or change any generator.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
from typing import Iterable

from .cache_manifest import build_manifest, compare_manifest, load_manifest
from .content_contracts import ContentRecord, normalized_value
from .content_registry import ContentRegistry, load_master_bank_legacy, load_puzzle_content_library_legacy
from .pipeline import load_taxonomy
from publishing.puzzle_types import resolve_puzzle_type

REVIEW_STRICT = "strict_verified"
REVIEW_LEGACY = "legacy_compatible"
REVIEW_POLICIES = frozenset({REVIEW_STRICT, REVIEW_LEGACY})
FRESHNESS_POLICIES = frozenset({"allow_all", "no_repeat_within_book", "avoid_prior_series_use", "exclude_prior_series_use", "exclude_all_prior_published_use"})
WORD_SEARCH_TYPES = frozenset({"word", "phrase"})
MECHANICAL_PROMPT_MARKERS = (
    "CURIOSITY MAKES ", " IS ONE PART OF A BIGGER STORY", "A CAREFUL LOOK AT ",
    " INVITES PATIENT THINKING", " CAN OPEN A NEW PATH TO ",
)


@dataclass(frozen=True)
class CapacityRequest:
    topic_id: str
    puzzle_type: str
    puzzle_count: int
    items_per_puzzle: int
    review_policy: str = REVIEW_STRICT
    freshness_policy: str = "allow_all"
    series_scope: str = ""
    current_content_ids: frozenset[str] = frozenset()
    allow_related_topics: bool = False
    cryptogram_max_characters: int = 110

    @property
    def format_id(self) -> str:
        return f"{self.puzzle_count}x{self.items_per_puzzle}"

    @property
    def required_count(self) -> int:
        return self.puzzle_count * self.items_per_puzzle


@dataclass
class VerifiedCapacityResult:
    topic_id: str
    puzzle_type: str
    format_id: str
    required_count: int
    raw_candidate_count: int = 0
    canonical_record_count: int = 0
    approved_count: int = 0
    topic_linked_count: int = 0
    primary_topic_count: int = 0
    related_topic_count: int = 0
    format_valid_count: int = 0
    fresh_count: int = 0
    reserved_or_unavailable_count: int = 0
    duplicate_exclusions: int = 0
    verified_capacity: int = 0
    margin: int = 0
    status: str = "insufficient_verified_content"
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    alternatives: list[str] = field(default_factory=list)
    source_revision: str = ""
    cache_state: str = "unknown_legacy_cache"
    excluded_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1, "topic_id": self.topic_id, "puzzle_type": self.puzzle_type,
            "format_id": self.format_id, "required_count": self.required_count,
            "raw_candidate_count": self.raw_candidate_count,
            "canonical_record_count": self.canonical_record_count,
            "approved_count": self.approved_count, "topic_linked_count": self.topic_linked_count,
            "primary_topic_count": self.primary_topic_count, "related_topic_count": self.related_topic_count,
            "format_valid_count": self.format_valid_count, "fresh_count": self.fresh_count,
            "reserved_or_unavailable_count": self.reserved_or_unavailable_count,
            "duplicate_exclusions": self.duplicate_exclusions, "verified_capacity": self.verified_capacity,
            "margin": self.margin, "status": self.status, "blockers": list(self.blockers),
            "warnings": list(self.warnings), "alternatives": list(self.alternatives),
            "source_revision": self.source_revision, "cache_state": self.cache_state,
            "excluded_counts": dict(sorted(self.excluded_counts.items())),
        }


def _normal_set(values: Iterable[object]) -> set[str]:
    return {normalized_value(value) for value in values if normalized_value(value)}


def load_reservation_evidence(project_root: Path | str) -> list[dict[str, object]]:
    """Read the existing reservation store only; never infer use from titles."""
    path = Path(project_root) / "data" / "word_reservations.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return []
    evidence = []
    for row in data.get("books", []) if isinstance(data, dict) else []:
        if isinstance(row, dict):
            evidence.append({"words": _normal_set(row.get("words", [])),
                             "scope_key": str(row.get("scope_key") or ""),
                             "title": str(row.get("title") or ""),
                             "source": "word_reservations"})
    return evidence


def _is_mechanical_prompt(record: ContentRecord) -> bool:
    text = record.display.upper()
    return any(marker in text for marker in MECHANICAL_PROMPT_MARKERS)


class ContentCapacityEngine:
    """Reusable, read-only capacity API for future UI and planning phases."""
    def __init__(self, project_root: Path | str, taxonomy, registry: ContentRegistry,
                 *, cache_state: dict[str, object] | None = None, approval_decisions: dict[str, object] | None = None) -> None:
        self.root = Path(project_root)
        self.taxonomy = taxonomy
        self.registry = registry
        self.reservation_evidence = load_reservation_evidence(self.root)
        # Human editorial decisions are an overlay, never a mutation of the
        # source bank.  Keep them in the authoritative capacity fingerprint so
        # a plan cannot remain current after its eligible content changed.
        self.approval_decisions = approval_decisions or {}
        self.cache_state = cache_state or {"state": "unknown_legacy_cache", "reasons": []}
        self.manifest = build_manifest(self.root)
        approvals = {key: {"decision": str(getattr(value, "decision", "")), "topic_id": str(getattr(value, "topic_id", "")),
                           "factual_status": str(getattr(value, "factual_status", ""))}
                     for key, value in sorted(self.approval_decisions.items())}
        proof = json.dumps({"manifest": self.manifest.get("source_hashes"), "approvals": approvals, "schema": 2}, sort_keys=True)
        self.source_revision = hashlib.sha256(proof.encode("utf-8")).hexdigest()

    @classmethod
    def from_project(cls, project_root: Path | str = ".", approval_input: Path | str | None = None) -> "ContentCapacityEngine":
        root = Path(project_root)
        taxonomy = load_taxonomy(root)
        master = load_master_bank_legacy(root / "word_banks" / "Guided_Builder_Master_Word_Bank.json", taxonomy)
        library = load_puzzle_content_library_legacy(root / "word_banks" / "puzzle_content_library.json", taxonomy)
        registry = ContentRegistry()
        for item in [*master.records.values(), *library.records.values()]: registry.add(item)
        store_path = root / "word_banks" / "word_intelligence" / "word_store.json"
        manifest_path = root / "word_banks" / "word_intelligence" / "source_manifest.json"
        current = build_manifest(root)
        raw_state = compare_manifest(load_manifest(manifest_path), current)
        if raw_state.get("state") == "missing_manifest" and store_path.exists():
            raw_state = {**raw_state, "state": "unknown_legacy_cache"}
        approvals = {}
        if approval_input:
            from .qualification import load_approval_input
            approvals = load_approval_input(approval_input)
        return cls(root, taxonomy, registry, cache_state=raw_state, approval_decisions=approvals)

    def evaluate(self, request: CapacityRequest) -> VerifiedCapacityResult:
        if request.review_policy not in REVIEW_POLICIES:
            raise ValueError(f"Unknown review policy: {request.review_policy}")
        if request.freshness_policy not in FRESHNESS_POLICIES:
            raise ValueError(f"Unknown freshness policy: {request.freshness_policy}")
        if request.puzzle_count < 1 or request.items_per_puzzle < 1:
            raise ValueError("puzzle_count and items_per_puzzle must be positive.")
        capability = resolve_puzzle_type(request.puzzle_type)
        if capability is None:
            return VerifiedCapacityResult(request.topic_id, request.puzzle_type, request.format_id, request.required_count,
                status="unsupported_format", blockers=[f"Unknown puzzle type: {request.puzzle_type}. Choose a registered puzzle type."],
                source_revision=self.source_revision, cache_state=str(self.cache_state.get("state")))
        if not capability.production_available:
            return VerifiedCapacityResult(request.topic_id, capability.type_id, request.format_id, request.required_count,
                status="unsupported_format", blockers=[f"{capability.display_name} is registered as {capability.lifecycle} and cannot enter normal production yet."],
                warnings=list(capability.known_limitations), source_revision=self.source_revision,
                cache_state=str(self.cache_state.get("state")))
        canonical_type = capability.type_id
        topic = self.taxonomy.resolve(request.topic_id)
        if canonical_type == "sudoku":
            return self._sudoku_result(request, topic)
        if canonical_type == "mixed":
            return VerifiedCapacityResult(topic or request.topic_id, canonical_type, request.format_id, request.required_count,
                status="composite_format_requires_recipe", blockers=["Mixed Brain Games capacity is assessed from its selected component formats; build a recipe in Puzzle Studio."],
                source_revision=self.source_revision, cache_state=str(self.cache_state.get("state")))
        if not topic:
            return VerifiedCapacityResult(request.topic_id, request.puzzle_type, request.format_id, request.required_count,
                status="needs_topic_review", blockers=["The requested topic does not resolve to a canonical Master Library topic."],
                source_revision=self.source_revision, cache_state=str(self.cache_state.get("state")))
        expected_type = frozenset(capability.content_record_types)
        if not expected_type:
            return VerifiedCapacityResult(topic, request.puzzle_type, request.format_id, request.required_count,
                status="unsupported_format", blockers=[f"{capability.display_name} has no reviewed editorial content contract."],
                source_revision=self.source_revision, cache_state=str(self.cache_state.get("state")))
        return self._editorial_result(request, topic, expected_type)

    def _topic_records(self, topic: str, allow_related: bool) -> list[ContentRecord]:
        direct = self.registry.find(topic_id=topic)
        if not allow_related: return direct
        related = self.taxonomy.related_closure(topic, hops=1)
        return [*direct, *(record for related_id in related for record in self.registry.find(topic_id=related_id))]

    def _editorial_result(self, request: CapacityRequest, topic: str, expected_types: frozenset[str]) -> VerifiedCapacityResult:
        result = VerifiedCapacityResult(topic, request.puzzle_type, request.format_id, request.required_count,
            source_revision=self.source_revision, cache_state=str(self.cache_state.get("state")))
        candidates = self._topic_records(topic, request.allow_related_topics)
        result.raw_candidate_count = len(candidates)
        result.canonical_record_count = len({record.id for record in candidates})
        counts: Counter[str] = Counter()
        related_ids = self.taxonomy.related_closure(topic, hops=1) if request.allow_related_topics else set()
        primary, related, eligible = [], [], []
        seen_normalized: set[str] = set()
        for record in candidates:
            decision = self.approval_decisions.get(record.id)
            decision_approved = bool(decision and getattr(decision, "decision", "") == "approved")
            decision_topic = str(getattr(decision, "topic_id", "") or "")
            if record.type not in expected_types:
                counts["wrong_content_type"] += 1; continue
            matching = [link for link in record.topics if link.topic_id == topic]
            matching_related = [link for link in record.topics if link.topic_id in related_ids]
            accepted_topic_states = {"approved"} if request.review_policy == REVIEW_STRICT else {"approved", "legacy_unreviewed"}
            if decision_approved and (not decision_topic or decision_topic == topic):
                primary.append(record)
            elif any(link.status in accepted_topic_states for link in matching):
                primary.append(record)
            elif request.allow_related_topics and any(link.status == "approved" for link in matching_related):
                related.append(record)
            else:
                counts["topic_ineligible"] += 1; continue
            if record.quality.editorial_status == "approved" or decision_approved:
                pass
            elif request.review_policy == REVIEW_LEGACY and record.quality.editorial_status == "legacy_unreviewed":
                counts["legacy_compatible"] += 1
            else:
                counts["review_ineligible"] += 1; continue
            if record.quality.trademark_review or record.quality.safety_review:
                counts["safety_review"] += 1; continue
            if record.provenance is None:
                counts["missing_provenance"] += 1; continue
            if request.puzzle_type == "word_search":
                if not record.normalized:
                    counts["blank_normalized"] += 1; continue
                if len(record.normalized) > 21:
                    counts["word_search_too_long"] += 1; continue
            elif request.puzzle_type == "cryptogram":
                if not record.display or len(record.display) > request.cryptogram_max_characters:
                    counts["cryptogram_layout_invalid"] += 1; continue
                if _is_mechanical_prompt(record):
                    counts["mechanical_prompt"] += 1
                    if request.review_policy == REVIEW_STRICT: continue
            elif request.puzzle_type == "scramble_trivia":
                question = str(record.payload.get("question") or "").strip()
                answer = str(record.payload.get("answer") or "").strip()
                if not question or not answer:
                    counts["incomplete_trivia"] += 1; continue
                if len(record.normalized) < 4 or not record.normalized.isalpha():
                    counts["invalid_scramble_answer"] += 1; continue
                factual_verified = record.quality.factual_status == "verified" or str(getattr(decision, "factual_status", "")) == "verified"
                if not factual_verified:
                    if request.review_policy == REVIEW_STRICT:
                        counts["factual_review_needed"] += 1; continue
                    counts["legacy_factual_compatible"] += 1
            if record.normalized in seen_normalized:
                counts["duplicate_normalized"] += 1; result.duplicate_exclusions += 1; continue
            seen_normalized.add(record.normalized); eligible.append(record)
        result.primary_topic_count = len(primary)
        result.related_topic_count = len(related)
        result.topic_linked_count = len(primary) + len(related)
        result.approved_count = sum(1 for r in candidates if r.quality.editorial_status == "approved")
        result.format_valid_count = len(eligible)
        fresh = self._fresh_records(eligible, request, counts)
        result.fresh_count = len(fresh)
        result.reserved_or_unavailable_count = max(0, len(eligible) - len(fresh))
        result.verified_capacity = len(fresh)
        result.margin = result.verified_capacity - result.required_count
        result.excluded_counts = dict(counts)
        if self.cache_state.get("state") in {"stale", "unknown_legacy_cache", "unsupported_manifest"}:
            result.warnings.append("Persisted Word Intelligence cache is " + str(self.cache_state.get("state")) + "; capacity was calculated directly from current legacy source files.")
        if request.review_policy == REVIEW_LEGACY and counts.get("legacy_compatible"):
            result.warnings.append(f"{counts['legacy_compatible']} records count only under legacy-compatible policy, not strict verified policy.")
        if counts.get("mechanical_prompt"):
            result.warnings.append(f"{counts['mechanical_prompt']} mechanically patterned prompts were excluded from strict verified capacity.")
        if result.verified_capacity >= result.required_count:
            result.status = "ready"
        elif result.verified_capacity == 0 and counts.get("review_ineligible"):
            result.status = "needs_editorial_review"
        elif result.verified_capacity == 0 and not result.topic_linked_count:
            result.status = "needs_topic_review"
        else:
            result.status = "insufficient_verified_content"
        if result.status != "ready":
            result.blockers.append(f"{result.required_count} required; {result.verified_capacity} eligible and fresh records are available.")
            result.alternatives = self._alternatives(result.verified_capacity, request)
        return result

    def _fresh_records(self, records: list[ContentRecord], request: CapacityRequest, counts: Counter[str]) -> list[ContentRecord]:
        output = []
        for record in records:
            if record.id in request.current_content_ids:
                counts["used_in_current_book"] += 1; continue
            hits = [row for row in self.reservation_evidence if record.normalized in row["words"]]
            if not hits or request.freshness_policy in {"allow_all", "no_repeat_within_book"}:
                output.append(record); continue
            in_series = bool(request.series_scope and any(row["scope_key"] == request.series_scope for row in hits))
            if request.freshness_policy == "avoid_prior_series_use":
                if in_series: counts["prior_series_warning"] += 1
                output.append(record); continue
            if request.freshness_policy == "exclude_prior_series_use" and in_series:
                counts["prior_series_reserved"] += 1; continue
            if request.freshness_policy == "exclude_all_prior_published_use":
                counts["prior_reserved"] += 1; continue
            output.append(record)
        return output

    @staticmethod
    def _alternatives(available: int, request: CapacityRequest) -> list[str]:
        if not available: return ["Expand reviewed, topic-linked source content before promising this format."]
        possible = available // request.items_per_puzzle
        suggestions = []
        if possible:
            suggestions.append(f"Use up to {possible} puzzles × {request.items_per_puzzle} items with the current policy.")
        if request.puzzle_type == "word_search" and request.items_per_puzzle != 12:
            suggestions.append(f"A 12-word format could support up to {available // 12} puzzles; use it only if that product format is intentionally chosen.")
        suggestions.append("Expand reviewed source content or explicitly allow approved related topics; do not silently weaken the requested book.")
        return suggestions

    def _sudoku_result(self, request: CapacityRequest, topic: str | None) -> VerifiedCapacityResult:
        result = VerifiedCapacityResult(topic or request.topic_id, "sudoku", request.format_id, request.required_count,
            raw_candidate_count=0, canonical_record_count=0, approved_count=0, topic_linked_count=0,
            format_valid_count=request.required_count, fresh_count=request.required_count,
            verified_capacity=request.required_count, margin=0, status="ready",
            source_revision=self.source_revision, cache_state=str(self.cache_state.get("state")))
        result.warnings.append("Sudoku capacity is algorithmic. Number, letter, and shape 9×9 grids remain subject to uniqueness validation at generation time.")
        return result

    def mixed_sections(self, topic_id: str, *, puzzle_count: int = 60, review_policy: str = REVIEW_STRICT,
                       freshness_policy: str = "allow_all") -> dict[str, VerifiedCapacityResult]:
        sudoku_count = puzzle_count // 3 + (1 if puzzle_count % 3 else 0)
        crypto_count = puzzle_count // 3 + (1 if puzzle_count % 3 > 1 else 0)
        trivia_count = puzzle_count - sudoku_count - crypto_count
        return {
            "sudoku": self.evaluate(CapacityRequest(topic_id, "sudoku", sudoku_count, 1, review_policy, freshness_policy)),
            "cryptogram": self.evaluate(CapacityRequest(topic_id, "cryptogram", crypto_count, 1, review_policy, freshness_policy)),
            "scramble_trivia": self.evaluate(CapacityRequest(topic_id, "scramble_trivia", trivia_count, 1, review_policy, freshness_policy)),
        }

    def evaluate_batch(self, requests: Iterable[CapacityRequest]) -> list[VerifiedCapacityResult]:
        """Evaluate a small caller-selected set without rebuilding any sources.

        Phase 2 deliberately keeps this read-only and leaves all-book planning
        and allocation to a later phase.  Reusing one engine instance keeps the
        registry, manifest proof, and reservation evidence consistent.
        """
        return [self.evaluate(request) for request in requests]


def evaluate_capacity(topic_id: str, puzzle_type: str, puzzle_count: int, items_per_puzzle: int,
                      review_policy: str = REVIEW_STRICT, freshness_policy: str = "allow_all", **kwargs) -> VerifiedCapacityResult:
    """Narrow public API for later UI and planning phases."""
    engine = ContentCapacityEngine.from_project(kwargs.pop("project_root", "."))
    return engine.evaluate(CapacityRequest(topic_id, puzzle_type, puzzle_count, items_per_puzzle,
                                           review_policy, freshness_policy, **kwargs))
