"""Local, explainable catalog strategy over the existing Publishing database.

No marketplace-demand values are guessed here. Rankings describe production
readiness, differentiation, coverage gaps, and remaining local work only.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
import hashlib
import re
from pathlib import Path
from time import perf_counter

from .production_gate import book_gate
from .puzzle_types import REGISTRY, resolve_puzzle_type

UNSUPPORTED_MARKET_TERMS = {"search volume", "cpc", "monthly sales", "profitability", "amazon competition", "ranking difficulty"}


def _tokens(value: object) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9]+", str(value or "").casefold()) if len(word) > 2}


def _jaccard(left: set[str], right: set[str]) -> float:
    return len(left & right) / max(1, len(left | right))


def _identity(*values: object) -> str:
    return hashlib.sha256("|".join(str(value) for value in values).encode("utf-8")).hexdigest()[:20]


@dataclass(frozen=True)
class CatalogRecord:
    book_id: str
    title: str
    subtitle: str
    puzzle_type: str
    topic: str
    audience: str
    series: str
    production_state: str
    marketplace_state: dict[str, str]
    puzzle_count: int
    package_path: str
    cover_identity: str
    listing_positioning: str
    published_or_released: bool

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ProductOpportunity:
    opportunity_id: str
    book_id: str
    topic_id: str
    title: str
    recommended_format: str
    production_readiness: str
    catalog_gap: str
    score: int
    differentiation: str
    series_opportunity: str
    reasons: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    missing_work: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        value = asdict(self)
        for key in ("reasons", "warnings", "missing_work"):
            value[key] = list(value[key])
        return value


class CatalogIntelligence:
    """Read model and strategy calculations; never mutates catalog records."""

    def __init__(self, publishing_service) -> None:
        self.service = publishing_service
        self.project = Path(publishing_service.project)

    @staticmethod
    def _cover_identity(meta: dict) -> str:
        files = meta.get("files") if isinstance(meta.get("files"), dict) else {}
        return str(meta.get("cover_art_id") or meta.get("cover_art_sha256") or files.get("front_cover") or "")

    def catalog(self) -> list[CatalogRecord]:
        rows = []
        for book in self.service.db.list_books():
            meta = dict(book.get("metadata") or {}); statuses = dict(book.get("statuses") or {})
            puzzle = resolve_puzzle_type(meta.get("puzzle_type_id") or meta.get("puzzle_type") or "word_search")
            kind = puzzle.type_id if puzzle else str(meta.get("puzzle_type") or "word_search")
            topic = str(meta.get("detected_topic") or meta.get("theme") or meta.get("topic") or "General").strip()
            title = str(meta.get("title") or "Untitled").strip()
            published = any(value in {"Uploaded", "Published"} for value in statuses.values())
            rows.append(CatalogRecord(
                str(book.get("book_id") or ""), title, str(meta.get("subtitle") or ""), kind,
                topic, str(meta.get("audience") or "general"), str(meta.get("series") or ""),
                str(meta.get("production_status") or ("Package available" if book.get("package_path") else "Source only")),
                statuses, int(meta.get("puzzle_count") or 0), str(book.get("package_path") or ""),
                self._cover_identity(meta), str(meta.get("positioning") or meta.get("description") or "")[:240], published,
            ))
        return rows

    @staticmethod
    def differentiation(left: CatalogRecord, right: CatalogRecord) -> dict:
        title = _jaccard(_tokens(left.title), _tokens(right.title))
        subtitle = _jaccard(_tokens(left.subtitle), _tokens(right.subtitle))
        same_topic = left.topic.casefold() == right.topic.casefold()
        same_format = left.puzzle_type == right.puzzle_type
        same_audience = left.audience.casefold() == right.audience.casefold()
        same_series = bool(left.series and left.series.casefold() == right.series.casefold())
        score = .42 * title + .18 * subtitle + .18 * same_topic + .10 * same_format + .07 * same_audience + .05 * same_series
        label = "Same Series — Intentional" if same_series and score >= .55 else "Duplicate-Like" if score >= .82 else "Highly Similar" if score >= .62 else "Distinct"
        return {"score": round(score, 3), "label": label,
                "evidence": {"title_overlap": round(title, 3), "subtitle_overlap": round(subtitle, 3),
                             "same_topic": same_topic, "same_format": same_format,
                             "same_audience": same_audience, "same_series": same_series}}

    def similarity_findings(self, records: list[CatalogRecord] | None = None) -> list[dict]:
        records = records or self.catalog(); inverted: dict[str, set[int]] = defaultdict(set)
        for index, record in enumerate(records):
            for token in _tokens(record.title) | {"topic:" + record.topic.casefold()}:
                inverted[token].add(index)
        pairs = set()
        for indexes in inverted.values():
            ordered = sorted(indexes)
            pairs.update((ordered[a], ordered[b]) for a in range(len(ordered)) for b in range(a + 1, len(ordered)))
        output = []
        for left_index, right_index in pairs:
            result = self.differentiation(records[left_index], records[right_index])
            if result["label"] != "Distinct":
                output.append({"left": records[left_index].book_id, "right": records[right_index].book_id, **result})
        return sorted(output, key=lambda row: (-row["score"], row["left"], row["right"]))

    def coverage_map(self, records: list[CatalogRecord] | None = None) -> dict:
        records = records or self.catalog(); topics: dict[str, dict] = {}
        all_formats = {item.type_id for item in REGISTRY.all(include_nonproduction=False)}
        for record in records:
            row = topics.setdefault(record.topic, {"books": 0, "formats": set(), "series": set(), "released": 0, "source_only": 0})
            row["books"] += 1; row["formats"].add(record.puzzle_type)
            if record.series: row["series"].add(record.series)
            row["released"] += int(record.published_or_released); row["source_only"] += int(not record.package_path)
        return {topic: {"books": row["books"], "formats": sorted(row["formats"]),
                        "missing_formats": sorted(all_formats - row["formats"]), "series": sorted(row["series"]),
                        "released": row["released"], "source_only": row["source_only"],
                        "coverage": "heavy" if row["books"] >= 6 else "light" if row["books"] <= 2 else "balanced"}
                for topic, row in sorted(topics.items())}

    def opportunities(self, limit: int = 20, view: str = "fastest") -> list[ProductOpportunity]:
        books = {str(book.get("book_id") or ""): book for book in self.service.db.list_books()}
        records = self.catalog(); coverage = self.coverage_map(records); findings = self.similarity_findings(records)
        risk_by_book: dict[str, list[dict]] = defaultdict(list)
        for row in findings:
            risk_by_book[row["left"]].append(row); risk_by_book[row["right"]].append(row)
        rows = []
        for record in records:
            book = books.get(record.book_id) or {}; gate = book_gate(book)
            cover_ready = bool(record.cover_identity)
            strict_ready = bool(gate.get("ready"))
            gap = coverage[record.topic]
            strongest = max((item["score"] for item in risk_by_book.get(record.book_id, [])), default=0.0)
            distinct_points = round(20 * (1 - strongest))
            gap_points = 20 if gap["books"] <= 1 else 14 if gap["books"] <= 3 else 6
            readiness_points = 35 if strict_ready else 8
            cover_points = 10 if cover_ready else 2
            workload_points = 10 if record.package_path else 6 if strict_ready else 1
            series_points = 5 if record.series and len(gap["formats"]) > 0 else 2
            score = readiness_points + gap_points + distinct_points + cover_points + workload_points + series_points
            missing = []
            if not strict_ready: missing.append("Resolve the current production/content gate")
            if not cover_ready: missing.append("Choose or approve a topic-matched cover background")
            if not record.package_path: missing.append("Create the complete local package")
            warnings = []
            if strongest >= .82: warnings.append("A duplicate-like local catalog record needs differentiation review")
            elif strongest >= .62: warnings.append("A highly similar local catalog record exists")
            reasons = ["Strict local production gate is ready" if strict_ready else "Current local gate still needs work",
                       f"Topic has {gap['books']} tracked book(s) across {len(gap['formats'])} format(s)",
                       "Approved/current cover identity is recorded" if cover_ready else "No approved/current cover identity is recorded",
                       f"Highest transparent catalog-overlap score is {strongest:.0%}"]
            if view == "gaps": score += gap_points
            elif view == "series" and record.series: score += 8
            rows.append(ProductOpportunity(
                _identity(record.book_id, record.topic, record.puzzle_type), record.book_id, record.topic,
                record.title, record.puzzle_type, "ready" if strict_ready else "blocked",
                gap["coverage"], min(100, score), "high overlap" if strongest >= .62 else "distinct",
                (f"Extend {record.series} into: {', '.join(gap['missing_formats'][:2])}" if record.series and gap["missing_formats"] else "No clear series extension from current evidence"),
                tuple(reasons), tuple(warnings), tuple(missing),
            ))
        return sorted(rows, key=lambda item: (-item.score, len(item.missing_work), item.title.casefold()))[:limit]

    def analyze(self, limit: int = 20) -> dict:
        started = perf_counter(); records = self.catalog(); catalog_ms = (perf_counter() - started) * 1000
        started = perf_counter(); coverage = self.coverage_map(records); coverage_ms = (perf_counter() - started) * 1000
        started = perf_counter(); overlaps = self.similarity_findings(records); overlap_ms = (perf_counter() - started) * 1000
        started = perf_counter(); opportunities = self.opportunities(limit); opportunity_ms = (perf_counter() - started) * 1000
        return {"records": [row.to_dict() for row in records], "coverage": coverage, "overlaps": overlaps,
                "opportunities": [row.to_dict() for row in opportunities],
                "notice": "All scores use local production evidence; no external marketplace-demand evidence is included.",
                "timing_ms": {"catalog": round(catalog_ms, 2), "coverage": round(coverage_ms, 2),
                              "overlap": round(overlap_ms, 2), "opportunities": round(opportunity_ms, 2)}}

    def commercial_catalog_audit(self, limit: int = 20) -> dict:
        """Read-only V2 view using catalog facts and transparent local heuristics."""
        from .commercial_intelligence import commercial_assessment
        from .commercial_profiles import infer_archetypes

        books = {str(book.get("book_id") or ""): book for book in self.service.db.list_books()}
        records = self.catalog(); base = self.opportunities(max(limit, len(records) or limit))
        opportunity_by_id = {row.book_id: row for row in base}
        rows = []
        for record in records:
            book = books.get(record.book_id) or {"metadata": record.to_dict()}
            assessment = commercial_assessment(book)
            base_row = opportunity_by_id.get(record.book_id)
            rows.append({
                "book_id": record.book_id, "title": record.title, "topic": record.topic,
                "puzzle_type": record.puzzle_type, "audience": record.audience,
                "archetypes": [item["label"] for item in assessment["commercial_archetypes"]],
                "marketplace_fit": {key: value["fit"] for key, value in assessment["marketplace_fit"].items()},
                "marketplace_breadth": assessment["marketplace_breadth"],
                "commercial_strengths": assessment["strengths"], "commercial_warnings": assessment["commercial_warnings"],
                "production_readiness": base_row.production_readiness if base_row else "unknown",
                "fastest_to_production_points": base_row.score if base_row else 0,
                "missing_work": list(base_row.missing_work) if base_row else [],
                "notice": "Internal readiness and product-fit heuristics only; not sales potential.",
            })

        topic_groups: dict[str, list[CatalogRecord]] = defaultdict(list)
        series_groups: dict[str, list[CatalogRecord]] = defaultdict(list)
        type_counts = Counter(record.puzzle_type for record in records)
        for record in records:
            topic_groups[record.topic].append(record)
            if record.series: series_groups[record.series].append(record)

        bundle_opportunities = []
        for topic, members in topic_groups.items():
            formats = sorted({item.puzzle_type for item in members})
            if len(members) >= 2 and len(formats) >= 2:
                bundle_opportunities.append({"title": f"{topic} Puzzle Bundle", "topic": topic,
                    "books": [item.title for item in members[:5]], "formats": formats,
                    "reason": "Existing distinct formats share one topic; review content overlap and digital rights before creating a bundle."})
        series_opportunities = []
        for series, members in series_groups.items():
            formats = sorted({item.puzzle_type for item in members})
            series_opportunities.append({"series": series, "existing_books": len(members), "formats": formats,
                "opportunity": "Review missing formats or adjacent subtopics while preserving the established cover family."})
        for topic, members in topic_groups.items():
            if not any(item.series for item in members) and len(members) >= 2:
                series_opportunities.append({"series": f"Potential {topic} series", "existing_books": len(members),
                    "formats": sorted({item.puzzle_type for item in members}),
                    "opportunity": "Multiple related catalog records could form a coherent series after human duplication review."})

        near_duplicates = self.similarity_findings(records)[:10]
        fastest = sorted(rows, key=lambda row: (-row["fastest_to_production_points"], len(row["missing_work"]), row["title"].casefold()))[:limit]
        strong_next = [row for row in fastest if row["production_readiness"] == "ready" and not row["commercial_warnings"]][:limit]
        nostalgia = [row for row in rows if "Nostalgia" in row["archetypes"]]
        senior = [row for row in rows if "Senior Large Print" in row["archetypes"]]
        weak = [row for row in rows if row["commercial_warnings"]]
        return {
            "top_next_opportunities": strong_next,
            "fastest_to_production": fastest,
            "near_duplicates": near_duplicates,
            "series_opportunities": series_opportunities[:10],
            "bundle_opportunities": bundle_opportunities[:10],
            "nostalgia_opportunities": nostalgia,
            "senior_large_print_opportunities": senior,
            "underrepresented_puzzle_types": [{"puzzle_type": key, "catalog_books": value} for key, value in sorted(type_counts.items(), key=lambda item: (item[1], item[0]))],
            "weak_marketplace_positioning": weak,
            "notice": "This is a read-only local catalog analysis. It contains no external demand, sales, competition, rank, or profit data and creates no product.",
        }

    def non_word_expansion_plan(self) -> dict:
        """Extend this catalog read model with format-specific non-word evidence."""
        from .non_word_catalog import non_word_catalog_plan
        return non_word_catalog_plan(self.project, self.catalog())


def contains_fake_market_metrics(payload: object) -> bool:
    text = str(payload).casefold()
    return any(term in text for term in UNSUPPORTED_MARKET_TERMS)
