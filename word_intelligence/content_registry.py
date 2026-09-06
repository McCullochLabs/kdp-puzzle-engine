"""Read-only compatibility registry for canonical editorial content records."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .content_contracts import (
    ContentRecord, TopicReference, canonical_display, legacy_content_record,
    normalized_value,
)


@dataclass
class ContentRegistry:
    """Small indexed registry. It does not alter legacy JSON, themes, or stores."""
    records: dict[str, ContentRecord] = field(default_factory=dict)
    by_topic: dict[str, set[str]] = field(default_factory=dict)
    by_type: dict[str, set[str]] = field(default_factory=dict)

    def add(self, record: ContentRecord) -> None:
        prior = self.records.get(record.id)
        if prior and prior != record:
            raise ValueError(f"Content ID collision: {record.id}")
        self.records[record.id] = record
        self.by_type.setdefault(record.type, set()).add(record.id)
        for link in record.topics:
            self.by_topic.setdefault(link.topic_id, set()).add(record.id)

    def get(self, content_id: str) -> ContentRecord | None:
        return self.records.get(str(content_id))

    def find(self, *, topic_id: str | None = None, content_type: str | None = None,
             editorial_status: str | None = None) -> list[ContentRecord]:
        candidates = set(self.records)
        if topic_id is not None:
            candidates &= self.by_topic.get(topic_id, set())
        if content_type is not None:
            candidates &= self.by_type.get(content_type, set())
        result = [self.records[item] for item in sorted(candidates)]
        if editorial_status is not None:
            result = [item for item in result if item.quality.editorial_status == editorial_status]
        return result

    def format_eligible(self, content_type: str, *, max_letters: int | None = None,
                        max_characters: int | None = None) -> list[ContentRecord]:
        result = self.find(content_type=content_type)
        eligible: list[ContentRecord] = []
        for item in result:
            if max_letters is not None and len(item.normalized) > max_letters:
                continue
            if max_characters is not None and len(item.display) > max_characters:
                continue
            eligible.append(item)
        return eligible


def _topic_ref(raw_name: str, taxonomy) -> TopicReference:
    resolved = taxonomy.resolve(raw_name) if taxonomy else None
    return TopicReference(resolved or canonical_display(raw_name), "primary", 100 if resolved else 0,
                          "legacy_unreviewed")


def load_master_bank_legacy(path: Path, taxonomy=None) -> ContentRegistry:
    """Adapt master-bank vocabulary in memory. No approval status is upgraded."""
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    registry = ContentRegistry()
    grouped: dict[str, tuple[str, list[TopicReference]]] = {}
    for topic, members in (data.get("topics") or {}).items():
        ref = _topic_ref(str(topic), taxonomy)
        for member in members or []:
            shown = canonical_display(member)
            key = normalized_value(shown)
            if not key:
                continue
            existing = grouped.get(key)
            if existing is None:
                grouped[key] = (shown, [ref])
            elif ref not in existing[1]:
                existing[1].append(ref)
    for normalized, (shown, topics) in grouped.items():
        content_type = "word" if " " not in shown and "-" not in shown else "phrase"
        registry.add(legacy_content_record(content_type, shown, source_id=f"master_bank:{normalized}", topics=topics))
    return registry


def load_puzzle_content_library_legacy(path: Path, taxonomy=None) -> ContentRegistry:
    """Adapt legacy Cryptogram and Trivia pack entries in memory."""
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    registry = ContentRegistry()
    for theme, pack in (data.get("packs") or {}).items():
        ref = _topic_ref(str(theme), taxonomy)
        for index, value in enumerate((pack or {}).get("cryptograms") or []):
            shown = canonical_display(value)
            if shown:
                registry.add(legacy_content_record("cryptogram_prompt", shown,
                    source_id=f"puzzle_content:{theme}:cryptogram:{index}", topics=(ref,)))
        for index, item in enumerate((pack or {}).get("trivia") or []):
            if not isinstance(item, (list, tuple)) or len(item) != 3:
                continue
            answer, question, explanation = (canonical_display(value) for value in item)
            if answer and question and explanation:
                registry.add(legacy_content_record("trivia", answer,
                    source_id=f"puzzle_content:{theme}:trivia:{index}", topics=(ref,),
                    payload={"question": question, "answer": explanation},
                    factual_status="legacy_unreviewed"))
    return registry


def load_theme_legacy(path: Path, taxonomy=None) -> ContentRegistry:
    """Expose a theme's existing word lists as unreviewed legacy records."""
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    registry = ContentRegistry()
    source_topics = ((data.get("source_word_bank") or {}).get("topics") or
                     [data.get("detected_topic") or data.get("topic") or data.get("series")])
    refs = tuple(_topic_ref(str(item), taxonomy) for item in source_topics if canonical_display(item))
    for p_index, puzzle in enumerate(data.get("puzzles") or []):
        for w_index, word in enumerate((puzzle or {}).get("words") or []):
            shown = canonical_display(word)
            if not shown:
                continue
            content_type = "word" if " " not in shown and "-" not in shown else "phrase"
            registry.add(legacy_content_record(content_type, shown,
                source_id=f"theme:{Path(path).name}:{p_index}:{w_index}", topics=refs))
    return registry
