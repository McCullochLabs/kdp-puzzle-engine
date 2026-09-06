"""Gemini-grounded niche discovery with an honest local fallback.

Research results are proposals only.  They never create, approve, queue, or
publish a product, and external demand is never inferred from local capacity.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
from pathlib import Path
import re
import urllib.error
import urllib.request

from .listing_intelligence import GeminiCredentials, _interaction_output_text


@dataclass(frozen=True)
class TrendProposal:
    topic: str
    puzzle_type: str
    audience: str
    buyer_angle: str
    evidence_summary: str
    source_urls: tuple[str, ...]
    source: str
    research_date: str
    local_capacity_note: str = ""

    def to_dict(self) -> dict:
        value = asdict(self)
        value["source_urls"] = list(self.source_urls)
        return value


class TrendResearchError(RuntimeError):
    pass


def _http_fallback_note(exc: urllib.error.HTTPError) -> str:
    """Translate provider status into useful operator guidance without secrets."""
    if exc.code in {401, 403}:
        return "Gemini did not accept the saved API key or Search access. Check Gemini setup, then try again."
    if exc.code in {402, 429}:
        return "Gemini's current quota is exhausted. Live trend research can run after the quota resets or the Gemini plan is updated."
    if exc.code == 404:
        return "The saved Gemini model is not available for Google Search grounding. Choose a supported Gemini model in setup."
    return f"Gemini's live research service returned HTTP {exc.code}. Try again later or review the local suggestion."


def _json_from_text(value: str) -> dict:
    text = value.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.S)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("No JSON object returned")
    return json.loads(text[start:end + 1])


def _citations(payload: dict) -> tuple[str, ...]:
    urls: list[str] = []
    for candidate in payload.get("candidates", []):
        metadata = candidate.get("groundingMetadata") or {}
        for chunk in metadata.get("groundingChunks", []):
            url = str((chunk.get("web") or {}).get("uri") or "").strip()
            if url and url not in urls:
                urls.append(url)
    return tuple(urls[:8])


class TrendResearchService:
    def __init__(self, project: Path, publishing_service) -> None:
        self.project = Path(project)
        self.publishing_service = publishing_service

    @property
    def history_path(self) -> Path:
        return self.project / "data" / "trend_research_reviews.json"

    def discover(self) -> TrendProposal:
        credentials = GeminiCredentials.load()
        if not credentials:
            return self._local_proposal("Gemini is not configured; this is the strongest local production opportunity, not a live trend claim.")
        prompt = (
            "Act as a cautious puzzle-book niche researcher. Use current Google Search evidence to propose ONE timely, "
            "specific puzzle-book niche worth human review. Consider recurring seasonal interest, giftability, audience clarity, "
            "and visible interest in puzzle/activity books. Do not claim sales, profit, search volume, bestseller status, or low "
            "competition unless a cited source explicitly proves it. Avoid protected brands, celebrities, franchises, medical "
            "claims, and news-only fads. Choose puzzle_type from Word Search, Sudoku, Cryptogram, Word Scramble + Trivia, or "
            "Mixed Brain Games. Return JSON only with keys topic, puzzle_type, audience, buyer_angle, evidence_summary."
        )
        body = {"contents": [{"parts": [{"text": prompt}]}], "tools": [{"google_search": {}}]}
        model = credentials.model or "gemini-3.5-flash-lite"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        call = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers={
            "x-goog-api-key": credentials.api_key, "Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(call, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
            text = ""
            for candidate in payload.get("candidates", []):
                for part in (candidate.get("content") or {}).get("parts", []):
                    text += str(part.get("text") or "")
            data = _json_from_text(text or _interaction_output_text(payload))
            topic = " ".join(str(data.get("topic") or "").split())
            puzzle_type = " ".join(str(data.get("puzzle_type") or "Word Search").split())
            if not topic:
                raise ValueError("The researched topic was blank")
            if puzzle_type not in {"Word Search", "Sudoku", "Cryptogram", "Word Scramble + Trivia", "Mixed Brain Games"}:
                puzzle_type = "Word Search"
            result = TrendProposal(topic, puzzle_type,
                " ".join(str(data.get("audience") or "Adults & Teens").split()),
                " ".join(str(data.get("buyer_angle") or "Timely themed entertainment").split()),
                " ".join(str(data.get("evidence_summary") or "Review the cited current sources.").split()),
                _citations(payload), "Gemini + Google Search", datetime.now().date().isoformat())
            self._save(result)
            return result
        except urllib.error.HTTPError as exc:
            return self._local_proposal(_http_fallback_note(exc) + " This is a local readiness suggestion, not a trend claim.")
        except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            return self._local_proposal(f"Live research was unavailable ({type(exc).__name__}); this is a local readiness suggestion, not a trend claim.")

    def _local_proposal(self, note: str) -> TrendProposal:
        choices = self.publishing_service.catalog_intelligence(5, "gaps")
        if not choices:
            raise TrendResearchError("No live research result or local catalog opportunity is available yet.")
        choice = choices[0]
        result = TrendProposal(str(choice.get("topic_id") or "General puzzles"),
            str(choice.get("recommended_format") or "Word Search").replace("_", " ").title(),
            "Adults & Teens", "Strongest current local catalog opportunity", note, (),
            "Local catalog fallback", datetime.now().date().isoformat(),
            "; ".join(choice.get("missing_work") or ["Review the existing production checks."]))
        self._save(result)
        return result

    def _save(self, proposal: TrendProposal) -> None:
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            payload = json.loads(self.history_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            payload = {"schema_version": 1, "proposals": []}
        payload.setdefault("proposals", []).append(proposal.to_dict())
        payload["proposals"] = payload["proposals"][-50:]
        self.history_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
