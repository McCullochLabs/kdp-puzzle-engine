"""Evidence-based production capability audit; never a sales prediction."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime

from .production_gate import book_gate
from .puzzle_types import PuzzleTypeRegistry, REGISTRY


@dataclass(frozen=True)
class CapabilityRecord:
    capability_id: str
    name: str
    status: str
    confidence: str
    evidence: tuple[str, ...]
    limitations: tuple[str, ...] = ()
    next_action: str = "Review local evidence"
    evaluated_at: str = ""

    def to_dict(self):
        value = asdict(self); value["evidence"] = list(self.evidence); value["limitations"] = list(self.limitations); return value


class ProductionCapabilityAudit:
    """Reads current catalog evidence without generating or changing anything."""
    def __init__(self, service, *, registry: PuzzleTypeRegistry | None = None) -> None:
        self.service = service
        # Injection keeps this audit easy to test and lets a future format be
        # assessed before it is ever exposed to production screens.
        self.registry = registry or REGISTRY

    def evaluate(self) -> list[CapabilityRecord]:
        books = self.service.db.list_books(); now = datetime.now().isoformat(timespec="seconds")
        ready = [book for book in books if book_gate(book).get("ready")]
        records = []
        for capability in self.registry.all():
            count = sum(1 for item in ready if str((item.get("metadata") or {}).get("puzzle_type_id") or "") == capability.type_id
                        or str((item.get("metadata") or {}).get("puzzle_type") or "Word Search") == capability.display_name)
            if capability.production_available:
                status = "GREEN" if count else "UNKNOWN"
                confidence = "observed" if count else "insufficient_evidence"
                evidence = (f"{count} locally production-ready catalog record(s).",
                            "Registered generator and validator are available through the current production workflow.")
                limitations = () if count else ("No ready local package evidence found.",)
                next_action = "Open Production Dashboard" if count else "Run a controlled local package test"
            else:
                status = "RED"
                confidence = "declared"
                evidence = (f"Registered as {capability.lifecycle}; no production generator is enabled.",)
                limitations = capability.known_limitations or ("This format is not production-ready.",)
                next_action = "Register a generator, validator, and deterministic solution verifier before enabling production."
            records.append(CapabilityRecord(capability.type_id, capability.display_name, status, confidence, evidence,
                                            limitations, next_action, now))
        cover = sum(1 for book in ready if ((book.get("metadata") or {}).get("files") or {}).get("front_cover"))
        records.append(CapabilityRecord("cover_generation", "Cover generation", "GREEN" if cover else "YELLOW", "observed", (f"{cover} ready record(s) include a front-cover fact.",), () if cover else ("Ready packages need cover evidence.",), "Review approved cover assets", now))
        return records
