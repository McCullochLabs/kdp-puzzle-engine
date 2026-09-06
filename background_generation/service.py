"""Prompt, queue, validation, and approval workflow for cover backgrounds."""
from __future__ import annotations
import hashlib, json, random, re
from dataclasses import dataclass
from pathlib import Path
from .index import COVER_ASSETS, QUEUE_FILE, BackgroundAssetIndex, file_sha256, image_health, perceptual_hash, utc_now
from .providers import CloudflareWorkersAIProvider, ProviderError
GENERATED_DIR = COVER_ASSETS / "generated_backgrounds"
def _tokens(text: str) -> set[str]: return {word for word in re.findall(r"[a-z0-9]+", text.casefold()) if len(word) > 2}
def build_prompt(topic: str, *, palette: str = "", composition: str = "center", adult: bool = False, variation: int = 0) -> str:
    styles = ["cinematic editorial illustration", "polished dimensional paper-cut scene", "rich contemporary editorial art", "textured graphic-novel illustration", "warm premium gouache artwork", "bold refined vector-style illustration"]
    palette_line = f"Palette direction: {palette}. " if palette else ""
    audience = "for adults, tasteful and non-explicit" if adult else "welcoming for a general puzzle-book audience"
    return (f"Original {styles[variation % len(styles)]} for a SladePuzzleCo puzzle-book cover about {topic}. {palette_line}{audience}. "
        "Central open space for title and badge. Strong but uncluttered subject matter directly related to the topic; portrait-friendly composition, "
        "print-ready visual hierarchy, no words, no letters, no numbers, no logos, no watermarks, no book covers, no puzzle grids, no brand marks, no copyrighted characters.")
def _hamming_hex(left: str, right: str) -> int:
    try: return (int(left, 16) ^ int(right, 16)).bit_count()
    except ValueError: return 64
