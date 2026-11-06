"""Local, auditable registry for Slade Puzzles cover backgrounds.

The registry is intentionally separate from the legacy manifest.  The legacy
file remains readable for compatibility, while this registry is the sole
authority for automatic production selection.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageStat


ROOT = Path(__file__).resolve().parents[1]
COVER_ASSETS = ROOT / "cover_assets"
REGISTRY_FILE = COVER_ASSETS / "generated_background_index.json"
QUEUE_FILE = COVER_ASSETS / "background_generation_queue.json"
LEGACY_LIBRARY_FILE = COVER_ASSETS / "background_photo_library.json"
# Classification is only one part of the production gate.  A file is never
# selectable merely because it happens to live in a cover-assets folder.
APPROVED_PROVENANCE = {"APPROVED_CHATGPT_GENERATED", "APPROVED_PROJECT_GENERATED", "APPROVED_CLOUDFLARE_GENERATED", "APPROVED_GEMINI_GENERATED"}
APPROVED_PHOTO_CLASSIFICATIONS = {"APPROVED_PROJECT_PHOTO", "APPROVED_LOCAL_PHOTO"}
APPROVED_PROJECT_PROVIDERS = {
    "chatgpt project generation",
    "cloudflare workers ai",
    "gemini api",
    "sladepuzzleco project generation",
}


def retired_from_new_production(row: dict | None) -> bool:
    """Retirement preserves history while excluding an asset from new work."""
    if not row:
        return False
    lifecycle = str(row.get("lifecycle_state") or "").strip().casefold().replace(" ", "_")
    return row.get("retired_from_new_production") is True or lifecycle in {"retired", "archived", "obsolete"}


def hash_distance(left: str, right: str) -> int:
    """Hamming distance for the existing 64-bit perceptual hashes."""
    try:
        return (int(left, 16) ^ int(right, 16)).bit_count()
    except (TypeError, ValueError):
        return 64


class CoverAssetApprovalError(ValueError):
    """Raised whenever production art lacks current, explicit approval."""


def approval_state(row: dict | None) -> str:
    """Return one authoritative state while preserving explicit legacy approvals."""
    if not row:
        return "missing"
    state = str(row.get("approval_state") or "").strip().casefold().replace(" ", "_")
    if state in {"approved", "approved_for_production"}:
        return "approved"
    if state in {"awaiting_review", "pending", "generated_awaiting_review"}:
        return "awaiting_review"
    if state == "rejected":
        return "rejected"
    # The pre-enforcement registry already stored an explicit approval bit.
    # Keep those reviewed rows usable; never infer approval from a directory.
    if not state and row.get("production_approved") is True:
        return "approved"
    return "unknown"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temp, path)


def _safe_read(path: Path, default: dict) -> dict:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8-sig"))
        return parsed if isinstance(parsed, dict) else default
    except (OSError, json.JSONDecodeError):
        return default


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def perceptual_hash(path: Path) -> str:
    """Small dependency-free difference hash used only as a duplicate signal."""
    with Image.open(path) as image:
        gray = image.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
        # Pillow 14 deprecates getdata(); get_flattened_data keeps this
        # lightweight duplicate check forward-compatible.
        pixels = list(gray.get_flattened_data())
    bits = "".join("1" if pixels[row * 9 + col] > pixels[row * 9 + col + 1] else "0" for row in range(8) for col in range(8))
    return f"{int(bits, 2):016x}"


def image_health(path: Path) -> tuple[bool, dict]:
    """Validate a real image without claiming to semantically judge artwork."""
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            rgb = image.convert("RGB")
            width, height = rgb.size
            variance = sum(ImageStat.Stat(rgb.resize((64, 64))).var) / 3.0
        return width >= 768 and height >= 768 and variance >= 5.0, {"width": width, "height": height, "variance": round(variance, 2)}
    except Exception as exc:
        return False, {"error": f"Unreadable image: {type(exc).__name__}"}


class BackgroundAssetIndex:
    """Reads, audits, selects, and records use of approved backgrounds."""

    def __init__(self, registry_file: Path | None = None) -> None:
        self.registry_file = Path(registry_file or os.environ.get("SLADE_COVER_ASSET_REGISTRY") or REGISTRY_FILE)

    def payload(self) -> dict:
        return _safe_read(self.registry_file, {"schema_version": 1, "created_at": utc_now(), "assets": [], "audit_notes": []})

    def save(self, payload: dict) -> None:
        payload["updated_at"] = utc_now()
        _atomic_write(self.registry_file, payload)

    def assets(self) -> list[dict]:
        return [row for row in self.payload().get("assets", []) if isinstance(row, dict)]

    def ensure_provenance_audited(self) -> None:
        """Upgrade legacy manifest records once before production selection.

        Older registry rows predate the explicit ``project_generated`` field.
        Re-running the existing manifest audit is safe: it preserves files and
        usage history while adding the missing provenance evidence.
        """
        rows = self.assets()
        if self.registry_file.resolve() == REGISTRY_FILE.resolve() and (not rows or any("project_generated" not in row for row in rows)):
            self.audit_legacy_library()
            rows = self.assets()
        if self.registry_file.resolve() == REGISTRY_FILE.resolve() and any(not row.get("visual_family_id") for row in rows):
            self.refresh_derived_metadata()

    def refresh_derived_metadata(self) -> dict[str, int]:
        """Safely rebuild evidence-derived discovery fields only.

        Approval, provenance, files, and use history are never changed. The
        refresh is restart-persistent and can be run repeatedly.
        """
        payload = self.payload(); rows = [row for row in payload.get("assets", []) if isinstance(row, dict)]
        refreshed = []
        for row in rows:
            candidate = ROOT / str(row.get("path") or "")
            copy = dict(row)
            if candidate.is_file() and not copy.get("perceptual_hash"):
                try: copy["perceptual_hash"] = perceptual_hash(candidate)
                except OSError: pass
            health = copy.get("health") if isinstance(copy.get("health"), dict) else {}
            width, height = int(health.get("width") or 0), int(health.get("height") or 0)
            if width and height and not copy.get("orientation"):
                copy["orientation"] = "portrait" if height > width else "landscape" if width > height else "square"
            if not copy.get("source_type") and copy.get("project_generated") is True:
                copy["source_type"] = "generated_art"
            if not copy.get("lifecycle_state"):
                copy["lifecycle_state"] = "active" if not retired_from_new_production(copy) else "retired"
            refreshed.append(copy)
        annotated = self._with_visual_families(refreshed)
        changed = 0
        by_id = {str(row.get("asset_id") or ""): row for row in annotated}
        for row in rows:
            derived = by_id.get(str(row.get("asset_id") or ""), {})
            for key in ("perceptual_hash", "visual_family_id", "orientation", "source_type", "lifecycle_state"):
                if derived.get(key) and row.get(key) != derived.get(key):
                    row[key] = derived[key]; changed += 1
        if changed:
            payload["assets"] = rows
            payload.setdefault("audit_notes", []).append({"at": utc_now(), "action": "safe_discovery_metadata_refresh", "fields_changed": changed,
                "policy": "Only image-derived discovery metadata changed; approvals, provenance, files, and usage were preserved."})
            self.save(payload)
        return {"assets": len(rows), "fields_changed": changed}

    @staticmethod
    def production_selectable(row: dict) -> bool:
        """Return whether an asset has complete, explicit production provenance.

        This intentionally fails closed.  File location, a friendly filename,
        or a legacy library entry can never substitute for an explicit record.
        """
        provenance = row.get("provenance") or {}
        provider = str(provenance.get("provider") or "").casefold()
        generated = (
            row.get("project_generated") is True
            and str(row.get("classification") or "") in APPROVED_PROVENANCE
            and provider in APPROVED_PROJECT_PROVIDERS
        )
        approved_photo = (
            str(row.get("classification") or "") in APPROVED_PHOTO_CLASSIFICATIONS
            and row.get("rights_verified") is True
            and str(row.get("source_type") or "").casefold() in {"approved_photo", "licensed_photo", "owned_photo"}
            and bool(str(provenance.get("rights_basis") or "").strip())
        )
        return (
            not retired_from_new_production(row)
            and
            approval_state(row) == "approved"
            and
            row.get("production_approved") is True
            and (generated or approved_photo)
        )

    @staticmethod
    def active_usage(row: dict) -> list[dict]:
        """Count distinct current books, not abandoned rebuild attempts."""
        distinct: dict[tuple[str, str], dict] = {}
        for use in row.get("usage") or []:
            if not isinstance(use, dict):
                continue
            package = str(use.get("package") or "").strip()
            if package and not Path(package).is_dir():
                continue
            title = str(use.get("title") or "").strip().casefold()
            theme = str(use.get("theme") or "").strip().casefold()
            key = (title or package.casefold(), theme)
            if key[0]:
                distinct[key] = use
        return list(distinct.values())

    @staticmethod
    def _with_visual_families(rows: list[dict]) -> list[dict]:
        """Annotate candidates without mutating approval records.

        Explicit reviewed families win. Otherwise the already-recorded dHash
        groups close crops/recolors locally; missing hashes fail back to the
        stable asset identity rather than merging unrelated art.
        """
        representatives: list[tuple[str, str]] = []
        output = []
        for row in rows:
            family = str(row.get("visual_family_id") or "").strip()
            phash = str(row.get("perceptual_hash") or "").strip().casefold()
            if not family and phash:
                family = next((name for name, value in representatives if hash_distance(phash, value) <= 6), "")
                if not family:
                    family = "vf_" + phash
                    representatives.append((family, phash))
            if not family:
                family = "vf_asset_" + str(row.get("asset_id") or hashlib.sha1(str(row.get("path") or "").encode()).hexdigest()[:12])
            output.append({**row, "visual_family_id": family})
        return output

    def asset_record_for_path(self, path: Path | str | None) -> dict | None:
        """Resolve a raw path to its registry row without implying eligibility."""
        if not path:
            return None
        target = Path(path)
        if not target.is_absolute():
            target = ROOT / target
        try:
            resolved = target.resolve()
        except OSError:
            return None
        for row in self.assets():
            candidate = ROOT / str(row.get("path") or "")
            try:
                if candidate.resolve() == resolved:
                    return row
            except OSError:
                continue
        return None

    def eligibility(self, path: Path | str | None) -> tuple[bool, str, dict | None]:
        """Fail-closed production decision including file-fingerprint freshness."""
        row = self.asset_record_for_path(path)
        if not row:
            return False, "unknown or unregistered cover asset", None
        state = approval_state(row)
        if state != "approved":
            return False, f"cover asset is {state.replace('_', ' ')}", row
        if not self.production_selectable(row):
            return False, "cover approval record lacks required project provenance", row
        candidate = ROOT / str(row.get("path") or "")
        if not candidate.is_file():
            return False, "approved cover asset file is missing", row
        recorded = str(row.get("sha256") or "").strip().casefold()
        if not recorded:
            return False, "cover approval record has no file fingerprint", row
        try:
            current = file_sha256(candidate).casefold()
        except OSError:
            return False, "approved cover asset cannot be read", row
        if current != recorded:
            return False, "cover asset changed after approval", row
        return True, "approved for production", row

    @staticmethod
    def cover_brief(data: dict) -> dict:
        """Create the small common cover brief used by every selector."""
        topic = str(data.get("detected_topic") or data.get("topic") or data.get("theme") or "").strip()
        title = str(data.get("title") or "").strip()
        subtitle = str(data.get("subtitle") or "").strip()
        series = str(data.get("series") or "").strip()
        puzzle_type = str(data.get("puzzle_type") or data.get("format_label") or "Word Search").strip()
        audience = str(data.get("audience") or "general").strip().casefold()
        text = " ".join(value for value in (topic, title, subtitle, series, puzzle_type) if value)
        topic_tokens = {token for token in re.findall(r"[a-z0-9]+", topic.casefold()) if len(token) > 2}
        tokens = {token for token in text.casefold().replace("&", " ").replace("/", " ").split() if len(token) > 2}
        # Light plural normalisation improves deterministic matching of
        # pairs such as "Outdoors" -> "outdoor" without a heavy NLP layer.
        topic_tokens |= {token[:-1] for token in topic_tokens if token.endswith("s") and len(token) > 4}
        tokens |= {token[:-1] for token in tokens if token.endswith("s") and len(token) > 4}
        if puzzle_type.casefold() == "mixed brain games":
            # A general mixed-games cover may use only a genuine puzzle-art
            # family; it must never fall through to an unrelated niche scene.
            tokens |= {"mixed", "brain", "games", "sudoku", "cryptogram", "scramble", "trivia", "logic", "cipher", "puzzle"}
        return {"topic": topic, "title": title, "puzzle_type": puzzle_type, "audience": audience, "tokens": tokens, "topic_tokens": topic_tokens}

    @staticmethod
    def _topic_score(row: dict, brief: dict) -> int:
        tags = {str(item).casefold() for item in row.get("topics", []) if str(item).strip()}
        tag_tokens = {token for tag in tags for token in re.findall(r"[a-z0-9]+", tag) if len(token) > 2}
        tag_tokens |= {token[:-1] for token in tag_tokens if token.endswith("s") and len(token) > 4}
        tokens = set(brief.get("tokens") or ())
        topic = str(brief.get("topic") or "").casefold()
        name = str(row.get("name") or "").casefold()
        exact = topic and (topic in tags or topic == name)
        topic_overlap = len(set(brief.get("topic_tokens") or ()) & tag_tokens)
        context_overlap = len(tokens & tag_tokens) - topic_overlap
        audience = str(row.get("audience") or "general").casefold()
        audience_bonus = 3 if audience in {"", "general", str(brief.get("audience") or "general")} else 0
        # Exact topic evidence is deliberately dominant; clean empty space
        # and palette are secondary once relevance has been established.
        is_generic_topic = topic in {"", "general starter", "general knowledge & curiosity"}
        context_weight = 12 if is_generic_topic else 5
        score = (100 if exact else 0) + topic_overlap * 30 + max(0, context_overlap) * context_weight + audience_bonus
        # A broad pets image can be useful for a general pet collection, but
        # it must not outrank species-specific artwork for a dog- or cat-led
        # title. This also protects future routes that share one broad theme.
        wants_dog = bool(tokens & {"dog", "dogs", "canine", "puppy"})
        wants_cat = bool(tokens & {"cat", "cats", "feline", "kitten"})
        has_dog = bool(tag_tokens & {"dog", "dogs", "canine", "puppy"})
        has_cat = bool(tag_tokens & {"cat", "cats", "feline", "kitten"})
        if wants_dog and not wants_cat and has_cat:
            score -= 50
        if wants_cat and not wants_dog and has_dog:
            score -= 50
        # A road landscape alone is weaker evidence than the named vehicle
        # subject in a classic-car book, even when both mention travel.
        vehicles = {"car", "cars", "vehicle", "vehicles", "automotive", "truck", "trucks", "automobile", "automobiles"}
        if tokens & vehicles and not tag_tokens & vehicles:
            score -= 60
        risque_request = bool(tokens & {"naughty","kinky","swear","swearing","cuss","cussing","profanity","raunchy","risque"}) or {"sex","toys"}.issubset(tokens)
        adult_visuals = {"naughty","kinky","swear","swearing","profanity","risque","raunchy","cocktail","cocktails","bar","nightlife","afterhours","lingerie","boudoir","masquerade"}
        if risque_request and not tag_tokens & adult_visuals:
            score -= 100  # An "adult" audience tag alone is not a matching theme.
        return score

    def production_choices(self, data: dict, limit: int | None = None) -> list[dict]:
        """Return only meaningfully matched, approved project backgrounds.

        There is deliberately no unrelated visual fallback.  Callers can show
        a clear "background needed" state when this returns no candidates.
        """
        self.ensure_provenance_audited()
        brief = self.cover_brief(data)
        scored: list[tuple[int, int, dict]] = []
        for row in self.assets():
            # A finished, owner-approved cover is valid for wrap reuse, not a background for new titles.
            if row.get("asset_role") == "finished_front_cover":
                continue
            if not self.production_selectable(row):
                continue
            if not (ROOT / str(row.get("path") or "")).is_file():
                continue
            relevance = self._topic_score(row, brief)
            if relevance < 12:
                continue
            recent_uses = len(self.active_usage(row))
            score = relevance - min(recent_uses, 10) * 3
            scored.append((score, relevance, row))
        scored.sort(key=lambda item: (-item[0], -item[1], str(item[2].get("name", "")).casefold()))
        rows = [{**row, "match_score": score, "topic_match_score": relevance, "file": row["path"],
                 "times_used_total": len(self.active_usage(row)),
                 "times_used_same_topic": sum(str(use.get("theme") or "").casefold() == str(brief.get("topic") or "").casefold() for use in self.active_usage(row)),
                 "times_used_same_puzzle_type": sum(str(brief.get("puzzle_type") or "").casefold() in str(use.get("title") or "").casefold() for use in self.active_usage(row))}
                for score, relevance, row in scored]
        rows = self._with_visual_families(rows)
        return rows if limit is None else rows[:limit]

    def gallery_choices(self, data: dict, slots: int = 6, refresh_offset: int = 0) -> dict:
        """Choose artwork families before templates are assigned.

        Reuse occurs only after every suitable family and distinct asset has
        been offered. This method is read-only and never invokes generation.
        """
        if slots < 1:
            raise ValueError("Gallery slots must be positive.")
        candidates = self.production_choices(data)
        family_buckets: dict[str, list[dict]] = {}
        for row in candidates:
            family_buckets.setdefault(str(row["visual_family_id"]), []).append(row)
        families = list(family_buckets)
        if families and refresh_offset:
            shift = refresh_offset % len(families)
            families = families[shift:] + families[:shift]
        selected: list[dict] = []
        # First pass: one best artwork from each visual family.
        for family in families:
            selected.append(family_buckets[family][0])
            if len(selected) == slots:
                break
        # Second pass: other genuinely distinct files before any repeat.
        chosen_ids = {str(row.get("asset_id") or "") for row in selected}
        for row in candidates:
            if len(selected) == slots:
                break
            if str(row.get("asset_id") or "") not in chosen_ids:
                selected.append(row); chosen_ids.add(str(row.get("asset_id") or ""))
        # Do not fill empty cards by repeating the same file.  Repetition made
        # sense when every slot also had a different template, but this is now
        # a truthful artwork chooser: one image equals one option.
        asset_ids = [str(row.get("asset_id") or "") for row in selected]
        shown_families = [str(row.get("visual_family_id") or "") for row in selected]
        return {
            "candidates": candidates, "selected": selected,
            "metrics": {
                "eligible_asset_count": len(candidates),
                "eligible_visual_family_count": len(family_buckets),
                "requested_slot_count": slots,
                "gallery_slot_count": len(selected),
                "distinct_art_assets_shown": len(set(asset_ids)),
                "distinct_visual_families_shown": len(set(shown_families)),
                "duplicate_asset_count": len(asset_ids) - len(set(asset_ids)),
                "duplicate_visual_family_count": len(shown_families) - len(set(shown_families)),
                "retired_asset_count_shown": sum(retired_from_new_production(row) for row in selected),
                "unapproved_asset_count_shown": sum(not self.production_selectable(row) for row in selected),
                "diversity_limited": len(family_buckets) < min(4, slots),
            },
        }

    @staticmethod
    def _asset_id(path: Path) -> str:
        return "bg_" + hashlib.sha1(str(path).casefold().encode("utf-8")).hexdigest()[:16]

    def audit_legacy_library(self) -> dict[str, int]:
        """Index legacy library files; retain all files and quarantine unknowns."""
        legacy = _safe_read(LEGACY_LIBRARY_FILE, {"items": []})
        known: dict[str, dict] = {}
        for item in legacy.get("items", []):
            if not isinstance(item, dict):
                continue
            for raw in item.get("files") or [item.get("file")]:
                if raw:
                    known[str(raw).replace("/", "\\").casefold()] = item
        payload = self.payload()
        prior = {str(row.get("path", "")).replace("/", "\\").casefold(): row for row in payload.get("assets", []) if isinstance(row, dict)}
        stats = {"approved": 0, "quarantined": 0, "invalid": 0, "unchanged": 0}
        observed: list[dict] = []
        for path in sorted((COVER_ASSETS / "background_photos").glob("*")):
            if not path.is_file():
                continue
            relative = str(path.relative_to(ROOT)).replace("/", "\\")
            item = known.get(relative.casefold())
            valid, health = image_health(path)
            if not valid:
                classification, approved = "UNKNOWN_PROVENANCE", False; stats["invalid"] += 1
            elif item:
                classification, approved = "APPROVED_CHATGPT_GENERATED", True; stats["approved"] += 1
            else:
                classification, approved = "UNKNOWN_PROVENANCE", False; stats["quarantined"] += 1
            existing = prior.get(relative.casefold(), {})
            observed.append({**existing, "asset_id": existing.get("asset_id") or self._asset_id(path), "path": relative,
                "name": str(item.get("name")) if item else path.stem.replace("_", " ").title(), "topics": list(item.get("match_terms", [])) if item else [],
                "palette": str(item.get("palette") or "") if item else "", "focus": str(item.get("focus") or "center") if item else "center",
                "classification": classification, "production_approved": approved,
                # The historical manifest is an explicit Slade Puzzles
                # generated-art record, not a filename-only guess.  Unknown
                # files remain quarantined even when placed beside it.
                "project_generated": bool(item), "health": health, "sha256": file_sha256(path),
                "perceptual_hash": perceptual_hash(path) if valid else "", "visual_family_id": existing.get("visual_family_id") or ("vf_" + perceptual_hash(path) if valid else ""),
                "source_type": existing.get("source_type") or ("generated_art" if item else "unknown"),
                "orientation": existing.get("orientation") or ("portrait" if int(health.get("height") or 0) > int(health.get("width") or 0) else "landscape" if int(health.get("width") or 0) > int(health.get("height") or 0) else "square"),
                "lifecycle_state": existing.get("lifecycle_state") or "active", "provenance": existing.get("provenance") or {
                    "provider": "ChatGPT project generation" if item else "unknown", "basis": "Existing Slade Puzzles AI background library manifest" if item else "Not listed in project background manifest", "audited_at": utc_now()},
                "usage": existing.get("usage", []), "created_at": existing.get("created_at") or utc_now(), "updated_at": utc_now()})
        observed_paths = {row["path"].casefold() for row in observed}
        # Never preserve a vanished file as an active approved choice.  This
        # was the route by which deleted cover art could remain selectable
        # after a later legacy audit.  Keep its history, but fail it closed.
        for row in payload.get("assets", []):
            if not isinstance(row, dict) or str(row.get("path", "")).casefold() in observed_paths:
                continue
            observed.append({**row, "lifecycle_state": "retired", "retired_from_new_production": True,
                             "production_approved": False, "missing_from_disk": True,
                             "updated_at": utc_now()})
        payload["assets"] = observed
        payload.setdefault("audit_notes", []).append({"at": utc_now(), "action": "legacy_manifest_audit", "summary": stats,
            "policy": "Unknown or invalid assets remain on disk but are excluded from automatic production selection."})
        self.save(payload)
        return stats

    def approved_choices(self, text: str, limit: int | None = None) -> list[dict]:
        return self.production_choices({"topic": text, "title": text}, limit)

    def record_use(self, path: Path, *, title: str, theme: str, package: str = "") -> None:
        target = str(path.resolve()).casefold(); payload = self.payload()
        for row in payload.get("assets", []):
            candidate = ROOT / str(row.get("path") or "")
            if candidate.exists() and str(candidate.resolve()).casefold() == target:
                row.setdefault("usage", []).append({"at": utc_now(), "title": title, "theme": theme, "package": package})
                row["updated_at"] = utc_now(); self.save(payload); return

    def ledger_details(self, path: Path | None) -> dict | None:
        if not path: return None
        if not self.assets(): self.audit_legacy_library()
        allowed, _reason, row = self.eligibility(path)
        return row if allowed else None


def require_production_approved_cover_asset(path: Path | str | None, *, index: BackgroundAssetIndex | None = None) -> dict:
    """Lowest shared fail-closed check for every production cover route."""
    active = index or BackgroundAssetIndex()
    active.ensure_provenance_audited()
    allowed, reason, row = active.eligibility(path)
    if not allowed:
        raise CoverAssetApprovalError(
            "COVER ART REQUIRED â€” production stopped because the selected background is " + reason +
            ". Choose an approved asset or review pending artwork."
        )
    return row or {}


def cover_approval_proof_path(front_cover: Path | str) -> Path:
    return Path(front_cover).with_name(Path(front_cover).stem + ".approval.json")


def write_cover_approval_proof(front_cover: Path | str, asset: dict) -> Path:
    front = Path(front_cover)
    proof = cover_approval_proof_path(front)
    payload = {
        "schema_version": 1, "approval_state": "approved", "asset_id": asset.get("asset_id", ""),
        "asset_path": asset.get("path", ""), "asset_sha256": asset.get("sha256", ""),
        "approval_revision": asset.get("approval_revision") or asset.get("updated_at") or asset.get("created_at") or "legacy-explicit",
        "provenance": asset.get("provenance") or {}, "front_cover_sha256": file_sha256(front),
        "rendered_at": utc_now(),
    }
    _atomic_write(proof, payload)
    return proof


def verify_rendered_cover_approval(front_cover: Path | str, *, index: BackgroundAssetIndex | None = None) -> tuple[bool, str, dict]:
    """Verify that a rendered cover and its approved source have not changed."""
    front = Path(front_cover); proof = cover_approval_proof_path(front)
    data = _safe_read(proof, {})
    if not data:
        return False, "cover approval proof is missing", {}
    if not front.is_file() or str(data.get("front_cover_sha256") or "") != file_sha256(front):
        return False, "rendered front cover changed after approval proof", data
    try:
        asset = require_production_approved_cover_asset(data.get("asset_path"), index=index)
    except CoverAssetApprovalError as exc:
        return False, str(exc), data
    if str(asset.get("asset_id") or "") != str(data.get("asset_id") or "") or str(asset.get("sha256") or "") != str(data.get("asset_sha256") or ""):
        return False, "cover approval proof is stale against the approved asset record", data
    return True, "cover and approved asset fingerprints are current", data


def approved_background_choices(text: str, limit: int | None = None) -> list[dict]:
    return BackgroundAssetIndex().approved_choices(text, limit)
