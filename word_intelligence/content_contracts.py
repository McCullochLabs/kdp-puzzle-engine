"""Canonical, additive content contracts for the future Content Intelligence Engine.

This module deliberately does not replace ``WordRecord`` or change any puzzle
generator.  It gives legacy loaders, migration tools, and later planners one
small shared representation for editorial content while the existing
``word_intelligence`` public API remains intact.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Iterable

from .normalization import clean_surface

SCHEMA_VERSION = 1
CONTENT_TYPES = frozenset({"word", "phrase", "cryptogram_prompt", "trivia", "fact", "bonus_page"})
RELATIONSHIPS = frozenset({"primary", "related"})
TOPIC_STATES = frozenset({"approved", "legacy_unreviewed", "proposed", "rejected", "unknown"})
EDITORIAL_STATES = frozenset({"approved", "legacy_unreviewed", "pending_review", "rejected", "unknown"})
FACTUAL_STATES = frozenset({"verified", "not_applicable", "legacy_unreviewed", "pending_review", "rejected", "unknown"})
SOURCE_TYPES = frozenset({"curated", "public_domain", "dictionary", "generated", "imported", "legacy"})
_ID_PART = re.compile(r"^[a-z][a-z0-9_-]{2,120}$")


class ContentContractError(ValueError):
    """Raised when a new canonical record is structurally unsafe to use."""


def canonical_display(value: object) -> str:
    """Keep buyer-facing spacing while treating all whitespace consistently."""
    return " ".join(str(value or "").strip().split())


def normalized_value(value: object) -> str:
    """Use the existing Word Intelligence comparison key without changing grids."""
    return clean_surface(canonical_display(value))


def deterministic_content_id(content_type: str, display: object, *, source_id: str = "") -> str:
    """Stable legacy migration ID based on type, normalized value, and source identity."""
    value = normalized_value(display)
    seed = "|".join((str(content_type).strip().casefold(), value, str(source_id).strip()))
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:20]
    return f"{str(content_type).strip().casefold()}_{digest}"


@dataclass(frozen=True)
class TopicReference:
    topic_id: str
    relationship: str = "primary"
    confidence: float = 0.0
    status: str = "legacy_unreviewed"

    def to_dict(self) -> dict[str, object]:
        return {"topic_id": self.topic_id, "relationship": self.relationship,
                "confidence": self.confidence, "status": self.status}


@dataclass(frozen=True)
class Provenance:
    source_type: str
    source_id: str
    reviewed_at: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"source_type": self.source_type, "source_id": self.source_id,
                "reviewed_at": self.reviewed_at}


@dataclass(frozen=True)
class QualityStatus:
    editorial_status: str = "legacy_unreviewed"
    factual_status: str = "not_applicable"
    trademark_review: bool = False
    safety_review: bool = False

    def to_dict(self) -> dict[str, object]:
        return {"editorial_status": self.editorial_status,
                "factual_status": self.factual_status,
                "trademark_review": self.trademark_review,
                "safety_review": self.safety_review}


@dataclass(frozen=True)
class FormatRules:
    word_search_max_letters: int | None = None
    cryptogram_max_characters: int | None = None
    requires_trivia_question_answer: bool = False
    safe_for_cover: bool = False

    def to_dict(self) -> dict[str, object]:
        return {"word_search_max_letters": self.word_search_max_letters,
                "cryptogram_max_characters": self.cryptogram_max_characters,
                "requires_trivia_question_answer": self.requires_trivia_question_answer,
                "safe_for_cover": self.safe_for_cover}


@dataclass(frozen=True)
class ContentRecord:
    """One generic editorial content item; not a Sudoku grid or a book plan."""
    id: str
    type: str
    display: str
    normalized: str
    topics: tuple[TopicReference, ...] = ()
    audiences: tuple[str, ...] = ()
    difficulty: str = "standard"
    format_rules: FormatRules = field(default_factory=FormatRules)
    quality: QualityStatus = field(default_factory=QualityStatus)
    provenance: Provenance | None = None
    payload: dict[str, object] = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version, "id": self.id, "type": self.type,
            "display": self.display, "normalized": self.normalized,
            "topics": [item.to_dict() for item in self.topics],
            "audiences": list(self.audiences), "difficulty": self.difficulty,
            "format_rules": self.format_rules.to_dict(), "quality": self.quality.to_dict(),
            "provenance": self.provenance.to_dict() if self.provenance else None,
            "payload": dict(self.payload),
        }


def _mapping(value: object, name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ContentContractError(f"{name} must be an object.")
    return value


def _strings(values: object, name: str) -> tuple[str, ...]:
    if values is None:
        return ()
    if not isinstance(values, (list, tuple)) or not all(isinstance(item, str) for item in values):
        raise ContentContractError(f"{name} must be a list of text values.")
    return tuple(canonical_display(item) for item in values if canonical_display(item))


def _state(value: object, allowed: frozenset[str], name: str) -> str:
    result = str(value or "").strip().casefold()
    if result not in allowed:
        raise ContentContractError(f"{name} must be one of: {', '.join(sorted(allowed))}.")
    return result


def content_record_from_dict(data: dict[str, object], *, strict: bool = True) -> ContentRecord:
    """Parse and validate a canonical record without writing any source file."""
    if not isinstance(data, dict):
        raise ContentContractError("Content record must be an object.")
    version = data.get("schema_version", SCHEMA_VERSION)
    if version != SCHEMA_VERSION:
        raise ContentContractError(f"Unsupported content schema version: {version!r}.")
    content_type = str(data.get("type") or "").strip().casefold()
    if content_type not in CONTENT_TYPES:
        raise ContentContractError(f"Unsupported content type: {content_type or '(missing)'}.")
    display = canonical_display(data.get("display"))
    if not display:
        raise ContentContractError("display is required.")
    normalized = normalized_value(data.get("normalized") or display)
    if not normalized:
        raise ContentContractError("normalized value is empty after cleanup.")
    source_raw = _mapping(data.get("provenance"), "provenance")
    provenance = None
    if source_raw:
        source_type = _state(source_raw.get("source_type"), SOURCE_TYPES, "provenance.source_type")
        source_id = canonical_display(source_raw.get("source_id"))
        if not source_id:
            raise ContentContractError("provenance.source_id is required.")
        provenance = Provenance(source_type, source_id, canonical_display(source_raw.get("reviewed_at")))
    elif strict:
        raise ContentContractError("provenance is required for canonical records.")
    record_id = canonical_display(data.get("id"))
    if not record_id:
        raise ContentContractError("id is required.")
    if not _ID_PART.fullmatch(record_id):
        raise ContentContractError("id must start with a lowercase letter and use lowercase letters, numbers, underscores, or hyphens.")
    topic_refs: list[TopicReference] = []
    raw_topics = data.get("topics") or []
    if not isinstance(raw_topics, list):
        raise ContentContractError("topics must be a list.")
    for index, raw in enumerate(raw_topics, 1):
        item = _mapping(raw, f"topics[{index}]")
        topic_id = canonical_display(item.get("topic_id"))
        if not topic_id:
            raise ContentContractError(f"topics[{index}].topic_id is required.")
        relationship = _state(item.get("relationship", "primary"), RELATIONSHIPS, f"topics[{index}].relationship")
        try:
            confidence = float(item.get("confidence", 0))
        except (TypeError, ValueError):
            raise ContentContractError(f"topics[{index}].confidence must be numeric.") from None
        if not 0 <= confidence <= 100:
            raise ContentContractError(f"topics[{index}].confidence must be between 0 and 100.")
        topic_refs.append(TopicReference(topic_id, relationship, confidence,
                                         _state(item.get("status", "legacy_unreviewed"), TOPIC_STATES, f"topics[{index}].status")))
    quality_raw = _mapping(data.get("quality"), "quality")
    quality = QualityStatus(
        _state(quality_raw.get("editorial_status", "legacy_unreviewed"), EDITORIAL_STATES, "quality.editorial_status"),
        _state(quality_raw.get("factual_status", "not_applicable"), FACTUAL_STATES, "quality.factual_status"),
        bool(quality_raw.get("trademark_review", False)), bool(quality_raw.get("safety_review", False)),
    )
    rules_raw = _mapping(data.get("format_rules"), "format_rules")
    def nonnegative_int(name: str) -> int | None:
        value = rules_raw.get(name)
        if value is None: return None
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ContentContractError(f"format_rules.{name} must be a positive integer or null.")
        return value
    rules = FormatRules(nonnegative_int("word_search_max_letters"), nonnegative_int("cryptogram_max_characters"),
                        bool(rules_raw.get("requires_trivia_question_answer", False)), bool(rules_raw.get("safe_for_cover", False)))
    payload = _mapping(data.get("payload"), "payload")
    if content_type == "trivia" and strict and (not canonical_display(payload.get("question")) or not canonical_display(payload.get("answer"))):
        raise ContentContractError("Trivia records require payload.question and payload.answer.")
    return ContentRecord(record_id, content_type, display, normalized, tuple(topic_refs),
                         _strings(data.get("audiences") or [], "audiences"), canonical_display(data.get("difficulty")) or "standard",
                         rules, quality, provenance, dict(payload), int(version))


def legacy_content_record(content_type: str, display: object, *, source_id: str,
                          topics: Iterable[TopicReference] = (), payload: dict[str, object] | None = None,
                          factual_status: str = "not_applicable") -> ContentRecord:
    """Adapt legacy data without claiming it has newly received editorial approval."""
    shown = canonical_display(display)
    source = Provenance("legacy", source_id)
    return content_record_from_dict({
        "schema_version": SCHEMA_VERSION,
        "id": deterministic_content_id(content_type, shown, source_id=source_id),
        "type": content_type, "display": shown, "normalized": normalized_value(shown),
        "topics": [item.to_dict() for item in topics],
        "quality": {"editorial_status": "legacy_unreviewed", "factual_status": factual_status,
                    "trademark_review": False, "safety_review": False},
        "provenance": source.to_dict(), "payload": payload or {},
    })


def deterministic_json(record: ContentRecord) -> str:
    """Stable serialization for curated files, tests, and future migration tooling."""
    return json.dumps(record.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