@dataclass
class GenerationResult: status: str; message: str; asset: dict | None = None
class BackgroundGenerationService:
    def __init__(self, index=None, provider=None): self.index, self.provider = index or BackgroundAssetIndex(), provider or CloudflareWorkersAIProvider()
    def enqueue(self, *, topic: str, palette: str = "", adult: bool = False, quantity: int = 1) -> list[dict]:
        queue = self._load_queue(); jobs = []
        for number in range(max(1, min(int(quantity), 12))):
            seed = random.SystemRandom().randint(1, 2**31 - 1); job = {"job_id": hashlib.sha1(f"{topic}|{seed}".encode()).hexdigest()[:16], "topic": topic, "palette": palette, "adult": bool(adult), "seed": seed, "variation": number, "status": "QUEUED", "attempts": 0, "created_at": utc_now(), "updated_at": utc_now()}
            queue["jobs"].append(job); jobs.append(job)
        self._save_queue(queue); return jobs
    def process_next(self) -> GenerationResult:
        queue = self._load_queue(); job = next((row for row in queue["jobs"] if row.get("status") in {"QUEUED", "RETRY"}), None)
        if not job: return GenerationResult("IDLE", "There are no background requests waiting.")
        job.update(status="GENERATING", attempts=int(job.get("attempts", 0)) + 1, updated_at=utc_now()); self._save_queue(queue)
        prompt = build_prompt(str(job["topic"]), palette=str(job.get("palette") or ""), adult=bool(job.get("adult")), variation=int(job.get("variation", 0)))
        try: raw = self.provider.generate(prompt)
        except ProviderError as exc:
            job.update(status="PAUSED", last_error=str(exc), updated_at=utc_now()); self._save_queue(queue); return GenerationResult("PAUSED", str(exc))
        candidate = GENERATED_DIR / "candidates" / f"{job['job_id']}.png"; candidate.parent.mkdir(parents=True, exist_ok=True); candidate.write_bytes(raw)
        valid, health = image_health(candidate)
        if not valid:
            job.update(status="REJECTED", last_error="Generated file failed image quality checks.", updated_at=utc_now()); self._save_queue(queue); return GenerationResult("REJECTED", "The generated background was rejected by image quality checks.")
        sha, phash = file_sha256(candidate), perceptual_hash(candidate)
        duplicate = next((row for row in self.index.assets() if row.get("sha256") == sha or _hamming_hex(str(row.get("perceptual_hash", "")), phash) <= 6), None)
        if duplicate:
            job.update(status="REJECTED", last_error="Too similar to an existing approved or reviewed asset.", updated_at=utc_now()); self._save_queue(queue); return GenerationResult("REJECTED", "The generated background was too close to an existing image, so it was not added.")
        relative = str(candidate.relative_to(Path(__file__).resolve().parents[1])).replace("/", "\\")
        asset = {"asset_id": "bg_" + job["job_id"], "path": relative, "file": relative, "name": f"Generated {job['topic']} background", "topics": list(_tokens(str(job["topic"]))), "palette": str(job.get("palette") or ""), "focus": "center", "audience": "adult" if job.get("adult") else "general", "classification": "GENERATED_AWAITING_REVIEW", "approval_state": "awaiting_review", "production_approved": False, "project_generated": True, "source_type": "generated_art", "lifecycle_state": "active", "orientation": "portrait" if int(health.get("height") or 0) > int(health.get("width") or 0) else "landscape", "health": health, "sha256": sha, "perceptual_hash": phash, "visual_family_id": "vf_" + phash, "provenance": {"provider": "Cloudflare Workers AI", "model": getattr(self.provider.credentials, "model", "configured model"), "prompt": prompt, "generated_at": utc_now()}, "usage": [], "created_at": utc_now(), "updated_at": utc_now()}
        payload = self.index.payload(); payload.setdefault("assets", []).append(asset); self.index.save(payload)
        job.update(status="AWAITING_REVIEW", asset_id=asset["asset_id"], updated_at=utc_now()); self._save_queue(queue); return GenerationResult("AWAITING_REVIEW", "A new background is ready for human review. It cannot enter production until approved.", asset)

    def review(self, asset_id: str, decision: str) -> GenerationResult:
        """Record one explicit human decision; generation never self-approves."""
        decision = str(decision).strip().casefold()
        if decision not in {"approved", "rejected"}:
            raise ValueError("Choose approved or rejected.")
        payload = self.index.payload()
        row = next((item for item in payload.get("assets", []) if str(item.get("asset_id")) == str(asset_id)), None)
        if not row:
            return GenerationResult("MISSING", "The background record could not be found.")
        source = Path(__file__).resolve().parents[1] / str(row.get("path") or "")
        if not source.is_file():
            return GenerationResult("MISSING", "The background image file could not be found.", row)
        if decision == "rejected":
            row.update(approval_state="rejected", production_approved=False, classification="REJECTED", approval_revision=utc_now(), updated_at=utc_now())
            self.index.save(payload)
            return GenerationResult("REJECTED", "The background was rejected and remains unavailable to production.", row)
        approved = GENERATED_DIR / "approved" / source.name
        approved.parent.mkdir(parents=True, exist_ok=True)
        if source.resolve() != approved.resolve(): source.replace(approved)
        relative = str(approved.relative_to(Path(__file__).resolve().parents[1])).replace("/", "\\")
        row.update(path=relative, file=relative, approval_state="approved", production_approved=True,
                   classification="APPROVED_CLOUDFLARE_GENERATED", approval_revision=utc_now(),
                   sha256=file_sha256(approved), updated_at=utc_now())
        self.index.save(payload)
        return GenerationResult("APPROVED", "The reviewed background is approved for production.", row)
    @staticmethod
    def _load_queue() -> dict:
        try:
            parsed = json.loads(QUEUE_FILE.read_text(encoding="utf-8")); return parsed if isinstance(parsed, dict) and isinstance(parsed.get("jobs"), list) else {"jobs": []}
        except (OSError, json.JSONDecodeError): return {"jobs": []}
    @staticmethod
    def _save_queue(queue: dict) -> None:
        QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True); temp = QUEUE_FILE.with_suffix(".tmp"); temp.write_text(json.dumps(queue, indent=2), encoding="utf-8"); temp.replace(QUEUE_FILE)
