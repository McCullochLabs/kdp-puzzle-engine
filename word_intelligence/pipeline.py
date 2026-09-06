"""End-to-end intelligence pipeline runner.

One entry point used by the GUI, future CLI and validation probes so the
classification flow stays identical everywhere:

    build taxonomy -> build store -> prepare indexes -> classify -> stats
"""

from __future__ import annotations

import json
from pathlib import Path

from .ambiguity import AmbiguityRegistry, scan_for_ambiguity
from .analysis import coverage_summary
from .classifier import Classifier, RunStats, scope_records
from .store import DEFAULT_STATE_DIR, WordIntelligenceStore, _load_json
from .taxonomy import TopicTaxonomy


def load_taxonomy(project_root=".") -> TopicTaxonomy:
    bank = _load_json(Path(project_root) / "word_banks"
                      / "Guided_Builder_Master_Word_Bank.json") or {}
    taxonomy = TopicTaxonomy.from_master_bank(bank)
    # Shared legacy aliases must resolve in capacity checks and audits too,
    # not only inside the Book Planner's optional saved-route flow.
    from .topic_routing import apply_builtin_aliases
    apply_builtin_aliases(taxonomy)
    return taxonomy


def load_or_build_store(taxonomy, project_root=".", state_dir=DEFAULT_STATE_DIR):
    """Reuse the persisted store when present, else rebuild from sources."""
    try:
        return WordIntelligenceStore.load(state_dir)
    except FileNotFoundError:
        from .store import build_store
        store, report = build_store(project_root, taxonomy)
        return store, report


def run_classification(store, taxonomy, catalog=None, themes_dir=None,
                       scope: str = "proven",
                       ambiguity_registry: AmbiguityRegistry | None = None,
                       detect_ambiguous: bool = True):
    """Classify the requested scope; returns (classifier, RunStats)."""
    registry = ambiguity_registry if ambiguity_registry is not None \
        else AmbiguityRegistry.load(DEFAULT_STATE_DIR)
    classifier = Classifier(store, taxonomy, registry)
    prepared = classifier.prepare(catalog=catalog, themes_dir=themes_dir)

    families = {cid: t.family for cid, t in taxonomy.topics.items()}
    detected = scan_for_ambiguity(store, families, registry) if detect_ambiguous else []

    stats = RunStats()
    records = sorted(scope_records(store, scope),
                     key=lambda r: r.normalized)
    classifier.classify_many(records, stats)
    summary = {
        "prepared": prepared,
        "scope": scope,
        "ambiguity_detected": detected,
        "stats": stats.to_dict(),
        "coverage": coverage_summary(store),
    }
    return classifier, stats, summary


def load_candidate_catalog(project_root=".") -> dict:
    return _load_json(Path(project_root) / "word_banks" / "source_data"
                      / "dwyl_topic_candidate_catalog.json") or {}


def save_store_quietly(store, state_dir=DEFAULT_STATE_DIR):
    try:
        path = store.save(state_dir)
        return {"saved": True, "path": str(path)}
    except OSError as exc:
        return {"saved": False, "error": str(exc)}
