"""Deterministic, non-generating Book Plan layer (Content Intelligence Phase 3)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
from typing import Iterable

from .capacity import CapacityRequest, ContentCapacityEngine, REVIEW_LEGACY, REVIEW_STRICT, WORD_SEARCH_TYPES, _is_mechanical_prompt
from .content_contracts import ContentRecord, FormatRules, Provenance, QualityStatus, TopicReference, normalized_value
from .qualification import ApprovalDecision, load_approval_input, prequalification_reasons
from .taxonomy import TopicDef

PLAN_SCHEMA_VERSION = 1


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PlanRequest:
    topic_id: str
    puzzle_type: str
    puzzle_count: int
    items_per_puzzle: int = 1
    seed: int = 7
    difficulty: str = "standard"
    large_print: bool = False
    review_policy: str = REVIEW_STRICT
    freshness_policy: str = "allow_all"
    series_scope: str = ""
    allow_related_topics: bool = False
    general_pool: bool = False
    symbol_set: str = "numbers"
    grid_size: int = 9

    @property
    def format_id(self) -> str:
        return f"{self.puzzle_count}x{self.items_per_puzzle}"

    @property
    def required_count(self) -> int:
        return self.puzzle_count * self.items_per_puzzle


@dataclass(frozen=True)
class PuzzleAllocation:
    puzzle_number: int
    content_ids: tuple[str, ...] = ()
    mini_theme: str = ""
    section: str = ""

    def to_dict(self) -> dict[str, object]:
        return {"puzzle_number": self.puzzle_number, "content_ids": list(self.content_ids),
                "mini_theme": self.mini_theme, "section": self.section}


@dataclass
class BookPlan:
    book_plan_id: str
    created_at: str
    puzzle_type: str
    topic_ids: list[str]
    format: dict[str, object]
    seed: int
    review_policy: str
    freshness_policy: str
    source_revision: str
    capacity_proof: str
    selected_content_ids: list[str] = field(default_factory=list)
    puzzle_allocations: list[PuzzleAllocation] = field(default_factory=list)
    quality_snapshot: dict[str, object] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    freshness_snapshot: dict[str, object] = field(default_factory=dict)
    section_plans: dict[str, "BookPlan"] = field(default_factory=dict)
    schema_version: int = PLAN_SCHEMA_VERSION

    def to_dict(self) -> dict[str, object]:
        return {"schema_version": self.schema_version, "book_plan_id": self.book_plan_id,
                "created_at": self.created_at, "puzzle_type": self.puzzle_type,
                "topic_ids": list(self.topic_ids), "format": dict(self.format), "seed": self.seed,
                "review_policy": self.review_policy, "freshness_policy": self.freshness_policy,
                "source_revision": self.source_revision, "capacity_proof": self.capacity_proof,
                "selected_content_ids": list(self.selected_content_ids),
                "puzzle_allocations": [item.to_dict() for item in self.puzzle_allocations],
                "quality_snapshot": dict(self.quality_snapshot), "warnings": list(self.warnings),
                "freshness_snapshot": dict(self.freshness_snapshot),
                "section_plans": {name: plan.to_dict() for name, plan in self.section_plans.items()}}

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "BookPlan":
        if int(data.get("schema_version") or 0) != PLAN_SCHEMA_VERSION:
            raise ValueError("Unsupported Book Plan schema version.")
        allocations = [PuzzleAllocation(int(row["puzzle_number"]), tuple(row.get("content_ids") or []),
                         str(row.get("mini_theme") or ""), str(row.get("section") or ""))
                       for row in data.get("puzzle_allocations") or []]
        return cls(str(data["book_plan_id"]), str(data.get("created_at") or ""), str(data["puzzle_type"]),
                   list(data.get("topic_ids") or []), dict(data.get("format") or {}), int(data.get("seed") or 0),
                   str(data.get("review_policy") or ""), str(data.get("freshness_policy") or ""),
                   str(data.get("source_revision") or ""), str(data.get("capacity_proof") or ""),
                   list(data.get("selected_content_ids") or []), allocations,
                   dict(data.get("quality_snapshot") or {}), list(data.get("warnings") or []),
                   dict(data.get("freshness_snapshot") or {}),
                   {name: cls.from_dict(value) for name, value in (data.get("section_plans") or {}).items()})


@dataclass
class PlanResult:
    plan: BookPlan | None
    status: str
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    capacity: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class PlanValidation:
    status: str
    reasons: tuple[str, ...] = ()


class BookPlanner:
    """Deterministically select eligible IDs; never generate a puzzle or PDF."""
    def __init__(self, engine: ContentCapacityEngine, approvals: dict[str, ApprovalDecision] | None = None) -> None:
        self.engine = engine
        self.approvals = approvals or {}

    @classmethod
    def from_project(cls, project_root: Path | str = ".", approval_input: Path | str | None = None) -> "BookPlanner":
        approvals = load_approval_input(approval_input) if approval_input else {}
        root = Path(project_root)
        engine = ContentCapacityEngine.from_project(root, approval_input)
        from .topic_routing import TopicRouter
        TopicRouter(root, engine.taxonomy).apply_saved()
        # Approved generated candidates form an additive editorial overlay. They
        # never rewrite source banks and remain absent until an individual human
        # approval decision exists.
        candidate_path = root / "data" / "content_expansion_candidates.json"
        try:
            rows = json.loads(candidate_path.read_text(encoding="utf-8-sig")).get("candidates") or []
        except (OSError, json.JSONDecodeError):
            rows = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            candidate_id = str(row.get("candidate_id") or "")
            approval = approvals.get(candidate_id)
            if not candidate_id or not approval or approval.decision != "approved" or engine.registry.get(candidate_id):
                continue
            display = str(row.get("display") or "").strip(); topic = str(row.get("topic_id") or "").strip()
            normal = normalized_value(display)
            if not display or not normal or not topic:
                continue
            # A user-created topic may not yet exist in the older Master
            # Library. Keep it as a small additive overlay until it is later
            # curated into that library; do not discard its approved content.
            canonical_topic = engine.taxonomy.resolve(topic)
            if not canonical_topic:
                canonical_topic = "_".join(topic.casefold().split())
                related = []
                if canonical_topic == "summer_activities":
                    related = [item for item in ("outdoor_adventure", "weather_climate", "coastal_lake_river_life", "travel_geography", "sports_hobbies") if item in engine.taxonomy.topics]
                engine.taxonomy.topics[canonical_topic] = TopicDef(canonical_topic, topic, [topic], related=related, description="Approved generated-content overlay")
                engine.taxonomy.alias_to_id[topic] = canonical_topic
                engine.taxonomy.trusted_words[canonical_topic] = set()
            engine.taxonomy.trusted_words.setdefault(canonical_topic, set()).add(normal)
            content_type = "phrase" if " " in display else "word"
            engine.registry.add(ContentRecord(candidate_id, content_type, display, normal,
                (TopicReference(canonical_topic, "primary", 100, "approved"),), format_rules=FormatRules(word_search_max_letters=21),
                quality=QualityStatus("approved", "not_applicable", False, False),
                provenance=Provenance("generated", str(row.get("provenance") or "generated"), approval.reviewed_at)))
        return cls(engine, approvals)

    def create(self, request: PlanRequest) -> PlanResult:
        if request.puzzle_type == "mixed":
            return self._mixed_plan(request)
        if request.puzzle_type == "sudoku":
            return self._sudoku_plan(request)
        if request.puzzle_type not in {"word_search", "cryptogram", "scramble_trivia"}:
            return PlanResult(None, "unsupported_format", [f"Unsupported puzzle type: {request.puzzle_type}."])
        candidates, exclusions, warnings = self._eligible_records(request)
        capacity_proof = self._capacity_proof(request, candidates)
        if len(candidates) < request.required_count:
            return PlanResult(None, "insufficient_verified_content",
                              [f"{request.required_count} required; {len(candidates)} eligible records are available."], warnings,
                              {"required_count": request.required_count, "verified_capacity": len(candidates),
                               "excluded_counts": exclusions, "capacity_proof": capacity_proof})
        selected = list(candidates)
        random.Random(request.seed).shuffle(selected)
        selected = selected[:request.required_count]
        if len({record.id for record in selected}) != len(selected) or len({record.normalized for record in selected}) != len(selected):
            return PlanResult(None, "invalid", ["Duplicate content reached the allocation stage."], warnings)
        allocations = self._allocate(request, selected)
        if any(len(row.content_ids) != request.items_per_puzzle for row in allocations):
            return PlanResult(None, "invalid", ["A puzzle allocation is incomplete; the plan was not created."], warnings)
        warning_list = list(warnings)
        mini_themes = [row.mini_theme for row in allocations if row.mini_theme]
        if not mini_themes:
            warning_list.append("mini_theme_map_missing: no trustworthy mini-theme metadata was supplied by the selected records.")
        diversity = len(set(mini_themes)) / max(1, len(allocations)) if mini_themes else 0.0
        max_concentration = max((mini_themes.count(item) for item in set(mini_themes)), default=0) / max(1, len(allocations))
        if mini_themes and max_concentration > 0.70:
            warning_list.append("mini_theme_imbalance: one supplied mini-theme contributes more than 70% of allocations.")
        plan_id = _digest({"source_revision": self.engine.source_revision, "request": asdict(request),
                           "capacity_proof": capacity_proof, "selected": [record.id for record in selected]})[:24]
        plan = BookPlan(plan_id, datetime.now(timezone.utc).isoformat(timespec="seconds"), request.puzzle_type,
                        [self._canonical_topic(request)], self._format(request), request.seed, request.review_policy,
                        request.freshness_policy, self.engine.source_revision, capacity_proof,
                        [record.id for record in selected], allocations,
                        {"topic_fit": 1.0, "diversity_score": round(diversity, 3),
                         "max_mini_theme_concentration": round(max_concentration, 3),
                         "freshness_status": "clean", "related_topics_used": request.allow_related_topics},
                        warning_list,
                        {"history_source": "word_reservations", "excluded_counts": exclusions,
                         "unknown_history_count": 0})
        return PlanResult(plan, "valid", warnings=warning_list,
                          capacity={"required_count": request.required_count, "verified_capacity": len(candidates),
                                    "capacity_proof": capacity_proof, "excluded_counts": exclusions})

    def _eligible_records(self, request: PlanRequest) -> tuple[list[ContentRecord], dict[str, int], list[str]]:
        from collections import Counter
        counts: Counter[str] = Counter(); warnings: list[str] = []
        topic = self.engine.taxonomy.resolve(request.topic_id)
        if not topic and not request.general_pool:
            return [], {"unresolved_topic": 1}, ["The requested topic does not resolve to a canonical topic."]
        definition = self.engine.taxonomy.topics.get(topic or "")
        inferred_related = topic == "summer_activities" or bool(definition and definition.description == "Saved topic connection")
        use_related = request.allow_related_topics or inferred_related
        source = list(self.engine.registry.records.values()) if request.general_pool else self.engine._topic_records(topic, use_related)
        related = self.engine.taxonomy.related_closure(topic, 1) if topic and use_related else set()
        selected: list[ContentRecord] = []; seen: set[str] = set()
        expected = {"word_search": WORD_SEARCH_TYPES, "cryptogram": {"cryptogram_prompt"}, "scramble_trivia": {"trivia"}}[request.puzzle_type]
        for record in sorted(source, key=lambda item: item.id):
            if record.type not in expected:
                counts["wrong_content_type"] += 1; continue
            decision = self.approvals.get(record.id)
            if not request.general_pool and not self._topic_eligible(record, topic, related, request, decision):
                counts["topic_ineligible"] += 1; continue
            if decision and decision.decision == "rejected":
                counts["explicitly_rejected"] += 1; continue
            if not self._review_eligible(record, decision, topic, request):
                counts["review_ineligible"] += 1; continue
            if record.quality.trademark_review or record.quality.safety_review or not record.provenance:
                counts["safety_or_provenance"] += 1; continue
            reasons = prequalification_reasons(record, topic or "general", request.puzzle_type) if not request.general_pool else []
            if request.puzzle_type == "word_search":
                if not record.normalized or len(record.normalized) > 21:
                    counts["word_search_invalid"] += 1; continue
            elif request.puzzle_type == "cryptogram":
                if not record.display or len(record.display) > 110:
                    counts["cryptogram_layout_invalid"] += 1; continue
                if _is_mechanical_prompt(record) and request.review_policy == REVIEW_STRICT:
                    counts["mechanical_prompt"] += 1; continue
            else:
                if not str(record.payload.get("question") or "").strip() or not str(record.payload.get("answer") or "").strip():
                    counts["incomplete_trivia"] += 1; continue
                if len(record.normalized) < 4 or not record.normalized.isalpha():
                    counts["invalid_scramble_answer"] += 1; continue
                factual_ok = record.quality.factual_status == "verified" or bool(decision and decision.factual_status == "verified")
                if not factual_ok and request.review_policy == REVIEW_STRICT:
                    counts["factual_review_needed"] += 1; continue
            if record.normalized in seen:
                counts["duplicate_normalized"] += 1; continue
            seen.add(record.normalized); selected.append(record)
        fresh = self.engine._fresh_records(selected, CapacityRequest(topic or request.topic_id, request.puzzle_type,
            request.puzzle_count, request.items_per_puzzle, request.review_policy, request.freshness_policy,
            request.series_scope), counts)
        if request.review_policy == REVIEW_LEGACY:
            warnings.append("legacy_compatible planning is not strict editorial verification.")
        return fresh, dict(counts), warnings

    def _review_eligible(self, record: ContentRecord, decision: ApprovalDecision | None, topic: str | None, request: PlanRequest) -> bool:
        if request.review_policy == REVIEW_LEGACY:
            return record.quality.editorial_status in {"approved", "legacy_unreviewed"} or bool(decision and decision.is_approval)
        if record.quality.editorial_status == "approved":
            return True
        return bool(decision and decision.is_approval and (not decision.topic_id or decision.topic_id == topic))

    @staticmethod
    def _topic_eligible(record: ContentRecord, topic: str | None, related: set[str], request: PlanRequest,
                        decision: ApprovalDecision | None = None) -> bool:
        # An explicit human approval is a planning overlay for this exact topic.
        # It does not rewrite the legacy TopicReference stored in source data.
        if decision and decision.is_approval and (not decision.topic_id or decision.topic_id == topic):
            return True
        for link in record.topics:
            if link.topic_id == topic and (link.status == "approved" or request.review_policy == REVIEW_LEGACY and link.status == "legacy_unreviewed"):
                return True
            if request.allow_related_topics and link.topic_id in related and link.status == "approved":
                return True
        return False

    def _allocate(self, request: PlanRequest, records: list[ContentRecord]) -> list[PuzzleAllocation]:
        groups: dict[str, list[ContentRecord]] = {}
        for record in records:
            mini_theme = str(record.payload.get("mini_theme") or "")
            groups.setdefault(mini_theme, []).append(record)
        rng = random.Random(request.seed ^ 0x534C4144)
        for values in groups.values():
            rng.shuffle(values)
        if set(groups) == {""}:
            mixed = list(groups[""])
            return [PuzzleAllocation(index + 1, tuple(record.id for record in mixed[index * request.items_per_puzzle:(index + 1) * request.items_per_puzzle]))
                    for index in range(request.puzzle_count)]
        ordered_groups = sorted(groups)
        rng.shuffle(ordered_groups)
        per_group = {name: list(values) for name, values in groups.items()}
        allocations: list[PuzzleAllocation] = []
        for number in range(1, request.puzzle_count + 1):
            # A page carrying a mini-theme name must contain words from that
            # mini-theme. The former round-robin-by-word strategy mixed many
            # categories and then attached a misleading majority label.
            choices = [name for name in ordered_groups
                       if len(per_group[name]) >= request.items_per_puzzle]
            theme = choices[(number - 1) % len(choices)] if choices else ""
            if theme:
                bucket = [per_group[theme].pop() for _ in range(request.items_per_puzzle)]
            else:
                # Sparse leftovers can still form an honest general-topic page,
                # but it receives no false mini-theme label.
                remainder = [item for name in ordered_groups for item in per_group[name]]
                rng.shuffle(remainder)
                if len(remainder) < request.items_per_puzzle:
                    raise ValueError("Eligible pool changed during deterministic allocation.")
                bucket = remainder[:request.items_per_puzzle]
                used = {item.id for item in bucket}
                for name in ordered_groups:
                    per_group[name] = [item for item in per_group[name] if item.id not in used]
            rng.shuffle(bucket)
            allocations.append(PuzzleAllocation(number, tuple(record.id for record in bucket), theme))
        return allocations

    def _sudoku_plan(self, request: PlanRequest) -> PlanResult:
        if request.symbol_set not in {"numbers", "letters", "shapes"} or request.grid_size != 9:
            return PlanResult(None, "unsupported_format", ["Sudoku supports 9×9 number, letter, or shape plans only."])
        proof = self._capacity_proof(request, [])
        plan_id = _digest({"source_revision": self.engine.source_revision, "request": asdict(request), "capacity_proof": proof})[:24]
        plan = BookPlan(plan_id, datetime.now(timezone.utc).isoformat(timespec="seconds"), "sudoku", [request.topic_id],
                        self._format(request), request.seed, request.review_policy, request.freshness_policy,
                        self.engine.source_revision, proof, [], [],
                        {"difficulty_distribution": {request.difficulty: request.puzzle_count}, "symbol_set": request.symbol_set,
                         "grid_size": request.grid_size, "unique_solution_required": True, "determinism": "seed passed to existing generator"},
                        ["Sudoku grids are generated and uniqueness-validated by the existing specialized generator."])
        return PlanResult(plan, "valid", warnings=plan.warnings, capacity={"required_count": request.puzzle_count, "verified_capacity": request.puzzle_count, "capacity_proof": proof})

    def _mixed_plan(self, request: PlanRequest) -> PlanResult:
        from publishing.non_word_catalog import deterministic_mixed_allocation
        allocation = deterministic_mixed_allocation(request.puzzle_count, "balanced")
        # The current production engine supports three non-Word-Search mixed
        # sections. Word Search allocation is retained as zero until the shared
        # orchestrator can consume it without creating a competing route.
        carry = allocation.pop("word_search")
        # Redistribute the reserved Word Search share evenly across the three
        # sections the current Mixed renderer actually supports. This keeps
        # legacy small plans viable and avoids pretending Word Search is in the
        # rendered book before that route is implemented end to end.
        supported = ("sudoku", "cryptogram", "scramble_trivia")
        for index in range(carry):
            allocation[supported[index % len(supported)]] += 1
        sections = {"sudoku": PlanRequest(request.topic_id, "sudoku", allocation["sudoku"], 1, request.seed, request.difficulty, request.large_print, request.review_policy, request.freshness_policy, request.series_scope, request.allow_related_topics, request.general_pool, request.symbol_set, request.grid_size),
                    "cryptogram": PlanRequest(request.topic_id, "cryptogram", allocation["cryptogram"], 1, request.seed + 1009, request.difficulty, request.large_print, request.review_policy, request.freshness_policy, request.series_scope, request.allow_related_topics, request.general_pool),
                    "scramble_trivia": PlanRequest(request.topic_id, "scramble_trivia", allocation["scramble_trivia"], 1, request.seed + 2017, request.difficulty, request.large_print, request.review_policy, request.freshness_policy, request.series_scope, request.allow_related_topics, request.general_pool)}
        results = {name: self.create(section) for name, section in sections.items()}
        blocked = {name: result for name, result in results.items() if result.plan is None}
        if blocked:
            return PlanResult(None, "blocked_section", [f"{name}: {'; '.join(result.blockers)}" for name, result in blocked.items()],
                              ["Themed Mixed plans never substitute a general pool for an insufficient themed section."])
        proof = self._capacity_proof(request, [])
        children = {name: result.plan for name, result in results.items() if result.plan}
        plan_id = _digest({"source_revision": self.engine.source_revision, "request": asdict(request), "sections": {name: plan.book_plan_id for name, plan in children.items()}})[:24]
        mixed_format = self._format(request)
        mixed_format["section_allocation"] = dict(allocation)
        mixed_format["allocation_profile"] = "balanced"
        plan = BookPlan(plan_id, datetime.now(timezone.utc).isoformat(timespec="seconds"), "mixed", [request.topic_id], mixed_format,
                        request.seed, request.review_policy, request.freshness_policy, self.engine.source_revision, proof,
                        [], [], {"section_count": len(children), "general_pool_explicit": request.general_pool},
                        ["Mixed plan is a section contract; existing routing is unchanged."], section_plans=children)
        return PlanResult(plan, "valid", warnings=plan.warnings)

    def _canonical_topic(self, request: PlanRequest) -> str:
        return self.engine.taxonomy.resolve(request.topic_id) or request.topic_id

    @staticmethod
    def _format(request: PlanRequest) -> dict[str, object]:
        return {"puzzle_count": request.puzzle_count, "items_per_puzzle": request.items_per_puzzle,
                "difficulty": request.difficulty, "large_print": request.large_print,
                "symbol_set": request.symbol_set, "grid_size": request.grid_size}

    def _capacity_proof(self, request: PlanRequest, candidates: Iterable[ContentRecord]) -> str:
        return _digest({"source_revision": self.engine.source_revision, "request": asdict(request),
                        "eligible_content_ids": [item.id for item in candidates]})

    def validate(self, plan: BookPlan) -> PlanValidation:
        if plan.schema_version != PLAN_SCHEMA_VERSION:
            return PlanValidation("invalid", ("Unsupported Book Plan schema.",))
        if plan.source_revision != self.engine.source_revision:
            return PlanValidation("stale", ("Source revision changed since this plan was created.",))
        request = PlanRequest(plan.topic_ids[0] if plan.topic_ids else "", plan.puzzle_type,
                              int(plan.format.get("puzzle_count") or 0), int(plan.format.get("items_per_puzzle") or 1),
                              plan.seed, str(plan.format.get("difficulty") or "standard"), bool(plan.format.get("large_print")),
                              plan.review_policy, plan.freshness_policy,
                              symbol_set=str(plan.format.get("symbol_set") or "numbers"), grid_size=int(plan.format.get("grid_size") or 9))
        if plan.puzzle_type == "mixed":
            for section in plan.section_plans.values():
                outcome = self.validate(section)
                if outcome.status != "valid": return PlanValidation(outcome.status, ("A mixed section is " + outcome.status + ".", *outcome.reasons))
            return PlanValidation("valid")
        if plan.puzzle_type == "sudoku": return PlanValidation("valid")
        candidates, _, _ = self._eligible_records(request)
        proof = self._capacity_proof(request, candidates)
        if proof != plan.capacity_proof:
            return PlanValidation("invalid", ("Capacity proof changed; eligible content or policy no longer matches.",))
        ids = [item.id for item in candidates]
        missing = [item for item in plan.selected_content_ids if item not in ids]
        if missing: return PlanValidation("invalid", (f"{len(missing)} selected content IDs are no longer eligible.",))
        expected = request.required_count
        if len(plan.selected_content_ids) != expected or len(set(plan.selected_content_ids)) != expected:
            return PlanValidation("invalid", ("Selected content count does not match the requested format.",))
        if len(plan.puzzle_allocations) != request.puzzle_count or any(len(row.content_ids) != request.items_per_puzzle for row in plan.puzzle_allocations):
            return PlanValidation("invalid", ("Puzzle allocations do not match the requested format.",))
        return PlanValidation("valid")

    def word_search_placement_precheck(self, plan: BookPlan) -> PlanValidation:
        """Sample the existing grid placer deterministically without producing files.

        This is deliberately an optional planning-time guard, not a replacement
        for the generator's full validation.  Its random state is restored so
        it cannot affect an existing generation path.
        """
        if plan.puzzle_type != "word_search":
            return PlanValidation("invalid", ("Placement precheck applies only to Word Search plans.",))
        import random as global_random
        from wordsearch import generate_puzzle, grid_size_for
        state = global_random.getstate()
        try:
            for allocation in plan.puzzle_allocations:
                words = [self.engine.registry.get(content_id) for content_id in allocation.content_ids]
                if any(word is None for word in words):
                    return PlanValidation("invalid", (f"Puzzle {allocation.puzzle_number} references missing content.",))
                display = [word.normalized for word in words if word]
                global_random.seed(plan.seed + allocation.puzzle_number)
                _grid, _placements, placed = generate_puzzle(display, grid_size_for(display))
                if len(placed) != len(display):
                    return PlanValidation("invalid", (f"Puzzle {allocation.puzzle_number} failed placement precheck.",))
        finally:
            global_random.setstate(state)
        return PlanValidation("valid")


def save_plan(path: Path | str, plan: BookPlan) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(plan.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target


def load_plan(path: Path | str) -> BookPlan:
    return BookPlan.from_dict(json.loads(Path(path).read_text(encoding="utf-8-sig")))
