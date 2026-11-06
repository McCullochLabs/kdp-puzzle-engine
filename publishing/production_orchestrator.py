"""One dependency-aware local production job over the existing studio systems.

This module does not generate puzzles, covers, listings, or marketplace files.
It coordinates those existing capabilities, records one understandable state,
and identifies the next safe action without crossing a human review gate.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Callable

SCHEMA_VERSION = 1
STAGES = (
    "idea", "feasibility", "content_plan", "generation", "cover",
    "product_qa", "listing", "package", "final_review", "platform_preview",
    "marketplace_handoff",
)
DEPENDENCIES = {
    "idea": (),
    "feasibility": ("idea",),
    "content_plan": ("feasibility",),
    "generation": ("content_plan",),
    "cover": ("content_plan",),
    "product_qa": ("generation", "cover"),
    "listing": ("content_plan", "product_qa"),
    "package": ("generation", "cover", "product_qa", "listing"),
    "final_review": ("package",),
    "platform_preview": ("final_review",),
    "marketplace_handoff": ("platform_preview",),
}
HUMAN_GATES = {"content_plan", "final_review", "marketplace_handoff"}
COMPLETED = {"complete", "passed", "approved", "ready"}
LABELS = {
    "idea": "Book Idea", "feasibility": "Check Feasibility",
    "content_plan": "Review Book Plan", "generation": "Create Interior",
    "cover": "Create / Review Cover", "product_qa": "Run Product QA",
    "listing": "Review Listing", "package": "Prepare Package",
    "final_review": "Complete Final Local Review",
    "platform_preview": "Open Platform Preview", "marketplace_handoff": "Prepare Marketplace Handoff",
}


def plan_review_summary(context: dict) -> str:
    """Plain-English facts an operator must see before approving a plan."""
    puzzle_type = str(context.get("puzzle_type") or "Puzzle book").replace("_", " ").title()
    count = context.get("puzzle_count") or "Not recorded"
    items = context.get("items_per_puzzle") or "Automatic"
    return "\n".join((
        f"Title: {context.get('title') or 'Untitled'}",
        f"Topic: {context.get('topic') or context.get('detected_topic') or 'Not recorded'}",
        f"Puzzle type: {puzzle_type}",
        f"Puzzles: {count}",
        f"Words/items per puzzle: {items}",
        f"Difficulty: {str(context.get('difficulty') or 'Automatic').title()}",
        f"Edition: {'Signature Edition' if context.get('signature_edition') else 'Standard Edition'}",
    ))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")).hexdigest()


def _atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.stem}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, ensure_ascii=False); stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def component_fingerprints(context: dict) -> dict[str, str]:
    """Hash only inputs that can change a particular production component."""
    content = {key: context.get(key) for key in (
        "book_plan_id", "source_revision", "capacity_proof", "puzzle_type",
        "puzzle_count", "items_per_puzzle", "difficulty", "seed",
        "repetition_policy", "collection_id", "collection_book_id", "interior_profile",
        "reader_profile",
    )}
    from .puzzle_integrity import POLICY_REVISION
    content['puzzle_quality_policy'] = POLICY_REVISION
    cover = {key: context.get(key) for key in (
        "title", "subtitle", "author", "puzzle_type", "puzzle_count",
        "difficulty", "large_print", "cover_art_id", "cover_art_sha256",
        "cover_style", "palette",
    )}
    cover['puzzle_preview_policy'] = POLICY_REVISION
    listing = {key: context.get(key) for key in (
        "title", "subtitle", "author", "topic", "audience", "series",
        "puzzle_type", "puzzle_count", "difficulty", "large_print",
        "signature_edition", "no_repeat_words", "page_count", "trim_size", "repetition_policy",
    )}
    return {
        "idea": _digest({key: context.get(key) for key in ("book_id", "title", "topic", "puzzle_type")}),
        "feasibility": _digest(content),
        "content_plan": _digest(content),
        "generation": _digest(content),
        "cover": _digest(cover),
        "product_qa": _digest({"content": content, "cover": cover}),
        "listing": _digest(listing),
        "package": _digest({"content": content, "cover": cover, "listing": listing}),
        "final_review": _digest({"content": content, "cover": cover, "listing": listing}),
        "platform_preview": _digest({"content": content, "cover": cover, "listing": listing}),
        "marketplace_handoff": _digest({"content": content, "cover": cover, "listing": listing}),
    }


@dataclass(frozen=True)
class ProductionState:
    production_job_id: str
    book_id: str
    puzzle_type: str
    status: str
    current_stage: str
    next_action: str
    attention: tuple[str, ...] = ()
    resumable: bool = True

    def to_dict(self) -> dict:
        value = asdict(self); value["attention"] = list(self.attention)
        value["attention_bucket"] = {
            "feasibility": "Content Review Needed",
            "content_plan": "Ready to Plan",
            "generation": "Generation Problem" if self.status in {"blocked", "needs_review"} else "Interior Generation Needed",
            "cover": "Cover Review Needed" if self.status == "needs_review" else "Cover Needed",
            "product_qa": "QA Review Needed",
            "listing": "Listing Review Needed",
            "final_review": "Final Local Review",
            "platform_preview": "Ready for Platform Preview",
            "marketplace_handoff": "Marketplace Handoff",
        }.get(self.current_stage, "Book Idea")
        return value


class ProductionOrchestrator:
    """Persistent coordinator for one book; specialized engines remain callers."""

    def __init__(self, project: Path | str, book_id: str) -> None:
        self.project, self.book_id = Path(project), str(book_id)
        self.production_job_id = "job_" + _digest(self.book_id)[:20]
        self.path = self.project / "data" / "production_jobs" / f"{self.production_job_id}.json"

    def load(self) -> dict:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8-sig"))
            if isinstance(value, dict):
                return value
        except (OSError, json.JSONDecodeError):
            pass
        return {"schema_version": SCHEMA_VERSION, "production_job_id": self.production_job_id,
                "book_id": self.book_id, "book_plan_id": "", "puzzle_type": "",
                "status": "idea", "context": {}, "fingerprints": {}, "steps": {},
                "events": [], "created_at": _now(), "updated_at": _now()}

    def save(self, record: dict) -> dict:
        record["updated_at"] = _now(); _atomic_write(self.path, record); return record

    def start(self, context: dict) -> dict:
        record = self.load(); previous = dict(record.get("fingerprints") or {})
        current = component_fingerprints(context)
        record.update({"book_plan_id": str(context.get("book_plan_id") or record.get("book_plan_id") or ""),
                       "puzzle_type": str(context.get("puzzle_type") or record.get("puzzle_type") or ""),
                       "context": dict(context), "fingerprints": current, "paused": False})
        if previous:
            for stage in STAGES:
                if previous.get(stage) and previous.get(stage) != current.get(stage):
                    self._stale_stage(record, stage, "Inputs changed after this stage was completed.")
        # Real production artifacts use absolute paths. If one disappears
        # between sessions, resume at that exact stage rather than trusting a
        # stale checkpoint or regenerating unrelated upstream work.
        for stage in ("generation", "cover", "product_qa", "listing", "package"):
            step = record.get("steps", {}).get(stage) or {}
            artifact = Path(str(step.get("artifact") or ""))
            if step.get("status") in COMPLETED and artifact.is_absolute() and not artifact.exists():
                self._stale_stage(record, stage, "The recorded stage artifact is missing and must be repaired.")
        record.setdefault("events", []).append({"at": _now(), "event": "started_or_resumed"})
        record["events"] = record["events"][-200:]
        self._refresh_status(record)
        return self.save(record)

    @staticmethod
    def _dependents(stage: str) -> set[str]:
        found: set[str] = set()
        changed = True
        while changed:
            changed = False
            for candidate, needs in DEPENDENCIES.items():
                if candidate not in found and (stage in needs or any(item in found for item in needs)):
                    found.add(candidate); changed = True
        return found

    def _stale_stage(self, record: dict, stage: str, reason: str) -> None:
        for item in {stage, *self._dependents(stage)}:
            step = record.setdefault("steps", {}).get(item)
            if step and step.get("status") in COMPLETED:
                step.update({"status": "stale", "stale_at": _now(), "stale_reason": reason})

    def complete(self, stage: str, *, artifact: str = "", detail: str = "", approved: bool = False,
                 human_evidence: dict | None = None) -> dict:
        if stage not in STAGES:
            raise ValueError(f"Unknown production stage: {stage}")
        record = self.load(); expected = set(DEPENDENCIES[stage])
        incomplete = [item for item in expected if (record.get("steps", {}).get(item) or {}).get("status") not in COMPLETED]
        if incomplete:
            raise ValueError("Complete prerequisite stage(s) first: " + ", ".join(incomplete))
        if stage in HUMAN_GATES:
            if not approved:
                raise ValueError(f"{LABELS[stage]} is a human checkpoint and cannot be completed automatically.")
            evidence = dict(human_evidence or {})
            if not str(evidence.get("source") or "").strip() or not str(evidence.get("evidence_id") or "").strip():
                raise ValueError(f"{LABELS[stage]} requires persisted human-review evidence.")
        else:
            evidence = {}
        status = "approved" if approved else "complete"
        record.setdefault("steps", {})[stage] = {"status": status, "fingerprint": (record.get("fingerprints") or {}).get(stage, ""), "completed_at": _now(), "artifact": artifact, "detail": detail, **({"human_evidence": evidence} if evidence else {})}
        record.setdefault("events", []).append({"at": _now(), "event": "stage_complete", "stage": stage, "status": status})
        self._refresh_status(record); return self.save(record)

    def fail(self, stage: str, reason: str, *, human_review: bool = False,
             error_type: str = "stage_error", retryable: bool = True) -> dict:
        record = self.load(); record.setdefault("steps", {})[stage] = {
            "status": "needs_review" if human_review else "blocked", "failed_at": _now(),
            "detail": str(reason), "error_type": str(error_type), "retryable": bool(retryable),
            "affected_stages": sorted(self._dependents(stage))}
        record.setdefault("events", []).append({"at": _now(), "event": "stage_failed", "stage": stage,
                                                 "reason": str(reason), "error_type": str(error_type),
                                                 "retryable": bool(retryable)})
        self._refresh_status(record); return self.save(record)

    def approve_human_stage(self, stage: str, *, source: str, evidence_id: str,
                            artifact: str = "", detail: str = "") -> dict:
        """Adopt a persisted human decision; never manufactures one."""
        if stage not in HUMAN_GATES:
            raise ValueError(f"{LABELS.get(stage, stage)} is not a human checkpoint.")
        return self.complete(stage, artifact=artifact, detail=detail, approved=True,
                             human_evidence={"source": source, "evidence_id": evidence_id})

    def stop(self, stage: str | None = None, detail: str = "Stopped safely by the operator.") -> dict:
        """Pause without deleting artifacts or converting valid work to failure."""
        record = self.load(); active = stage or str(record.get("current_stage") or self.state().current_stage)
        record["paused"] = True; record["status"] = "stopped"; record["current_stage"] = active
        record["next_action"] = "Continue Production"; record["attention"] = [detail]
        record.setdefault("events", []).append({"at": _now(), "event": "stopped", "stage": active, "detail": detail})
        return self.save(record)

    def retry(self, stage: str, action: Callable[[], object]) -> dict:
        """Retry one failed/stale stage only; completed prerequisites remain intact."""
        record = self.load(); step = record.get("steps", {}).get(stage) or {}
        if step.get("status") not in {"blocked", "needs_review", "stale"}:
            return {"status": "not_retryable", "stage": stage, "reason": "This stage is not failed or stale."}
        if step.get("retryable") is False:
            return {"status": "human_review_required", "stage": stage, "reason": step.get("detail", "")}
        try:
            value = action(); artifact = str(value.get("artifact") or "") if isinstance(value, dict) else ""
            detail = str(value.get("detail") or "") if isinstance(value, dict) else str(value or "")
            self.complete(stage, artifact=artifact, detail=detail)
            return {"status": "complete", "stage": stage, "next": self.state().to_dict()}
        except Exception as exc:
            self.fail(stage, str(exc), error_type=type(exc).__name__)
            return {"status": "blocked", "stage": stage, "reason": str(exc)}

    def invalidate(self, stage: str, reason: str) -> dict:
        record = self.load(); self._stale_stage(record, stage, reason); self._refresh_status(record); return self.save(record)

    def state(self) -> ProductionState:
        record = self.load(); self._refresh_status(record)
        return ProductionState(record["production_job_id"], record["book_id"], str(record.get("puzzle_type") or ""),
                               str(record.get("status") or "idea"), str(record.get("current_stage") or "idea"),
                               str(record.get("next_action") or LABELS["idea"]), tuple(record.get("attention") or ()))

    def _refresh_status(self, record: dict) -> None:
        if record.get("paused"):
            record.update({"status": "stopped", "next_action": "Continue Production"})
            return
        steps = record.get("steps") or {}; attention = []
        for stage in STAGES:
            step = steps.get(stage) or {}; state = step.get("status")
            if state in {"blocked", "needs_review", "stale"}:
                message = str(step.get("detail") or step.get("stale_reason") or f"{LABELS[stage]} needs attention.")
                record.update({"status": state, "current_stage": stage, "next_action": LABELS[stage], "attention": [message]}); return
            if state not in {"complete", "passed", "approved", "ready"}:
                record.update({"status": "waiting_for_review" if stage in HUMAN_GATES else "ready",
                               "current_stage": stage, "next_action": LABELS[stage], "attention": attention}); return
        record.update({"status": "complete", "current_stage": "marketplace_handoff",
                       "next_action": "No production action is waiting", "attention": []})

    def continue_production(self, actions: dict[str, Callable[[], object]]) -> dict:
        """Run only the next supplied safe action; never cross a human gate."""
        record = self.load()
        if record.get("paused"):
            record["paused"] = False; self._refresh_status(record); self.save(record)
        state = self.state(); stage = state.current_stage
        if stage in HUMAN_GATES:
            return {"status": "human_review_required", "stage": stage, "next_action": state.next_action}
        action = actions.get(stage)
        if not action:
            return {"status": "action_required", "stage": stage, "next_action": state.next_action}
        try:
            result = action()
            artifact = str(result.get("artifact") or "") if isinstance(result, dict) else ""
            detail = str(result.get("detail") or "") if isinstance(result, dict) else str(result or "")
            self.complete(stage, artifact=artifact, detail=detail)
            return {"status": "complete", "stage": stage, "result": result, "next": self.state().to_dict()}
        except Exception as exc:
            self.fail(stage, str(exc), error_type=type(exc).__name__)
            return {"status": "blocked", "stage": stage, "reason": str(exc)}


class ProductionJobIndex:
    """Fast read-only queue view over persisted canonical job records."""

    def __init__(self, project: Path | str) -> None:
        self.project = Path(project)
        self.directory = self.project / "data" / "production_jobs"

    def rows(self, *, status: str = "", puzzle_type: str = "", blocker: str = "",
             priority: str = "") -> list[dict]:
        records: list[dict] = []
        for path in self.directory.glob("job_*.json") if self.directory.is_dir() else ():
            try:
                row = json.loads(path.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(row, dict):
                continue
            state = ProductionOrchestrator(self.project, str(row.get("book_id") or "")).state().to_dict()
            context = row.get("context") or {}; attention = " ".join(state.get("attention") or [])
            item = {**state, "title": str(context.get("title") or row.get("book_id") or "Untitled"),
                    "priority": str(context.get("priority") or "normal"),
                    "updated_at": str(row.get("updated_at") or ""), "blocker": attention}
            if status and item["status"] != status: continue
            if puzzle_type and item["puzzle_type"] != puzzle_type: continue
            if blocker and blocker.casefold() not in attention.casefold(): continue
            if priority and item["priority"] != priority: continue
            records.append(item)
        priority_order = {"urgent": 0, "high": 1, "normal": 2, "low": 3}
        return sorted(records, key=lambda row: (priority_order.get(row["priority"], 2), row["updated_at"], row["title"].casefold()))
