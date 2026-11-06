"""Checkpointed local production coordination built on existing generators.

This is intentionally an orchestration record, not another puzzle or package
engine.  Callers supply existing generation stages; the coordinator records
their verified inputs, skips unchanged successful stages, bounds safe repairs,
and makes a human-review stop explicit when automation would be dishonest.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Callable

from .production_gate import book_gate
from .review import review_result

AUTOPILOT_VERSION = "1"
STAGES = ("validate", "plan", "generate", "cover", "preflight", "qa", "listing", "package", "handoffs", "register")
HUMAN_STOP_WORDS = ("author", "insufficient", "protected", "trademark", "no-repeat", "large-print", "rights", "theme mismatch")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _read(path: Path, fallback: dict) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        return value if isinstance(value, dict) else fallback
    except (OSError, json.JSONDecodeError):
        return fallback


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.stem}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, ensure_ascii=False); stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def canonical_facts(book: dict, source: dict | None = None) -> dict:
    """Build facts from catalog metadata and flag contradictions safely.

    Catalog metadata remains primary.  Source data fills only missing facts;
    any conflicting non-empty values are preserved as a human-review issue.
    """
    meta = dict(book.get("metadata") or {})
    source = source or {}
    aliases = {"pages": "page_count", "interior_pages": "page_count", "theme": "theme", "detected_topic": "topic", "puzzle_type": "puzzle_type", "puzzle_count": "puzzle_count", "author": "author", "title": "title", "subtitle": "subtitle", "series": "series"}
    facts = {"book_id": str(book.get("book_id") or ""), "source_key": str(book.get("source_key") or ""), "package_path": str(book.get("package_path") or "")}
    conflicts: list[str] = []
    for key in ("title", "subtitle", "author", "series", "theme", "detected_topic", "puzzle_type", "puzzle_count", "puzzle_seed", "page_count", "trim_size", "difficulty", "difficulty_label", "audience", "large_print", "signature_edition", "no_repeat_words", "answer_key", "files", "price", "description", "repetition_policy", "collection_id", "collection_book_id", "interior_profile"):
        value = meta.get(key)
        source_key = next((raw for raw, mapped in aliases.items() if mapped == key and source.get(raw) not in (None, "")), key)
        source_value = source.get(source_key)
        if value not in (None, "") and source_value not in (None, "") and str(value) != str(source_value):
            conflicts.append(f"Canonical {key.replace('_', ' ')} conflicts with its source record.")
        facts[key] = value if value not in (None, "") else source_value
    facts["brand"] = str(meta.get("imprint") or meta.get("brand") or source.get("brand") or "")
    facts["author"] = str(facts.get("author") or "")
    facts["metadata_locked"] = bool(book.get("metadata_locked"))
    facts["conflicts"] = conflicts
    facts["fingerprint"] = _hash({key: value for key, value in facts.items() if key not in {"conflicts", "fingerprint"}})
    return facts


def quality_score(book: dict, source: dict | None = None) -> dict:
    """Explainable local score, never a marketplace approval claim."""
    facts = canonical_facts(book, source)
    gate = book_gate(book)
    review = review_result(book, "amazon") if book.get("package_path") else {"ready": False, "blockers": ["Complete package has not been created yet."]}
    score, costs = 100, []
    if facts["conflicts"]: score -= 25; costs.extend(facts["conflicts"])
    if not gate.get("ready"): score -= min(40, 10 * len(gate.get("blockers") or [])); costs.extend(gate.get("blockers") or [])
    if not review.get("ready"): score -= min(30, 8 * len(review.get("blockers") or [])); costs.extend(review.get("blockers") or [])
    if not facts.get("package_path"): score -= 10; costs.append("Package files have not been created yet.")
    score = max(0, score)
    label = "Ready for Platform Preview" if score >= 90 and not costs else "Ready for Final Local Review" if score >= 75 else "Good Candidate" if score >= 55 else "Needs Work"
    return {"score": score, "label": label, "costs": list(dict.fromkeys(costs)), "facts": facts, "gate": gate, "review": review}


class ProductionAutopilot:
    """Small local checkpoint store with bounded, explicit safe repairs."""
    def __init__(self, project: Path, book_id: str) -> None:
        self.project, self.book_id = Path(project), str(book_id)
        self.path = self.project / "data" / "production_autopilot" / f"{self.book_id}.json"
        self._orchestrator = None

    def attach_orchestrator(self, context: dict) -> None:
        """Mirror this proven production route into the canonical job record."""
        from .production_orchestrator import ProductionOrchestrator
        self._orchestrator = ProductionOrchestrator(self.project, self.book_id)
        self._orchestrator.start({**context, "book_id": self.book_id})
        for stage in ("idea", "feasibility"):
            current = (self._orchestrator.load().get("steps", {}).get(stage) or {}).get("status")
            if current not in {"complete", "approved"}:
                self._orchestrator.complete(stage, detail="Adopted from the existing checked production route.")
        approval = context.get("content_plan_approval") or {}
        if isinstance(approval, dict) and approval.get("source") and approval.get("evidence_id"):
            current = (self._orchestrator.load().get("steps", {}).get("content_plan") or {}).get("status")
            if current not in {"complete", "approved"}:
                self._orchestrator.approve_human_stage(
                    "content_plan", source=str(approval["source"]),
                    evidence_id=str(approval["evidence_id"]),
                    detail="Adopted from persisted content-plan approval evidence.",
                )

    def _mirror_complete(self, stage: str, detail: str, artifact: str) -> None:
        if not self._orchestrator:
            return
        mapping = {"generate": "generation", "cover": "cover", "qa": "product_qa", "listing": "listing", "package": "package"}
        target = mapping.get(stage)
        if not target:
            return
        # Listing files are currently written before rendered Product QA. Keep
        # their checkpoint pending, then adopt it immediately after QA passes.
        if target == "listing" and (self._orchestrator.load().get("steps", {}).get("product_qa") or {}).get("status") != "complete":
            return
        try:
            self._orchestrator.complete(target, detail=detail, artifact=artifact)
            if target == "product_qa":
                saved_listing = (self.record().get("stages", {}).get("listing") or {})
                if saved_listing.get("status") == "complete":
                    self._orchestrator.complete("listing", detail=str(saved_listing.get("detail") or "Listing files created."), artifact=str(saved_listing.get("artifact") or ""))
        except ValueError:
            # The established production route remains authoritative. A mirror
            # mismatch is visible in the job record but never corrupts output.
            pass

    def record(self) -> dict:
        return _read(self.path, {"version": AUTOPILOT_VERSION, "book_id": self.book_id, "runs": [], "stages": {}})

    def begin(self, facts: dict) -> dict:
        record = self.record(); record["facts_fingerprint"] = facts["fingerprint"]; record["last_started"] = _now(); record.setdefault("runs", []).insert(0, {"run_id": _hash([self.book_id, _now()])[:16], "started": _now(), "facts_fingerprint": facts["fingerprint"], "result": "running"}); record["runs"] = record["runs"][:100]; _write(self.path, record); return record

    @staticmethod
    def stage_fingerprint(facts: dict, stage: str) -> str:
        from .puzzle_integrity import POLICY_REVISION
        return _hash({"facts": facts["fingerprint"], "stage": stage, "version": AUTOPILOT_VERSION,
                      "puzzle_quality_policy": POLICY_REVISION})

    def stage_is_current(self, stage: str, fingerprint: str) -> bool:
        value = self.record().get("stages", {}).get(stage, {})
        return value.get("status") == "complete" and value.get("fingerprint") == fingerprint

    def current_artifact(self, stage: str, fingerprint: str) -> Path | None:
        """Return only a verified unchanged stage artifact that still exists."""
        if not self.stage_is_current(stage, fingerprint):
            return None
        artifact = Path(str(self.record().get("stages", {}).get(stage, {}).get("artifact") or ""))
        return artifact if artifact.exists() else None

    def complete(self, stage: str, fingerprint: str, detail: str = "", artifact: str = "") -> None:
        record = self.record(); record.setdefault("stages", {})[stage] = {"status": "complete", "fingerprint": fingerprint, "completed": _now(), "detail": detail, "artifact": artifact}; _write(self.path, record)
        self._mirror_complete(stage, detail, artifact)

    def fail(self, stage: str, detail: str, *, human_review: bool = False) -> None:
        record = self.record(); record.setdefault("stages", {})[stage] = {"status": "needs_human_review" if human_review else "failed", "failed": _now(), "detail": detail};
        if record.get("runs"): record["runs"][0]["result"] = "needs_human_review" if human_review else "failed"; record["runs"][0]["failed_stage"] = stage
        _write(self.path, record)
        if self._orchestrator:
            mapping = {"validate": "feasibility", "plan": "content_plan", "generate": "generation", "cover": "cover", "preflight": "product_qa", "qa": "product_qa", "listing": "listing", "package": "package"}
            self._orchestrator.fail(mapping.get(stage, "generation"), detail, human_review=human_review)

    def run(self, facts: dict, stages: dict[str, Callable[[], object]], *, cancel: Callable[[], bool] | None = None, repair_limit: int = 2) -> dict:
        """Run supplied existing stages once each, resuming valid checkpoints.

        A stage callable may return a string detail or ``{"detail": ..., "repair":
        True}``. Repairs are bounded and only restart the same deterministic
        stage. Ambiguous errors are recorded for human review instead.
        """
        self.begin(facts); repairs = 0; result = {"completed": [], "skipped": [], "repairs": [], "status": "complete"}
        for stage in STAGES:
            if stage not in stages: continue
            fingerprint = self.stage_fingerprint(facts, stage)
            if self.stage_is_current(stage, fingerprint): result["skipped"].append(stage); continue
            if cancel and cancel(): self.fail(stage, "Stopped before this stage began."); result["status"] = "stopped"; return result
            try:
                value = stages[stage](); detail = value.get("detail", "") if isinstance(value, dict) else str(value or "")
                if isinstance(value, dict) and value.get("repair"):
                    if repairs >= repair_limit: self.fail(stage, "Safe repair limit reached; review this stage.", human_review=True); result["status"] = "needs_human_review"; return result
                    repairs += 1; result["repairs"].append(f"{stage}: {detail or 'safe deterministic repair'}"); value = stages[stage](); detail = value.get("detail", "") if isinstance(value, dict) else str(value or "")
                self.complete(stage, fingerprint, detail); result["completed"].append(stage)
            except Exception as exc:
                detail = str(exc); human = any(term in detail.casefold() for term in HUMAN_STOP_WORDS)
                self.fail(stage, detail, human_review=human); result["status"] = "needs_human_review" if human else "failed"; return result
        record = self.record()
        if record.get("runs"): record["runs"][0]["result"] = "complete"; record["runs"][0]["finished"] = _now(); _write(self.path, record)
        return result
