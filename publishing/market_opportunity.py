"""Persistent local Market Opportunity records built from existing evidence."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path

from .business_automation import BusinessAutomation
from .puzzle_types import resolve_puzzle_type


@dataclass(frozen=True)
class MarketOpportunity:
    opportunity_id: str
    book_id: str
    name: str
    topic: str
    puzzle_type: str
    score: int
    evidence_kind: str
    evidence: tuple[str, ...]
    risks: tuple[str, ...]
    production_feasibility: str
    review_required: bool
    status: str = "needs_review"
    created_at: str = ""
    puzzle_type_id: str = ""

    def to_dict(self):
        value = asdict(self); value["evidence"] = list(self.evidence); value["risks"] = list(self.risks); return value


class MarketOpportunityService:
    """Turns existing local production guidance into reviewable records.

    Scores are derived only from local readiness, content, package, overlap,
    and season signals. They are not sales or demand predictions.
    """
    def __init__(self, publishing_service) -> None:
        self.service = publishing_service; self.root = Path(publishing_service.project)

    @property
    def path(self) -> Path: return self.root / "data" / "market_opportunities.json"

    def refresh(self, limit: int = 24) -> list[MarketOpportunity]:
        now = datetime.now().isoformat(timespec="seconds"); rows = []
        for item in BusinessAutomation(self.service).opportunities(limit):
            book = item["book"]; identity = hashlib.sha256(str(book.get("book_id") or item["title"]).encode()).hexdigest()[:20]
            gate_ready = item["readiness"] == 100
            evidence = ("DERIVED from local production, content, package, overlap, and seasonal-fit evidence.", item["reason"])
            rows.append(MarketOpportunity(
                identity, str(item["book_id"]), item["title"], item["topic"],
                item["puzzle_type"], int(item["score"]), "DERIVED", evidence,
                (item["main_risk"],), "GREEN" if gate_ready else "YELLOW",
                True, "needs_review", now,
                (resolve_puzzle_type(item["puzzle_type"]).type_id if resolve_puzzle_type(item["puzzle_type"]) else ""),
            ))
        previous = {str(row.get("opportunity_id") or ""): row for row in self.load()}
        rows = [self._preserve_review(row, previous.get(row.opportunity_id)) for row in rows]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"schema_version": 1, "generated_at": now, "score_notice": "Local derived opportunity score; not a sales, ranking, traffic, or profitability prediction.", "opportunities": [row.to_dict() for row in rows]}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return rows

    def load(self) -> list[dict]:
        try: return list(json.loads(self.path.read_text(encoding="utf-8-sig")).get("opportunities") or [])
        except (OSError, json.JSONDecodeError): return []

    @staticmethod
    def _preserve_review(row: MarketOpportunity, previous: dict | None) -> MarketOpportunity:
        """Keep a human decision during refresh when the same local book remains."""
        if not previous or previous.get("status") not in {"approved", "rejected"}:
            return row
        return MarketOpportunity(
            row.opportunity_id, row.book_id, row.name, row.topic, row.puzzle_type,
            row.score, row.evidence_kind, row.evidence, row.risks,
            row.production_feasibility, row.review_required,
            str(previous["status"]), row.created_at, row.puzzle_type_id,
        )

    def review(self, opportunity_id: str, decision: str) -> bool:
        """Record an explicit local operator decision; it creates no book or listing."""
        decision = str(decision).casefold().strip()
        if decision not in {"approved", "rejected"}:
            raise ValueError("Opportunity review must be approved or rejected.")
        payload = self._payload()
        changed = False
        for row in payload["opportunities"]:
            if row.get("opportunity_id") == opportunity_id:
                row["status"] = decision
                row["reviewed_at"] = datetime.now().isoformat(timespec="seconds")
                changed = True
                break
        if changed:
            self.path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return changed

    def _payload(self) -> dict:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8-sig"))
            if isinstance(payload, dict) and isinstance(payload.get("opportunities"), list):
                return payload
        except (OSError, json.JSONDecodeError):
            pass
        return {"schema_version": 1, "generated_at": "", "score_notice": "Local derived opportunity score; not a sales, ranking, traffic, or profitability prediction.", "opportunities": []}
