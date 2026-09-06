"""Phase 4 local production proof orchestration.

This module is deliberately an orchestration layer over the existing planner,
PDF review, cover assessment, package contract, listing validation, and SQLite
release history.  It does not publish, create a package, or alter generators.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from word_intelligence.book_planning import BookPlan, BookPlanner
from .listing_intelligence import validate_output, verified_facts
from .package_layout import package_file, release_contract
from .production_intelligence import cover_assessment, pdf_assessment, visual_quality_assessment

SCHEMA_VERSION = 1
HARD_FAIL = "hard_fail"
NEEDS_REVIEW = "needs_review"
WARNING = "warning"
INFO = "info"


def canonical_json(value: object) -> str:
    """Stable JSON used for plan/proof identity; formatting never matters."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def book_plan_hash(plan: BookPlan) -> str:
    """Hash plan semantics while excluding its non-production creation timestamp."""
    data = plan.to_dict()
    data.pop("created_at", None)
    return sha256_bytes(canonical_json(data).encode("utf-8"))


@dataclass(frozen=True)
class QualityCheck:
    check_id: str
    stage: str
    severity: str
    status: str
    message: str
    evidence: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {"check_id": self.check_id, "stage": self.stage, "severity": self.severity,
                "status": self.status, "message": self.message, "evidence": self.evidence}


@dataclass
class ProductionProof:
    proof_id: str
    book_plan_id: str
    book_id: str
    package_id: str
    generated_at: str
    source_revision: str
    capacity_proof: str
    book_plan_hash: str
    artifacts: dict[str, dict[str, object]]
    checks: list[QualityCheck]
    scorecard: dict[str, int]
    blocking_reasons: list[str]
    warnings: list[str]
    attention_required: list[dict[str, str]]
    status: str
    content_verification_mode: str
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, object]:
        return {"schema_version": self.schema_version, "proof_id": self.proof_id,
                "book_plan_id": self.book_plan_id, "book_id": self.book_id,
                "package_id": self.package_id, "generated_at": self.generated_at,
                "source_revision": self.source_revision, "capacity_proof": self.capacity_proof,
                "book_plan_hash": self.book_plan_hash, "artifacts": self.artifacts,
                "checks": [check.to_dict() for check in self.checks], "scorecard": self.scorecard,
                "blocking_reasons": self.blocking_reasons, "warnings": self.warnings,
                "attention_required": self.attention_required, "status": self.status,
                "content_verification_mode": self.content_verification_mode}


def _check(check_id: str, stage: str, severity: str, passed: bool, message: str,
           evidence: dict[str, object] | None = None) -> QualityCheck:
    return QualityCheck(check_id, stage, severity, "passed" if passed else "failed", message, evidence or {})


def artifact_manifest(package: Path | str, *, include_metadata: bool = True) -> dict[str, dict[str, object]]:
    root = Path(package)
    names = {"interior": "interior.pdf", "cover": "front_cover.png", "wrap": "kdp_full_wrap.pdf"}
    if include_metadata:
        names["source_record"] = "PACKAGE_SOURCE_RECORD.json"
        names["listing"] = "KDP_LISTING_KIT.txt"
    output = {}
    for label, name in names.items():
        path = package_file(root, name)
        output[label] = {"path": str(path), "exists": path.is_file(),
                         "sha256": sha256_file(path) if path.is_file() else "",
                         "bytes": path.stat().st_size if path.is_file() else 0}
    from background_generation.index import verify_rendered_cover_approval
    approved, reason, approval = verify_rendered_cover_approval(package_file(root, "front_cover.png"))
    output["cover_approval"] = {
        "path": str(package_file(root, "front_cover.png")), "exists": approved,
        "sha256": str(approval.get("front_cover_sha256") or ""), "bytes": 0,
        "asset_id": str(approval.get("asset_id") or ""), "asset_sha256": str(approval.get("asset_sha256") or ""),
        "approval_state": str(approval.get("approval_state") or "missing"),
        "approval_revision": str(approval.get("approval_revision") or ""),
        "provenance": approval.get("provenance") or {}, "reason": reason,
    }
    return output


def _artifact_check(name: str, artifact: dict[str, object], required: bool = True) -> QualityCheck:
    exists = bool(artifact.get("exists"))
    severity = HARD_FAIL if required else WARNING
    return _check(f"artifact.{name}", "package", severity, exists,
                  f"{name.title()} artifact is present." if exists else f"Required {name} artifact is missing.", artifact)


