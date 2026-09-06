"""Plain-English operator status for the Content Intelligence workflow.

This module is deliberately a read model.  It does not keep a second set of
readiness flags in Tkinter widgets: capacity, plans, proofs, human reviews,
release locks, and marketplace history remain the respective sources of truth.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Iterable

from word_intelligence.book_planning import BookPlan, BookPlanner, PlanRequest, load_plan, save_plan
from word_intelligence.capacity import CapacityRequest, REVIEW_LEGACY, REVIEW_STRICT
from word_intelligence.qualification import ApprovalDecision, load_approval_input


@dataclass(frozen=True)
class OperatorStatus:
    book_id: str = ""
    package_id: str = ""
    headline_status: str = "ready_to_plan"
    stage: str = "feasibility"
    message: str = "Content is ready to plan."
    next_action: str = "build_safe_plan"
    attention_count: int = 0
    details: tuple[str, ...] = ()
    verification_mode: str = REVIEW_STRICT

    @property
    def label(self) -> str:
        return {
            "blocked": "Blocked",
            "needs_review": "Needs Review",
            "stale": "Out of Date",
            "ready_to_plan": "Ready to Plan",
            "plan_ready": "Plan Ready",
            "ready_for_final_local_review": "Ready for Final Local Review",
            "ready_for_platform_preview": "Ready for Platform Preview",
            "uploaded": "Uploaded",
            "published": "Published",
            "legacy": "Legacy Package — Modern Proof Not Available",
        }.get(self.headline_status, self.headline_status.replace("_", " ").title())

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["label"] = self.label
        data["details"] = list(self.details)
        return data


@dataclass(frozen=True)
class Feasibility:
    request: PlanRequest
    status: OperatorStatus
    verified_content: int
    required_content: int
    margin: int
    breakdown: dict[str, int] = field(default_factory=dict)
    alternatives: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def display_lines(self) -> list[str]:
        mode = "Verified Content" if self.request.review_policy == REVIEW_STRICT else "Legacy-Compatible Content"
        lines = [f"{self.request.topic_id}", "", f"Requested: {self.request.puzzle_count} puzzles × {self.request.items_per_puzzle} items", mode + f": {self.verified_content}", f"Required: {self.required_content}", f"Capacity margin: {self.margin}"]
        if self.breakdown:
            readable = {"raw_candidates": "source candidates", "canonical_records": "unique records", "topic_linked": "topic-matched", "format_valid": "format-valid", "reviewed": "reviewed and eligible"}
            lines += ["", "Content breakdown:"]
            for key in ("raw_candidates", "canonical_records", "topic_linked", "format_valid", "reviewed"):
                if key in self.breakdown:
                    lines.append(f"• {self.breakdown[key]} {readable[key]}")
        if self.alternatives:
            lines += ["", "Other honest options:", *[f"• {item}" for item in self.alternatives]]
        if self.warnings:
            lines += ["", *[f"Note: {item}" for item in self.warnings]]
        return lines


class OperatorStatusService:
    """One shared, non-generating service for Phase 5 UI surfaces."""

    def __init__(self, project: Path | str, database=None) -> None:
        self.project = Path(project)
        self.database = database

    @property
    def plan_directory(self) -> Path:
        return self.project / "plans" / "operator"

    @property
    def approval_path(self) -> Path:
        return self.project / "data" / "content_approval_decisions.json"

    def _planner(self) -> BookPlanner:
        return BookPlanner.from_project(self.project, self.approval_path if self.approval_path.is_file() else None)

    def feasibility(self, request: PlanRequest) -> Feasibility:
        planner = self._planner()
        capacity = planner.engine.evaluate(CapacityRequest(
            request.topic_id, request.puzzle_type, request.puzzle_count, request.items_per_puzzle,
            review_policy=request.review_policy, freshness_policy=request.freshness_policy,
            series_scope=request.series_scope, allow_related_topics=request.allow_related_topics,
        ))
        # Phase 3's explicit approval overlay is intentionally not written
        # into source records.  Count it through the planner here so a human
        # decision made in the review workflow is visible immediately.
        if request.puzzle_type in {"word_search", "cryptogram", "scramble_trivia"}:
            eligible, exclusions, planner_warnings = planner._eligible_records(request)
            verified = len(eligible)
        else:
            exclusions, planner_warnings = {}, []
            verified = int(capacity.verified_capacity)
        needed = int(capacity.required_count)
        # ``verified`` includes individually approved generated candidates,
        # which are deliberately an additive overlay rather than a source-bank
        # rewrite. Capacity's raw snapshot predates that overlay.
        if verified >= needed:
            message, headline, action = "Enough reviewed content is available. You can build a safe Book Plan.", "ready_to_plan", "build_safe_plan"
        elif request.review_policy == REVIEW_STRICT:
            missing = max(0, needed - verified)
            message, headline, action = f"Not enough reviewed content yet — {missing} more approved items are needed for this exact format.", "blocked", "review_content"
        else:
            message, headline, action = "Not enough eligible legacy-compatible content is available for this exact format.", "blocked", "review_content"
        if request.review_policy == REVIEW_LEGACY:
            message += " This mode requires a clear acknowledgement before local release readiness."
        breakdown = {
            "raw_candidates": int(capacity.raw_candidate_count), "canonical_records": int(capacity.canonical_record_count),
            "topic_linked": int(capacity.topic_linked_count), "format_valid": int(capacity.format_valid_count),
            "reviewed": verified,
        }
        status = OperatorStatus(headline_status=headline, stage="feasibility", message=message,
                                next_action=action, attention_count=0 if headline == "ready_to_plan" else 1,
                                details=tuple(capacity.blockers + capacity.warnings + planner_warnings), verification_mode=request.review_policy)
        return Feasibility(request, status, verified, needed, verified - needed, breakdown,
                           tuple(capacity.alternatives), tuple(capacity.warnings + planner_warnings))

    def build_safe_plan(self, request: PlanRequest) -> tuple[BookPlan | None, OperatorStatus, Path | None]:
        feasibility = self.feasibility(request)
        if feasibility.status.headline_status != "ready_to_plan":
            return None, feasibility.status, None
        result = self._planner().create(request)
        if not result.plan:
            return None, OperatorStatus(headline_status="blocked", stage="planning", message="The plan could not be built: " + "; ".join(result.blockers), next_action="review_content", attention_count=1, details=tuple(result.warnings), verification_mode=request.review_policy), None
        path = self.plan_directory / f"{result.plan.book_plan_id}.json"
        save_plan(path, result.plan)
        return result.plan, OperatorStatus(headline_status="plan_ready", stage="planning", message="Book Plan is ready and saved locally. Generate only after you review this plan.", next_action="generate_book", details=tuple(result.warnings), verification_mode=result.plan.review_policy), path

    def plan_status(self, plan: BookPlan | Path | str) -> OperatorStatus:
        active = load_plan(plan) if not isinstance(plan, BookPlan) else plan
        # Sudoku's content is algorithmic.  Its plan validity is format based
        # and does not require loading a word-library project merely to answer
        # this operator question.
        if active.puzzle_type == "sudoku":
            valid = active.format.get("grid_size", 9) == 9 and active.format.get("symbol_set", "numbers") in {"numbers", "letters", "shapes"}
            if valid:
                return OperatorStatus(headline_status="plan_ready", stage="planning", message="This Sudoku Book Plan is current.", next_action="generate_book", verification_mode=active.review_policy)
        validation = self._planner().validate(active)
        if validation.status == "valid":
            return OperatorStatus(headline_status="plan_ready", stage="planning", message="This Book Plan is current.", next_action="generate_book", verification_mode=active.review_policy)
        if validation.status == "stale":
            return OperatorStatus(headline_status="stale", stage="planning", message="This plan is out of date because the content library changed. Build an updated plan before production.", next_action="build_updated_plan", attention_count=1, details=validation.reasons, verification_mode=active.review_policy)
        return OperatorStatus(headline_status="blocked", stage="planning", message="This plan can no longer be used for production.", next_action="recheck_capacity", attention_count=1, details=validation.reasons, verification_mode=active.review_policy)

    def product_status(self, book: dict, *, plan: BookPlan | None = None, proof: dict | None = None) -> OperatorStatus:
        """Summarize a catalog product without changing its state."""
        statuses = book.get("statuses") or {}
        if any(value == "Published" for value in statuses.values()):
            return OperatorStatus(book_id=book.get("book_id", ""), headline_status="published", stage="marketplace", message="This book has a recorded Published marketplace status.", next_action="open_marketplace_handoff")
        if any(value == "Uploaded" for value in statuses.values()):
            return OperatorStatus(book_id=book.get("book_id", ""), headline_status="uploaded", stage="marketplace", message="This book has a recorded Uploaded marketplace status. Its history is protected.", next_action="open_marketplace_handoff")
        if not plan:
            return OperatorStatus(book_id=book.get("book_id", ""), headline_status="legacy", stage="legacy", message="This existing package has no modern Book Plan. It remains unchanged; review it or create a new revision when you choose.", next_action="review_existing_package")
        plan_state = self.plan_status(plan)
        if plan_state.headline_status != "plan_ready":
            return OperatorStatus(book_id=book.get("book_id", ""), package_id=plan_state.package_id,
                                  headline_status=plan_state.headline_status, stage=plan_state.stage,
                                  message=plan_state.message, next_action=plan_state.next_action,
                                  attention_count=plan_state.attention_count, details=plan_state.details,
                                  verification_mode=plan_state.verification_mode)
        if not proof:
            return OperatorStatus(book_id=book.get("book_id", ""), headline_status="plan_ready", stage="generation", message="The Book Plan is current. Generate the package, then run the Production Check.", next_action="generate_book", verification_mode=plan.review_policy)
        proof_status = str(proof.get("status") or "")
        proof_id, package = str(proof.get("proof_id") or ""), str(book.get("package_path") or "")
        if proof_status == "blocked":
            return OperatorStatus(book_id=book.get("book_id", ""), package_id=str(proof.get("package_id") or ""), headline_status="blocked", stage="production_proof", message="Production Check found an issue that must be fixed before release review.", next_action="review_production_proof", attention_count=len(proof.get("attention_required") or [1]), details=tuple(item.get("message", "") for item in proof.get("attention_required") or []), verification_mode=plan.review_policy)
        package_root = Path(package)
        if package_root.is_dir():
            from .package_layout import package_file
            from background_generation.index import verify_rendered_cover_approval
            cover_ok, cover_reason, _cover_proof = verify_rendered_cover_approval(package_file(package_root, "front_cover.png"))
            if not cover_ok:
                return OperatorStatus(book_id=book.get("book_id", ""), headline_status="blocked", stage="cover",
                                      message="Cover Art Required — this package cannot reach Platform Preview.",
                                      next_action="choose_approved_asset", attention_count=1,
                                      details=(cover_reason,), verification_mode=plan.review_policy)
        review = self.database.final_local_review(book.get("book_id", ""), proof_id, package) if self.database else None
        if proof_status == "needs_review" or not review:
            return OperatorStatus(book_id=book.get("book_id", ""), package_id=str(proof.get("package_id") or ""), headline_status="ready_for_final_local_review", stage="final_review", message="The automated checks passed enough to begin your Final Local Review.", next_action="complete_final_local_review", attention_count=0 if review else 1, verification_mode=plan.review_policy)
        locks = self.database.release_locks(book.get("book_id", "")) if self.database else []
        return OperatorStatus(book_id=book.get("book_id", ""), package_id=str(proof.get("package_id") or ""), headline_status="ready_for_platform_preview", stage="release", message="Final Local Review is recorded. This package is ready for platform preview; it is not published automatically.", next_action="open_marketplace_handoff", details=(f"Local release proof: {len(locks)} saved revision(s).",), verification_mode=plan.review_policy)

    def attention(self, books: Iterable[dict]) -> list[OperatorStatus]:
        """Read-only dashboard list, ordered blockers then review then legacy."""
        items = [self.product_status(book) for book in books]
        order = {"blocked": 0, "needs_review": 1, "stale": 2, "ready_for_final_local_review": 3, "plan_ready": 4, "ready_to_plan": 5, "legacy": 6, "uploaded": 7, "published": 8}
        return sorted(items, key=lambda item: (order.get(item.headline_status, 9), item.message.casefold()))

    def record_review_decisions(self, topic_id: str, decisions: Iterable[tuple[str, str]]) -> int:
        """Persist selected human review decisions as an approval overlay.

        This intentionally accepts only individual selected records.  It does
        not alter the source bank, bypass qualification, or offer an
        auto-approval path for an entire legacy library.
        """
        current = load_approval_input(self.approval_path)
        prior = {key: value.decision for key, value in current.items()}
        changed = 0
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for content_id, decision in decisions:
            if decision not in {"approved", "rejected", "needs_review"}:
                continue
            current[str(content_id)] = ApprovalDecision(str(content_id), str(topic_id), decision, now, "human")
            changed += 1
        self.approval_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema_version": 1, "decisions": [asdict(row) for row in sorted(current.values(), key=lambda item: item.content_id)]}
        self.approval_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        audit_path = self.project / "data" / "editorial_review_audit.jsonl"
        with audit_path.open("a", encoding="utf-8") as audit:
            for content_id, decision in decisions:
                if decision in {"approved", "rejected", "needs_review"}:
                    audit.write(json.dumps({"content_id": str(content_id), "topic_id": str(topic_id), "prior_state": prior.get(str(content_id), "unreviewed"), "new_state": decision, "reviewed_at": now, "review_source": "human"}, ensure_ascii=False) + "\n")
        return changed
