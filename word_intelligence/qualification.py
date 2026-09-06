"""Auditable, non-mutating editorial pre-qualification for Phase 3.

This module deliberately prepares records for a human decision.  It never
rewrites a source bank and never upgrades a record to editorial approval.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path

from .capacity import MECHANICAL_PROMPT_MARKERS, WORD_SEARCH_TYPES
from .content_contracts import ContentRecord, normalized_value


@dataclass(frozen=True)
class ApprovalDecision:
    content_id: str
    topic_id: str
    decision: str
    reviewed_at: str = ""
    review_source: str = "human"
    factual_status: str = ""

    @property
    def is_approval(self) -> bool:
        return self.decision == "approved" and self.review_source == "human"


def load_approval_input(path: Path | str) -> dict[str, ApprovalDecision]:
    """Load an explicit human-decision file; invalid entries are ignored.

    The file is an overlay for planning/review only.  It does not update a
    record, the Master Word Bank, or the persisted intelligence cache.
    """
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        return {}
    output: dict[str, ApprovalDecision] = {}
    for row in data.get("decisions") or []:
        if not isinstance(row, dict):
            continue
        content_id = str(row.get("content_id") or "")
        decision = str(row.get("decision") or "")
        if content_id and decision in {"approved", "rejected", "needs_review"}:
            output[content_id] = ApprovalDecision(
                content_id=content_id, topic_id=str(row.get("topic_id") or ""),
                decision=decision, reviewed_at=str(row.get("reviewed_at") or ""),
                review_source=str(row.get("review_source") or "human"),
                factual_status=str(row.get("factual_status") or ""),
            )
    return output


def prequalification_reasons(record: ContentRecord, topic_id: str, puzzle_type: str) -> list[str]:
    """Return deterministic reasons a record is or is not review-ready."""
    reasons: list[str] = []
    if not record.normalized:
        reasons.append("blank_normalized")
    if not record.provenance:
        reasons.append("missing_provenance")
    if record.quality.trademark_review or record.quality.safety_review:
        reasons.append("safety_or_trademark_review")
    links = [link for link in record.topics if link.topic_id == topic_id]
    if not links:
        reasons.append("topic_not_resolved")
    if puzzle_type == "word_search":
        if record.type not in WORD_SEARCH_TYPES:
            reasons.append("wrong_content_type")
        if len(record.normalized) > 21:
            reasons.append("word_search_too_long")
    elif puzzle_type == "cryptogram":
        if record.type != "cryptogram_prompt":
            reasons.append("wrong_content_type")
        if not record.display or len(record.display) > 110:
            reasons.append("cryptogram_layout_invalid")
        if any(marker in record.display.upper() for marker in MECHANICAL_PROMPT_MARKERS):
            reasons.append("mechanically_patterned")
    elif puzzle_type == "scramble_trivia":
        if record.type != "trivia":
            reasons.append("wrong_content_type")
        if not str(record.payload.get("question") or "").strip() or not str(record.payload.get("answer") or "").strip():
            reasons.append("incomplete_trivia")
        if len(record.normalized) < 4 or not record.normalized.isalpha():
            reasons.append("invalid_scramble_answer")
    else:
        reasons.append("unsupported_format")
    return reasons


def build_review_batch(records: list[ContentRecord], topic_id: str, puzzle_type: str) -> dict[str, object]:
    """Build an explicit review artifact without applying any decision."""
    rows = []
    seen: set[str] = set()
    for record in sorted(records, key=lambda item: (item.normalized, item.id)):
        reasons = prequalification_reasons(record, topic_id, puzzle_type)
        duplicate = bool(record.normalized and record.normalized in seen)
        seen.add(record.normalized)
        rows.append({
            "content_id": record.id, "display": record.display,
            "normalized": record.normalized, "topic_id": topic_id,
            "source": record.provenance.to_dict() if record.provenance else {},
            "editorial_status": record.quality.editorial_status,
            "format_eligible": not reasons and not duplicate,
            "duplicate_normalized": duplicate,
            "protected_name_flag": bool(record.quality.trademark_review),
            "suggested_review_action": "qualified_for_review" if not reasons and not duplicate else "needs_review",
            "reasons": reasons + (["duplicate_normalized"] if duplicate else []),
        })
    return {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "topic_id": topic_id, "puzzle_type": puzzle_type,
        "records": rows,
        "note": "This batch is review-only. It changes no source content or approval state.",
    }


def write_review_batch(path: Path | str, records: list[ContentRecord], topic_id: str, puzzle_type: str) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(build_review_batch(records, topic_id, puzzle_type), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target

