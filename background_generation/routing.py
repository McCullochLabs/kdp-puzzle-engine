"""Small shared adapter from book-creation routes to approved cover assets.

This module owns no artwork and renders nothing.  It normalizes route metadata,
reads optional style/palette memory, and delegates eligibility/ranking to the
authoritative BackgroundAssetIndex.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .index import BackgroundAssetIndex, ROOT, approval_state


@dataclass(frozen=True)
class CoverRequest:
    route: str
    title: str
    subtitle: str = ""
    author: str = ""
    puzzle_type: str = "Word Search"
    topic: str = ""
    audience: str = "general"
    edition: str = ""
    series: str = ""
    style: str = ""
    palette: str = ""
    book_id: str = ""
    theme_path: str = ""
    preferred_asset: str = ""
    generation_allowed: bool = False
    selection_seed: int = 0

    def selection_data(self) -> dict[str, str]:
        return {
            "title": self.title, "subtitle": self.subtitle,
            "detected_topic": self.topic, "topic": self.topic,
            "series": self.series, "puzzle_type": self.puzzle_type,
            "audience": self.audience,
        }


@dataclass
class CoverDecision:
    request: CoverRequest
    asset: dict[str, Any] | None
    candidates: list[dict[str, Any]] = field(default_factory=list)
    style: str = ""
    palette: str = ""
    fallback_reason: str = ""

    @property
    def selected_path(self) -> str:
        return str((self.asset or {}).get("path") or "")

    def diagnostics(self) -> dict[str, Any]:
        asset = self.asset or {}
        provenance = asset.get("provenance") or {}
        return {
            "creation_route": self.request.route,
            "cover_pipeline": "Shared Modern",
            "asset_candidates": len(self.candidates),
            "candidate_sources": sorted({_source_type(row) for row in self.candidates}),
            "selected_asset": asset.get("asset_id", ""),
            "selected_path": asset.get("path", ""),
            "source": _source_type(asset) if asset else "None",
            "provider": provenance.get("provider", ""),
            "approval_state": asset.get("approval_state") or ("approved" if asset.get("production_approved") else "missing"),
            "fallback_reason": self.fallback_reason or "No",
            "generation_requested": False,
        }


@dataclass
class CoverGalleryConcept:
    slot: int
    art_asset_id: str
    cover_template_id: str
    asset: dict[str, Any]
    palette: str
    reason: str

    def diagnostics(self) -> dict[str, Any]:
        return {
            "cover_slot": self.slot, "art_asset_id": self.art_asset_id,
            "cover_template_id": self.cover_template_id,
            "source_path": self.asset.get("path", ""),
            "visual_family_id": self.asset.get("visual_family_id", ""),
            "source_type": _source_type(self.asset),
            "approval_state": approval_state(self.asset),
            "topic_score": self.asset.get("topic_match_score", 0),
            "final_score": self.asset.get("match_score", 0),
            "times_used_total": self.asset.get("times_used_total", 0),
            "reason_selected": self.reason,
        }


@dataclass
class CoverGalleryDecision:
    request: CoverRequest
    concepts: list[CoverGalleryConcept]
    candidates: list[dict[str, Any]]
    metrics: dict[str, Any]

    def diagnostics(self) -> dict[str, Any]:
        return {"creation_route": self.request.route, "metrics": dict(self.metrics),
                "concepts": [item.diagnostics() for item in self.concepts],
                "candidate_count": len(self.candidates), "generation_requested": False}


def _source_type(row: dict[str, Any]) -> str:
    if not row:
        return "None"
    if row.get("project_generated") is True:
        return "Approved Generated"
    if str(row.get("source_type") or "").casefold() in {"approved_photo", "licensed_photo", "owned_photo"}:
        return "Approved Photo"
    return "Approved Asset"


def _template_sequence(puzzle_type: str) -> tuple[str, ...]:
    # This is an *artwork* gallery, not a layout gallery.  Previously each
    # card was assigned a different template even though only ``photo``
    # renders the selected asset.  The thumbnail label therefore claimed to
    # show one picture while minimal/bold/etc. silently discarded it.  Keep
    # every gallery concept image-led; layout is chosen separately in the
    # design controls.
    return ("photo",)


def select_cover_gallery(request: CoverRequest, *, slots: int = 6,
                         refresh_offset: int = 0,
                         index: BackgroundAssetIndex | None = None) -> CoverGalleryDecision:
    """Build diverse approved art concepts; never calls an image provider."""
    active = index or BackgroundAssetIndex()
    selection = active.gallery_choices(request.selection_data(), slots, refresh_offset)
    templates = _template_sequence(request.puzzle_type)
    concepts = []
    for slot, asset in enumerate(selection["selected"], 1):
        template = templates[(slot - 1 + refresh_offset) % len(templates)]
        palette = request.palette or str(asset.get("palette") or "midnight-gold")
        reason = "highest remaining relevant visual family" if slot <= selection["metrics"]["eligible_visual_family_count"] else "reused only because suitable approved visual-family inventory is limited"
        concepts.append(CoverGalleryConcept(slot, str(asset.get("asset_id") or ""), template, asset, palette, reason))
    return CoverGalleryDecision(request, concepts, selection["candidates"], selection["metrics"])


def _safe_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _stored_theme_path(path: str) -> str:
    if not path:
        return ""
    candidate = Path(path)
    try:
        # Match the native Windows key format already used by
        # word_search_creator._stored_theme_path and cover_preferences.json.
        return str(candidate.resolve().relative_to(ROOT.resolve()))
    except (OSError, ValueError):
        return str(candidate)


def remembered_direction(request: CoverRequest) -> dict[str, str]:
    """Read shared direction without turning old image memory into a permanent lock."""
    result: dict[str, str] = {}
    preferences = _safe_json(ROOT / "cover_preferences.json")
    saved = preferences.get(_stored_theme_path(request.theme_path), {}) if request.theme_path else {}
    if isinstance(saved, dict):
        for key in ("style", "palette", "art", "art_focus"):
            if saved.get(key):
                result[key] = str(saved[key])
    memory = _safe_json(ROOT / "niche_cover_memory.json")
    for identity in (request.series, request.topic):
        remembered = memory.get(identity, {}) if identity else {}
        if isinstance(remembered, dict):
            for key in ("style", "palette"):
                if remembered.get(key) and key not in result:
                    result[key] = str(remembered[key])
            if remembered:
                break
    return result


def select_cover_asset(request: CoverRequest, *, index: BackgroundAssetIndex | None = None) -> CoverDecision:
    """Choose the strongest existing approved asset; never makes an online call."""
    active = index or BackgroundAssetIndex()
    memory = remembered_direction(request)
    candidates = active.production_choices(request.selection_data())
    preferred = request.preferred_asset or memory.get("art", "")
    selected = None
    if preferred:
        preferred_row = active.asset_record_for_path(preferred)
        allowed, _reason, _row = active.eligibility(preferred)
        candidate_ids = {str(row.get("asset_id") or "") for row in candidates}
        if allowed and preferred_row and str(preferred_row.get("asset_id") or "") in candidate_ids:
            selected = next(row for row in candidates if row.get("asset_id") == preferred_row.get("asset_id"))
    if selected is None and candidates:
        strongest = max(int(row.get("match_score") or 0) for row in candidates)
        finalists = [row for row in candidates if int(row.get("match_score") or 0) == strongest]
        selected = finalists[request.selection_seed % len(finalists)]
    style = request.style or memory.get("style", "")
    palette = request.palette or memory.get("palette", "")
    if selected and selected.get("palette") and not request.palette and not memory.get("palette"):
        palette = str(selected["palette"])
    reason = ""
    if not selected:
        reason = "no strong topic-matched approved asset"
        if request.generation_allowed:
            reason += "; operator may explicitly request generation"
    elif preferred and str(selected.get("path") or "") != preferred:
        reason = "saved asset was stale, ineligible, or not relevant; strongest approved match used"
    return CoverDecision(request, selected, candidates, style, palette, reason)


def write_routing_diagnostics(path: Path, decision: CoverDecision) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(decision.diagnostics(), indent=2) + "\n", encoding="utf-8")
    return path


def request_from_mapping(route: str, data: dict[str, Any], **overrides: Any) -> CoverRequest:
    values = {
        "route": route,
        "book_id": str(data.get("book_id") or ""),
        "title": str(data.get("title") or ""),
        "subtitle": str(data.get("subtitle") or ""),
        "author": str(data.get("author") or ""),
        "puzzle_type": str(data.get("puzzle_type") or "Word Search"),
        "topic": str(data.get("detected_topic") or data.get("topic") or data.get("theme") or ""),
        "audience": str(data.get("audience") or "general"),
        "edition": str(data.get("edition") or ("Signature Edition" if data.get("signature_edition") else "")),
        "series": str(data.get("series") or ""),
        "style": str(data.get("cover_style") or ""),
        "palette": str(data.get("palette") or ""),
        "theme_path": str(data.get("theme_path") or ""),
        "preferred_asset": str(data.get("cover_art_path") or ""),
        "generation_allowed": False,
        "selection_seed": 0,
    }
    values.update(overrides)
    return CoverRequest(**values)
