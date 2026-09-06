"""Source-manifest foundation for persisted Word Intelligence caches.

Phase 1 only reports freshness. It intentionally does not alter current cache
rebuild behavior or add synchronous work to the Tkinter UI.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

SCHEMA_VERSION = 1
ENGINE_VERSION = "word_intelligence_phase1"
DEFAULT_SOURCES = {
    "master_bank": "word_banks/Guided_Builder_Master_Word_Bank.json",
    "candidate_catalog": "word_banks/source_data/dwyl_topic_candidate_catalog.json",
    "grade_bands": "word_banks/source_data/education_grade_word_bands.json",
    "dictionary": "word_banks/source_data/dwyl_words_alpha.txt",
    "curated_seeds": "word_banks/word_intelligence/curated_seeds.json",
    "content_library": "word_banks/puzzle_content_library.json",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(project_root: Path | str, *, sources: dict[str, str] | None = None,
                   record_count: int | None = None) -> dict[str, object]:
    root = Path(project_root)
    source_map = sources or DEFAULT_SOURCES
    hashes, missing = {}, []
    for name, relative in source_map.items():
        path = root / relative
        if path.is_file(): hashes[name] = sha256_file(path)
        else: missing.append(name)
    return {"schema_version": SCHEMA_VERSION, "engine_version": ENGINE_VERSION,
            "source_paths": dict(source_map), "source_hashes": hashes,
            "missing_sources": missing,
            "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "record_count": record_count}


def compare_manifest(saved: dict | None, current: dict) -> dict[str, object]:
    """Return a human-readable freshness result; never mutates caches."""
    if not saved:
        return {"fresh": False, "state": "missing_manifest", "reasons": ["No source manifest is stored with this cache."]}
    if saved.get("schema_version") != SCHEMA_VERSION:
        return {"fresh": False, "state": "unsupported_manifest", "reasons": ["Cache manifest schema is unsupported."]}
    reasons: list[str] = []
    if current.get("missing_sources"):
        reasons.append("Required content source is missing: " + ", ".join(current["missing_sources"]))
    before, after = saved.get("source_hashes") or {}, current.get("source_hashes") or {}
    for name in sorted(set(before) | set(after)):
        if before.get(name) != after.get(name): reasons.append(f"Source changed: {name}")
    return {"fresh": not reasons, "state": "fresh" if not reasons else "stale", "reasons": reasons,
            "saved_record_count": saved.get("record_count"), "current_record_count": current.get("record_count")}


def load_manifest(path: Path | str) -> dict | None:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def deterministic_manifest_json(manifest: dict) -> str:
    return json.dumps(manifest, indent=2, sort_keys=True) + "\n"


def safe_rebuild_store(project_root: Path | str, *, state_dir: Path | str | None = None) -> dict[str, object]:
    """Build a validated replacement cache before atomically activating it.

    This function is intentionally separate from normal UI loading.  It keeps
    the prior store as ``word_store.previous.json`` until a later maintenance
    policy decides how long to retain backups.
    """
    root = Path(project_root)
    active_dir = Path(state_dir) if state_dir else root / "word_banks" / "word_intelligence"
    active_store = active_dir / "word_store.json"
    active_manifest = active_dir / "source_manifest.json"
    active_dir.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix="word_intelligence_rebuild_", dir=str(active_dir.parent)))
    try:
        from .pipeline import load_taxonomy
        from .store import build_store
        taxonomy = load_taxonomy(root)
        store, report = build_store(root, taxonomy)
        if not store.records:
            raise RuntimeError("Rebuilt store has no records.")
        store.save(temp_dir)
        manifest = build_manifest(root, record_count=len(store.records))
        temp_manifest = temp_dir / "source_manifest.json"
        temp_manifest.write_text(deterministic_manifest_json(manifest), encoding="utf-8")
        active_dir.mkdir(parents=True, exist_ok=True)
        if active_store.exists(): shutil.copy2(active_store, active_dir / "word_store.previous.json")
        if active_manifest.exists(): shutil.copy2(active_manifest, active_dir / "source_manifest.previous.json")
        os.replace(temp_dir / "word_store.json", active_store)
        os.replace(temp_manifest, active_manifest)
        return {"rebuilt": True, "record_count": len(store.records), "manifest": manifest,
                "report": report, "backup": str(active_dir / "word_store.previous.json")}
    except Exception as exc:
        return {"rebuilt": False, "error": str(exc), "preserved_prior": active_store.exists()}
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