def _plan_content_check(plan: BookPlan, evidence: dict[str, object] | None) -> QualityCheck:
    if plan.puzzle_type == "sudoku":
        return _check("content.plan_correspondence", "content", HARD_FAIL, True,
                      "Sudoku plan carries deterministic generator specifications.")
    if plan.puzzle_type == "mixed":
        passed = bool(evidence and evidence.get("sections") == sorted(plan.section_plans))
        return _check("content.mixed_sections", "content", HARD_FAIL, passed,
                      "Mixed sections match the Book Plan." if passed else "Mixed section evidence does not match the Book Plan.")
    actual = list((evidence or {}).get("selected_content_ids") or [])
    expected = plan.selected_content_ids
    passed = actual == expected
    return _check("content.plan_correspondence", "content", HARD_FAIL, passed,
                  "Generated content IDs and ordering match the Book Plan." if passed else
                  "Generated content evidence does not exactly match the Book Plan.",
                  {"expected_count": len(expected), "actual_count": len(actual)})


def _listing_check(book: dict | None, plan: BookPlan) -> QualityCheck:
    if not book:
        return _check("listing.verified_facts", "listing", INFO, True, "No catalog listing was supplied for this standalone proof.")
    facts = verified_facts(book, "amazon")
    meta = book.get("metadata") or {}
    descriptions = [str(meta.get("description") or ""), *[str(value) for value in (meta.get("platform_descriptions") or {}).values()]]
    text = " ".join(item for item in descriptions if item).strip()
    if not text:
        return _check("listing.verified_facts", "listing", WARNING, True, "No listing description is present to validate yet.")
    valid, issues, _clean = validate_output({"description": text, "keywords": meta.get("amazon_keywords") or [], "tags": meta.get("etsy_tags") or []}, facts)
    return _check("listing.verified_facts", "listing", HARD_FAIL, valid,
                  "Listing claims agree with verified facts." if valid else "Listing conflicts with verified facts: " + "; ".join(issues),
                  {"plan_puzzle_count": plan.format.get("puzzle_count"), "listing_puzzle_count": facts.get("puzzle_count")})


def build_verified_facts(plan: BookPlan, *, page_count: int = 0, title: str = "", subtitle: str = "", author: str = "") -> dict[str, object]:
    """Canonical production facts permitted to flow to listing intelligence."""
    return {"title": title, "subtitle": subtitle, "author": author, "puzzle_type": plan.puzzle_type,
            "puzzle_count": int(plan.format.get("puzzle_count") or 0), "page_count": page_count,
            "difficulty": str(plan.format.get("difficulty") or "standard"),
            "large_print": bool(plan.format.get("large_print")), "solutions_included": True,
            "topic_ids": list(plan.topic_ids), "trim_size": "8.5x11",
            "edition": "Signature Edition" if int(plan.format.get("puzzle_count") or 0) >= 100 else "Standard",
            "content_verification_mode": plan.review_policy}


