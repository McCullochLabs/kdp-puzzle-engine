"""Load the approved additive editorial vocabulary overlay.

The large generated Master Library remains rebuildable.  Editorially promoted
book vocabulary lives in a small, fingerprinted additive file so a later
Master Library refresh cannot silently disconnect published themes from their
reviewed topic evidence.
"""
from __future__ import annotations

import json
from pathlib import Path

from .normalization import clean_surface
from .records import APPROVED, EvidenceItem, SIGNAL_HUMAN_DECISION, TopicLink


FILENAME = "editorial_wordsearch_topic_overlay.json"
APPROVED_STATUS = "APPROVED_FOR_LOCAL_PRODUCTION"


def load_overlay(project_root: Path | str) -> dict:
    path = Path(project_root) / "word_banks" / FILENAME
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) and data.get("status") == APPROVED_STATUS else {}


def merge_master_bank(bank: dict, project_root: Path | str) -> dict:
    """Return an in-memory merged library; never rewrite the generated bank."""
    from .family_content_reviews import merge_bank_reviews
    bank = merge_bank_reviews(bank, project_root)
    overlay = load_overlay(project_root)
    if not overlay:
        return bank
    topics = bank.setdefault("topics", {})
    profiles = bank.setdefault("word_profiles", {})
    words = bank.setdefault("words", [])
    all_words = set(str(item) for item in words)
    for topic, values in (overlay.get("topics") or {}).items():
        bucket = set(str(item) for item in topics.setdefault(str(topic), []))
        bucket.update(str(item) for item in values)
        topics[str(topic)] = sorted(bucket)
        all_words.update(str(item) for item in values)
    bank["words"] = sorted(all_words)
    for word, additions in (overlay.get("word_profiles") or {}).items():
        profile = profiles.setdefault(str(word), {})
        for field in ("topics", "sources", "grade_bands"):
            current = set(str(item) for item in profile.get(field, []))
            current.update(str(item) for item in additions.get(field, []))
            if current:
                profile[field] = sorted(current)
    return bank


def apply_store_overlay(store, taxonomy, project_root: Path | str) -> dict[str, int]:
    """Attach approved topic evidence to a persisted or newly built store."""
    from .family_content_reviews import apply_store_reviews
    apply_store_reviews(store, taxonomy, project_root)
    overlay = load_overlay(project_root)
    if not overlay:
        return {"added": 0, "updated": 0, "unknown_topics": 0}
    added = updated = unknown = 0
    for topic, values in (overlay.get("topics") or {}).items():
        topic_id = taxonomy.resolve(str(topic))
        if not topic_id:
            unknown += 1
            continue
        store.topic_lexicon.setdefault(topic_id, set())
        for display in values:
            normal = clean_surface(display)
            if not normal:
                continue
            record = store.ensure_record(normal, str(display))
            if "editorial_wordsearch_rebuild_v2" not in record.sources:
                record.sources.append("editorial_wordsearch_rebuild_v2")
            link = record.link_for(topic_id)
            if link is None:
                record.topics.append(TopicLink(topic_id, APPROVED, 100.0,
                    [EvidenceItem(SIGNAL_HUMAN_DECISION, "Approved editorial Word Search rebuild", 100.0)]))
                added += 1
            else:
                link.status = APPROVED
                link.confidence = 100.0
                updated += 1
            store.topic_lexicon[topic_id].add(normal)
    return {"added": added, "updated": updated, "unknown_topics": unknown}
