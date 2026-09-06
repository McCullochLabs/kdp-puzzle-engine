"""Word Intelligence store: records + performance indexes + persistence.

Ingests the EXISTING project data (read-only):

- Guided_Builder_Master_Word_Bank.json  -> trusted topic membership
- source_data/dwyl_topic_candidate_catalog.json -> root suggestions + zipf cache
- source_data/education_grade_word_bands.json   -> audience bands
- safety lists (REVIEW_REQUIRED_TERMS etc.)     -> trademark/safety flags

The master bank itself is NEVER modified by this module. Approved changes
flow through the apply engine / curated-source path instead.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .normalization import clean_surface, split_tokens, variant_group_key
from .records import (
    CLASSIFIER_VERSION,
    TRUSTED,
    EvidenceItem,
    SIGNAL_EXISTING,
    TopicLink,
    WordRecord,
    APPROVED,
    PROPOSED,
    REJECTED,
    SIGNAL_HUMAN_DECISION,

)
from .taxonomy import _name_tokens_in_order, canonical_slug

DEFAULT_STATE_DIR = Path("word_banks") / "word_intelligence"
STORE_FILENAME = "word_store.json"
AMBIGUITY_FILENAME = "ambiguity_registry.json"
REVIEW_QUEUE_FILENAME = "review_queue.json"
DECISIONS_LOGNAME = "decisions.jsonl"
APPROVED_LINKS_FILENAME = "approved_topic_links.json"


def _load_json(path) -> dict | None:
    try:
        with open(path, encoding="utf-8-sig") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def safety_terms():
    """Trademark/review term sets without duplicating their definitions.

    Imports the project's own lists (same pattern the existing builder
    scripts use).  Falls back to a minimal conservative seed when the GUI
    module cannot be imported (e.g., stripped test environments) so safety
    checks NEVER silently disappear.
    """
    try:
        from word_search_creator import EXTRA_REJECTED_TERMS, REVIEW_REQUIRED_TERMS

        return set(REVIEW_REQUIRED_TERMS), set(EXTRA_REJECTED_TERMS)
    except Exception:
        return (
            {"DISNEY", "MARVEL", "STARWARS", "POKEMON", "MINECRAFT",
             "FORTNITE", "NINTENDO", "PLAYSTATION", "XBOX", "LEGO"},
            set(),
        )


class WordIntelligenceStore:
    """Records plus the indexes that make classification cheap."""

    def __init__(self) -> None:
        self.records: dict[str, WordRecord] = {}
        self.dictionary_words: set[str] = set()      # full searchable vocabulary
        self.topic_lexicon: dict[str, set[str]] = {}  # canonical id -> trusted words
        self._token_index: dict[str, set[str]] = {}
        self._variant_groups: dict[str, set[str]] = {}
        self.display_forms: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    def ingest_master_bank(self, bank: dict, taxonomy=None) -> None:
        """Trusted membership + profiles. `taxonomy` canonicalizes aliases."""
        resolve = taxonomy.resolve if taxonomy else (
            lambda name: canonical_slug(_name_tokens_in_order(name)))
        topics: dict[str, list[str]] = bank.get("topics") or {}
        profiles: dict[str, dict] = bank.get("word_profiles") or {}

        for raw_key, members in topics.items():
            cid = resolve(raw_key)
            self.topic_lexicon.setdefault(cid, set())
            for member in members or []:
                norm = clean_surface(member)
                if len(norm) < 2:
                    continue
                self.topic_lexicon[cid].add(norm)
                record = self._record_for(norm, member)
                if "master_bank_topics" not in record.sources:
                    record.sources.append("master_bank_topics")
                existing = record.link_for(cid)
                if existing is None:
                    record.topics.append(TopicLink(
                        topic_id=cid,
                        status=TRUSTED,
                        confidence=100.0,
                        evidence=[EvidenceItem(
                            SIGNAL_EXISTING,
                            f"Existing trusted association ({raw_key})", 30)],
                    ))
                elif existing.status != TRUSTED:
                    existing.status = TRUSTED

        # Grade bands + related-topic hints from profiles.
        for word, profile in profiles.items():
            norm = clean_surface(word)
            record = self.records.get(norm)
            if record is None:
                continue
            bands = [b for b in profile.get("grade_bands", [])]
            if not bands:
                bands = sorted({
                    t for t in (profile.get("topics") or [])
                    if t.casefold().startswith("grade")
                })
            for band in bands:
                if band not in record.grade_bands:
                    record.grade_bands.append(band)

        for word in bank.get("words") or []:
            norm = clean_surface(word)
            if norm:
                self.dictionary_words.add(norm)

    def ingest_curated_seeds(self, doc: dict, taxonomy) -> dict:
        """Curated Phase-4 seed vocabulary - strong, explainable anchors.

        Adds TRUSTED links with explicit human-curation provenance.  Never
        overwrites an existing human decision: trusted/approved links are
        preserved as-is, REJECTED links are never flipped, and proposed
        links are yielded to TRUSTED only when the word is genuinely the
        curated topic's seed.  build_store() calls this on every rebuild;
        the resulting TRUSTED links persist in word_store.json.
        """
        if taxonomy is None:
            return {"added": 0, "kept": 0, "skipped_unknown_topic": 0,
                    "skipped_rejected": 0}
        resolve = taxonomy.resolve
        added = kept = bad_topic = bad_rejected = 0
        for seed in doc.get("seeds", []):
            cid = resolve(seed.get("topic_id", ""))
            if not cid or cid not in self.topic_lexicon:
                bad_topic += 1
                continue
            norm = clean_surface(seed.get("word", ""))
            if len(norm) < 2:
                bad_topic += 1
                continue
            record = self._record_for(norm, seed.get("word", norm))
            source = doc.get("provenance", "curated_seed")
            if source not in record.sources:
                record.sources.append(source)
            link = record.link_for(cid)
            if link is None:
                record.topics.append(TopicLink(
                    topic_id=cid, status=TRUSTED, confidence=100.0,
                    evidence=[EvidenceItem(
                        SIGNAL_HUMAN_DECISION,
                        f"Phase-4 curated seed ({source})", 100.0)]))
                self.topic_lexicon[cid].add(norm)
                added += 1
            elif link.status in (TRUSTED, APPROVED):
                self.topic_lexicon[cid].add(norm)
                kept += 1
            elif link.status == REJECTED:
                bad_rejected += 1
            elif link.status == PROPOSED:
                link.status = TRUSTED
                link.confidence = 100.0
                link.evidence = [EvidenceItem(
                    SIGNAL_HUMAN_DECISION,
                    f"Phase-4 curated seed ({source})", 100.0)]
                self.topic_lexicon[cid].add(norm)
                added += 1
        return {"added": added, "kept": kept,
                "skipped_unknown_topic": bad_topic,
                "skipped_rejected": bad_rejected}


    def ingest_candidate_catalog(self, catalog: dict, taxonomy=None) -> None:
        """Zipf familiarity cache + existing root suggestions (one signal each)."""
        resolve = taxonomy.resolve if taxonomy else (
            lambda name: canonical_slug(_name_tokens_in_order(name)))
        for word, score in (catalog.get("frequency_scores") or {}).items():
            norm = clean_surface(word)
            if not norm:
                continue
            record = self._record_for(norm, word)
            record.frequency = float(score)
        for word, suggested in (catalog.get("root_suggestions") or {}).items():
            norm = clean_surface(word)
            if not norm:
                continue
            record = self._record_for(norm, word)
            if "dwyl_root_suggestion" not in record.sources:
                record.sources.append("dwyl_root_suggestion")

    def ingest_grade_bands(self, bands_doc: dict) -> None:
        for band_name, words in (bands_doc.get("bands") or {}).items():
            for word in words or []:
                norm = clean_surface(word)
                if not norm:
                    continue
                record = self._record_for(norm, word)
                if band_name not in record.grade_bands:
                    record.grade_bands.append(band_name)

    def ingest_dictionary(self, words) -> int:
        """Register raw dictionary vocabulary for wide classification runs."""
        added = 0
        for word in words:
            norm = clean_surface(word)
            if len(norm) >= 3 and norm not in self.dictionary_words:
                self.dictionary_words.add(norm)
                added += 1
        return added

    def apply_safety_flags(self) -> tuple[int, int]:
        review_terms, rejected_terms = safety_terms()
        n_trademark = n_rejected = 0
        for term in review_terms:
            norm = clean_surface(term)
            record = self._record_for(norm, term)
            record.trademark_review = True
            n_trademark += 1
            self.dictionary_words.add(norm)
        for term in rejected_terms:
            norm = clean_surface(term)
            record = self._record_for(norm, term)
            record.safety_review = True
            n_rejected += 1
            self.dictionary_words.add(norm)
        return n_trademark, n_rejected

    # ------------------------------------------------------------------
    # Records + indexes
    # ------------------------------------------------------------------

    def _record_for(self, norm: str, original: str = "") -> WordRecord:
        record = self.records.get(norm)
        if record is None:
            record = WordRecord(normalized=norm, display=original or norm)
            self.records[norm] = record
        if original and original != norm and original not in record.aliases:
            record.aliases.append(original)
        self.display_forms.setdefault(norm, record.display)
        group = variant_group_key(norm)
        self._variant_groups.setdefault(group, set()).add(norm)
        for token in split_tokens(norm):
            self._token_index.setdefault(token, set()).add(norm)
        self.dictionary_words.add(norm)
        return record

    def get(self, normalized: str) -> WordRecord | None:
        return self.records.get(normalized)

    def ensure_record(self, normalized: str, original: str = "") -> WordRecord:
        return self._record_for(clean_surface(normalized), original)

    def words_with_token(self, token: str) -> set[str]:
        return set(self._token_index.get(token, ()))

    def variant_neighbors(self, normalized: str) -> set[str]:
        group = self._variant_groups.get(variant_group_key(normalized), set())
        return {w for w in group if w != normalized}

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "schema_version": 1,
            "classifier_version": CLASSIFIER_VERSION,
            "record_count": len(self.records),
            "dictionary_word_count": len(self.dictionary_words),
            "records": [r.to_dict() for r in self.records.values()],
            "dictionary_words": sorted(self.dictionary_words),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WordIntelligenceStore":
        store = cls()
        for rec in data.get("records", []):
            record = WordRecord.from_dict(rec)
            if record.normalized:
                store.records[record.normalized] = record
                store.dictionary_words.add(record.normalized)
                store.display_forms.setdefault(record.normalized, record.display)
                group = variant_group_key(record.normalized)
                store._variant_groups.setdefault(group, set()).add(record.normalized)
                for token in split_tokens(record.normalized):
                    store._token_index.setdefault(token, set()).add(record.normalized)
        for word in data.get("dictionary_words", []):
            store.dictionary_words.add(clean_surface(word))
        return store

    def save(self, state_dir=DEFAULT_STATE_DIR) -> Path:
        state_dir = Path(state_dir)
        state_dir.mkdir(parents=True, exist_ok=True)
        path = state_dir / STORE_FILENAME
        payload = json.dumps(self.to_dict(), indent=1, ensure_ascii=False)
        fd, tmp_name = tempfile.mkstemp(dir=str(state_dir), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(tmp_name, path)
        return path

    @classmethod
    def load(cls, state_dir=DEFAULT_STATE_DIR) -> "WordIntelligenceStore":
        data = _load_json(Path(state_dir) / STORE_FILENAME)
        if data is None:
            raise FileNotFoundError(f"No word intelligence store at {state_dir}")
        return cls.from_dict(data)


def build_store(project_root=".", taxonomy=None) -> tuple[WordIntelligenceStore, dict]:
    """Convenience: build a store from the real project files.

    Returns (store, sources_report) - strictly read-only over inputs.
    """
    root = Path(project_root)
    store = WordIntelligenceStore()
    report: dict[str, object] = {}

    bank = _load_json(root / "word_banks" / "Guided_Builder_Master_Word_Bank.json") or {}
    store.ingest_master_bank(bank, taxonomy)
    report["trusted_records"] = len(store.records)


    # Curated Phase-4 seed vocabulary (additive, human-decision-preserving).
    seeds_doc = _load_json(root / "word_banks" / "word_intelligence"
                           / "curated_seeds.json") or {}
    report["curated_seeds"] = store.ingest_curated_seeds(seeds_doc, taxonomy)

    catalog = _load_json(root / "word_banks" / "source_data" / "dwyl_topic_candidate_catalog.json") or {}
    store.ingest_candidate_catalog(catalog, taxonomy)
    report["with_frequency_cache"] = sum(1 for r in store.records.values() if r.frequency is not None)

    bands = _load_json(root / "word_banks" / "source_data" / "education_grade_word_bands.json") or {}
    store.ingest_grade_bands(bands)

    dwyl = root / "word_banks" / "source_data" / "dwyl_words_alpha.txt"
    if dwyl.exists():
        with open(dwyl, encoding="utf-8", errors="replace") as handle:
            raw_words = [line.strip() for line in handle if line.strip()]
        added = store.ingest_dictionary(raw_words)
        report["dictionary_entries"] = len(raw_words)
        report["dictionary_added_new"] = added

    trademark, rejected = store.apply_safety_flags()
    report["trademark_flagged"] = trademark
    report["safety_rejected"] = rejected
    return store, report


def make_test_store(topics: dict[str, list[str]], extra_words=None) -> WordIntelligenceStore:
    """Tiny store fixture for tests (mirrors master-bank shape)."""
    bank = {"topics": topics, "words": sorted({w for ws in topics.values() for w in ws})}
    store = WordIntelligenceStore()
    store.ingest_master_bank(bank)
    for word in extra_words or []:
        store.ensure_record(word, word)
    return store
