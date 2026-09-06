"""Truthful, read-only planning for puzzle formats beyond Word Search.

This module deliberately separates *renderable* content from content that has
the evidence required for commercial production.  It never creates books,
approves candidates, or calls an external provider.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
from typing import Iterable

from .commercial_profiles import infer_archetypes, marketplace_fit, normalize_puzzle_type

PLAN_VERSION = "non-word-catalog-2026.09"
READINESS = ("Ready Now", "Needs Minor Content Expansion", "Needs Editorial Review",
             "Needs Format Development", "Not Recommended")
TARGETS = {
    "mixed": (15, 25), "scramble_trivia": (15, 25),
    "cryptogram": (12, 20), "sudoku": (12, 20),
}

TOPICS = (
    "1950s Nostalgia", "1960s Nostalgia", "1970s Nostalgia", "1980s Nostalgia", "1990s Nostalgia",
    "Senior Large Print", "American Road Trip", "Route 66", "National Parks", "States and Landmarks",
    "Camping and RV Travel", "American History", "Americana", "Holidays and Seasons", "Family Game Night",
    "Screen-Free Relaxation", "Gardening", "Fishing", "Cooking", "Classic Cars", "Quilting", "Birding",
    "Hiking", "Travel and Adventure", "Nature and Outdoors", "Space and Astronomy", "Bible and Faith",
    "Pets and Animal Life", "School and Vocabulary", "Food and Home", "Mystery and Detective",
    "Wit and Wisdom", "Original Inspiration", "Retirement", "Geography", "Weather and Climate",
    "Ocean Life", "Homesteading", "Sports and Hobbies", "General Knowledge and Curiosity",
)

FORMAT_LABELS = {"mixed": "Mixed Brain Games", "scramble_trivia": "Scramble + Trivia",
                 "cryptogram": "Cryptograms", "sudoku": "Sudoku"}


def _clean(value: object) -> str:
    return " ".join(str(value or "").split()).strip()


def _load_library(project: Path) -> dict:
    path = project / "word_banks" / "puzzle_content_library.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _records(raw: object, kind: str) -> list[dict]:
    output = []
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, dict):
            row = dict(item)
        elif kind == "trivia" and isinstance(item, (list, tuple)) and len(item) >= 3:
            row = {"answer_word": item[0], "question": item[1], "answer": item[2]}
        else:
            row = {"text": item}
        output.append(row)
    return output


def _reviewed(row: dict) -> bool:
    return _clean(row.get("review_state") or row.get("status")).casefold() in {"approved", "reviewed", "verified"}


def _rights_safe(row: dict) -> bool:
    return _clean(row.get("rights_status")).casefold() in {"original", "public_domain", "licensed", "rights_cleared"} and bool(_clean(row.get("provenance") or row.get("source")))


def _fact_safe(row: dict) -> bool:
    state = _clean(row.get("factual_verification_status") or row.get("fact_status")).casefold()
    return state in {"verified", "fact_checked"} and bool(_clean(row.get("provenance") or row.get("source")))


def capacity_evidence(project: Path | str, topic: str) -> dict:
    """Return format-specific evidence; word counts never imply fact/rights safety."""
    project = Path(project); library = _load_library(project); packs = library.get("packs") or {}
    aliases = {re.sub(r"[^a-z0-9]+", "", str(name).casefold()): pack for name, pack in packs.items() if isinstance(pack, dict)}
    key = re.sub(r"[^a-z0-9]+", "", topic.casefold())
    pack = aliases.get(key, {})
    crypto = _records(pack.get("cryptograms") or pack.get("crypto") or [], "cryptogram")
    trivia = _records(pack.get("trivia") or [], "trivia")
    scramble = _records(pack.get("scrambles") or pack.get("vocabulary") or [], "scramble")
    rights_ready = sum(_reviewed(row) and _rights_safe(row) for row in crypto)
    facts_ready = sum(_reviewed(row) and _fact_safe(row) for row in trivia)
    scramble_ready = sum(_reviewed(row) for row in scramble)
    return {
        "topic": topic,
        "cryptogram": {"source": len(crypto), "verified": rights_ready, "rights_safe": rights_ready},
        "trivia": {"source": len(trivia), "verified": facts_ready, "fact_checked": facts_ready},
        "scramble": {"source": len(scramble), "verified": scramble_ready},
        "sudoku": {"algorithmic": True, "unique_solution_required": True, "variants": ["numbers", "letters", "shapes"]},
        "notice": "Source quantity is shown separately from reviewed, format-eligible capacity.",
    }


def deterministic_mixed_allocation(total: int, profile: str = "balanced",
                                   capacities: dict[str, int] | None = None) -> dict[str, int]:
    """Allocate a stable mixed plan without generic fallback or silent shortfall."""
    if total < 1:
        raise ValueError("Puzzle count must be positive.")
    weights = {
        "balanced": {"word_search": 30, "sudoku": 25, "cryptogram": 20, "scramble_trivia": 25},
        "word_play": {"word_search": 30, "sudoku": 15, "cryptogram": 25, "scramble_trivia": 30},
        "logic": {"word_search": 20, "sudoku": 40, "cryptogram": 25, "scramble_trivia": 15},
    }.get(profile)
    if not weights:
        raise ValueError(f"Unknown mixed profile: {profile}")
    exact = {key: total * value / 100 for key, value in weights.items()}
    result = {key: int(value) for key, value in exact.items()}
    for key in sorted(result, key=lambda name: (-(exact[name] - result[name]), name))[:total - sum(result.values())]:
        result[key] += 1
    if capacities:
        shortage = {key: result[key] - int(capacities.get(key, 0)) for key in result if result[key] > int(capacities.get(key, 0))}
        if shortage:
            detail = ", ".join(f"{key}: {amount}" for key, amount in sorted(shortage.items()))
            raise ValueError("Verified mixed-section capacity is short (" + detail + "). Generic fallback is not allowed.")
    return result


@dataclass(frozen=True)
class NonWordOpportunity:
    topic: str
    puzzle_type: str
    title: str
    readiness: str
    score: int
    audience: str
    archetypes: tuple[str, ...]
    marketplace_fit: tuple[str, ...]
    blockers: tuple[str, ...]
    next_safe_action: str
    series: str
    bundle: str

    def to_dict(self) -> dict:
        value = asdict(self)
        for key in ("archetypes", "marketplace_fit", "blockers"):
            value[key] = list(value[key])
        return value


def _opportunity(project: Path, topic: str, kind: str, catalog_counts: Counter) -> NonWordOpportunity:
    evidence = capacity_evidence(project, topic); blockers = []; readiness = "Ready Now"
    if kind == "cryptogram" and evidence["cryptogram"]["verified"] < 48:
        readiness = "Needs Editorial Review"; blockers.append("48 reviewed, rights-safe prompts with provenance are required")
    elif kind == "scramble_trivia" and (evidence["scramble"]["verified"] < 48 or evidence["trivia"]["verified"] < 48):
        readiness = "Needs Editorial Review"; blockers.append("Reviewed scramble vocabulary and independently verified trivia are required")
    elif kind == "mixed":
        readiness = "Needs Editorial Review"; blockers.append("Every themed section needs its own verified capacity; generic fallback is prohibited")
    elif kind == "sudoku" and any(term in topic.casefold() for term in ("history", "garden", "travel", "holiday", "nostalgia")):
        readiness = "Not Recommended"; blockers.append("The topic would be cosmetic unless a meaningful solving variant or audience promise is defined")
    meta = {"title": topic, "theme": topic, "puzzle_type": kind, "large_print": "senior" in topic.casefold()}
    archetypes = tuple(row["label"] for row in infer_archetypes(meta))
    markets = marketplace_fit(meta)
    best_markets = tuple(row[0] for row in sorted(((v["marketplace"], v["internal_heuristic_points"]) for v in markets.values()), key=lambda row: (-row[1], row[0]))[:3])
    score = max(0, min(100, 72 - 16 * len(blockers) + max(0, 5 - catalog_counts[kind]) * 2 + len(archetypes) * 2))
    label = FORMAT_LABELS[kind]
    title = f"{topic}: {label}"
    action = "Build Safe Plan" if readiness == "Ready Now" else "Review format-specific content evidence" if readiness == "Needs Editorial Review" else "Refine the product identity"
    return NonWordOpportunity(topic, kind, title, readiness, score,
        "seniors" if "Senior" in topic else "families and groups" if "Family" in topic else "adult puzzle solvers",
        archetypes, best_markets, tuple(blockers), action,
        f"{topic} cross-format family", f"{topic} printable and print bundle")


def non_word_catalog_plan(project: Path | str, catalog: Iterable[object] = ()) -> dict:
    project = Path(project); catalog = list(catalog); counts = Counter()
    for item in catalog:
        kind = normalize_puzzle_type(getattr(item, "puzzle_type", None) if not isinstance(item, dict) else item.get("puzzle_type"))
        counts[kind] += 1
    opportunities = [_opportunity(project, topic, kind, counts) for kind in FORMAT_LABELS for topic in TOPICS]
    by_format = {}
    first_sizes = {"mixed": 5, "scramble_trivia": 5, "cryptogram": 4, "sudoku": 4}
    for kind in FORMAT_LABELS:
        rows = sorted((row for row in opportunities if row.puzzle_type == kind), key=lambda row: (READINESS.index(row.readiness), -row.score, row.title))
        by_format[kind] = {
            "label": FORMAT_LABELS[kind], "catalog_count": counts[kind], "target_range": list(TARGETS[kind]),
            "first_wave": [row.to_dict() for row in rows[:first_sizes[kind]]],
            "second_wave": [row.to_dict() for row in rows[first_sizes[kind]:first_sizes[kind] + 10]],
            "top_20": [row.to_dict() for row in rows[:20]],
            "all_opportunities": [row.to_dict() for row in rows],
            "status_counts": dict(Counter(row.readiness for row in rows)),
        }
    return {
        "version": PLAN_VERSION, "formats": by_format,
        "catalog_balance": {"word_search": counts["word_search"], **{key: counts[key] for key in FORMAT_LABELS}},
        "topic_audit": [{"topic": topic, "capacity": capacity_evidence(project, topic),
                         "recommended_formats": [row.puzzle_type for row in opportunities if row.topic == topic and row.readiness != "Not Recommended"]}
                        for topic in TOPICS[:30]],
        "series_opportunities": [f"{topic} cross-format family" for topic in TOPICS[:10]],
        "bundle_opportunities": [f"{topic} print + printable bundle" for topic in TOPICS[:10]],
        "notice": "Read-only local planning. Scores are not demand, sales, competition, or profit predictions. No product was created.",
    }