def build_production_proof(project: Path | str, plan: BookPlan, package: Path | str, *,
                           book: dict | None = None, generation_evidence: dict[str, object] | None = None,
                           planner: BookPlanner | None = None, human_acknowledged: bool = False) -> ProductionProof:
    """Run the unified local gate.  It does not write, generate, or publish."""
    project, root = Path(project), Path(package)
    checks: list[QualityCheck] = []
    active_planner = planner or BookPlanner.from_project(project)
    plan_state = active_planner.validate(plan)
    checks.append(_check("plan.validity", "plan", HARD_FAIL, plan_state.status == "valid",
                         "Book Plan is valid." if plan_state.status == "valid" else "; ".join(plan_state.reasons) or "Book Plan is invalid."))
    manifest = artifact_manifest(root)
    checks.extend(_artifact_check(name, data, name in {"interior", "cover", "wrap", "cover_approval"}) for name, data in manifest.items())
    interior = pdf_assessment(package_file(root, "interior.pdf"))
    checks.append(_check("interior.pdf", "interior", HARD_FAIL, bool(interior.get("ok")),
                         "; ".join(interior.get("notes") or []), {"pages": interior.get("pages", 0), "sizes": interior.get("sizes", [])}))
    wrap = pdf_assessment(package_file(root, "kdp_full_wrap.pdf"), 1)
    checks.append(_check("wrap.pdf", "wrap", HARD_FAIL, bool(wrap.get("ok")), "; ".join(wrap.get("notes") or []), {"pages": wrap.get("pages", 0)}))
    cover = cover_assessment(package_file(root, "front_cover.png"))
    checks.append(_check("cover.readability", "cover", NEEDS_REVIEW, int(cover.get("score") or 0) >= 100,
                         "; ".join(cover.get("notes") or []), {"score": cover.get("score", 0)}))
    visual = visual_quality_assessment(project, root, (book or {}).get("metadata") or {}, plan=plan)
    for item in visual["checks"]:
        severity = {"hard_fail": HARD_FAIL, "needs_review": NEEDS_REVIEW, "warning": WARNING}[item["severity"]]
        checks.append(_check(item["check_id"], "visual_cover", severity, item["passed"], item["message"], item["evidence"]))
    checks.append(_plan_content_check(plan, generation_evidence))
    contract = release_contract(root)
    checks.append(_check("package.contract", "package", HARD_FAIL, bool(contract.get("ready")),
                         "Package release contract is complete." if contract.get("ready") else "Missing: " + ", ".join(contract.get("missing") or []), contract))
    checks.append(_listing_check(book, plan))
    if plan.review_policy != "strict_verified":
        checks.append(_check("content.compatibility_acknowledgement", "content", NEEDS_REVIEW, human_acknowledged,
                             "Compatibility mode was explicitly acknowledged." if human_acknowledged else
                             "Legacy-compatible content requires human acknowledgement before final local readiness."))
    blocks = [check.message for check in checks if check.severity == HARD_FAIL and check.status == "failed"]
    review = [check.message for check in checks if check.severity == NEEDS_REVIEW and check.status == "failed"]
    warns = [check.message for check in checks if check.severity == WARNING and check.status == "failed"]
    status = "blocked" if blocks else "needs_review" if review else "ready_for_platform_preview"
    score_dims = {"Content Integrity": 100 if not any(c.check_id.startswith("content") and c.status == "failed" for c in checks) else 0,
                  "Puzzle Integrity": 100 if not any(c.stage in {"plan", "interior"} and c.status == "failed" for c in checks) else 0,
                  "Interior Quality": 100 if interior.get("ok") else 0,
                  "Cover Truth": 100 if manifest["cover"]["exists"] else 0,
                  "Metadata Consistency": 100 if checks[-1].status == "passed" else 0,
                  "Package Completeness": 100 if contract.get("ready") else 0}
    plan_hash = book_plan_hash(plan)
    proof_key = {"plan_hash": plan_hash, "artifacts": {key: value.get("sha256") for key, value in manifest.items()},
                 "source_revision": plan.source_revision, "capacity_proof": plan.capacity_proof, "checks": [check.to_dict() for check in checks]}
    proof_id = sha256_bytes(canonical_json(proof_key).encode("utf-8"))[:24]
    attention = [{"area": check.stage, "severity": check.severity, "message": check.message}
                 for check in checks if check.status == "failed" and check.severity in {HARD_FAIL, NEEDS_REVIEW, WARNING}]
    return ProductionProof(proof_id, plan.book_plan_id, str((book or {}).get("book_id") or ""),
                           sha256_bytes(str(root.resolve()).encode("utf-8"))[:16], datetime.now(timezone.utc).isoformat(timespec="seconds"),
                           plan.source_revision, plan.capacity_proof, plan_hash, manifest, checks, score_dims,
                           blocks, warns, attention, status, plan.review_policy)


def proof_is_current(proof: ProductionProof, plan: BookPlan, package: Path | str) -> tuple[bool, list[str]]:
    """Dependency-aware comparison: changed artifacts stale the matching proof."""
    reasons: list[str] = []
    if proof.schema_version != SCHEMA_VERSION: reasons.append("Unsupported production-proof schema.")
    if proof.book_plan_hash != book_plan_hash(plan): reasons.append("Book Plan changed.")
    if proof.source_revision != plan.source_revision: reasons.append("Source revision changed.")
    current = artifact_manifest(package)
    for name, artifact in proof.artifacts.items():
        now = current.get(name, {})
        if artifact.get("sha256") != now.get("sha256"):
            reasons.append(f"{name.title()} artifact changed.")
            if name == "interior":
                reasons.append("Wrap must be revalidated because the interior may have changed page count or spine geometry.")
    return not reasons, reasons


def write_proof_report(path: Path | str, proof: ProductionProof, facts: dict[str, object] | None = None) -> Path:
    target = Path(path); target.parent.mkdir(parents=True, exist_ok=True)
    lines = ["PRODUCTION PROOF GATE", "=" * 56, "", f"FINAL LOCAL STATUS: {proof.status.replace('_', ' ').upper()}",
             f"Book Plan: {proof.book_plan_id}", f"Proof: {proof.proof_id}", f"Verification mode: {proof.content_verification_mode}", "", "CHECKS"]
    lines += [f"• {check.status.upper()} — {check.stage}: {check.message}" for check in proof.checks]
    if proof.attention_required:
        lines += ["", "ATTENTION REQUIRED"] + [f"• {item['area']}: {item['message']}" for item in proof.attention_required]
    if facts: lines += ["", "VERIFIED LISTING FACTS", *[f"• {key}: {value}" for key, value in facts.items()]]
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target
