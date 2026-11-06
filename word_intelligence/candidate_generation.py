"""Explicit, provider-ready generation of review-only content candidates."""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Protocol

from .content_contracts import normalized_value


@dataclass(frozen=True)
class GenerationRequest:
    campaign_id: str
    topic_id: str
    puzzle_type: str
    requested_count: int
    exclusion_normalized: tuple[str, ...] = ()
    concept_targets: tuple[str, ...] = ()
    explicit_provider_action: bool = False


@dataclass(frozen=True)
class GeneratedCandidate:
    display: str
    content_type: str
    payload: dict[str, object] = field(default_factory=dict)
    source_reference: str = ""


@dataclass(frozen=True)
class GenerationResult:
    provider: str
    requested_count: int
    accepted: tuple[GeneratedCandidate, ...]
    rejected: tuple[str, ...]
    status: str


class CandidateProvider(Protocol):
    provider_name: str
    def available(self) -> bool: ...
    def generate(self, request: GenerationRequest) -> list[GeneratedCandidate]: ...


class DisabledLocalProvider:
    """The safe default: it never invents candidate content."""
    provider_name = "Local candidate generation disabled"
    def available(self) -> bool: return False
    def generate(self, request: GenerationRequest) -> list[GeneratedCandidate]: return []


class CandidateProviderError(RuntimeError):
    """A displayed, non-fallback error from an explicit candidate request."""


_AUTO_CREDENTIALS = object()


class GeminiCandidateGenerationProvider:
    """Word-Search-only adapter using the existing Gemini credential store."""
    provider_name = "Gemini"

    def __init__(self, credentials=_AUTO_CREDENTIALS, timeout: int = 20) -> None:
        from publishing.listing_intelligence import GeminiCredentials
        from integrations.wincred import WinCredError
        self.unavailable_reason = ''
        if credentials is _AUTO_CREDENTIALS:
            try:
                credentials = GeminiCredentials.load()
            except WinCredError:
                credentials = None
                self.unavailable_reason = 'Windows denied credential access. Reconnect the provider before generating candidates.'
        self.credentials = credentials
        self.timeout = timeout

    def available(self) -> bool:
        return self.credentials is not None

    def generate(self, request: GenerationRequest) -> list[GeneratedCandidate]:
        if request.puzzle_type != "word_search":
            raise CandidateProviderError("Live candidate generation is currently available for Word Search only.")
        if not self.credentials:
            raise CandidateProviderError("Gemini candidate generation is not configured. Existing local review remains available.")
        import urllib.error
        import urllib.request
        excluded = list(request.exclusion_normalized)[:240]
        prompt = ("Generate only natural, non-brand Word Search vocabulary for the exact topic below. "
                  "Return JSON only: {\"candidates\":[{\"display\":\"...\",\"suggested_group\":\"...\"}]}. "
                  "Use short recognizable words or phrases, each 21 normalized letters or fewer. Do not use filler, "
                  "adjective+noun variations, trivial plurals, duplicates, protected brands, or unrelated terms.\n"
                  f"TOPIC: {request.topic_id}\nCOUNT: {min(100, max(1, request.requested_count))}\n"
                  f"FOCUS GROUPS: {', '.join(request.concept_targets[:16]) or 'broaden genuine topic coverage'}\n"
                  f"EXCLUDE: {', '.join(excluded)}")
        schema = {"type": "object", "properties": {"candidates": {"type": "array", "items": {"type": "object", "properties": {"display": {"type": "string"}, "suggested_group": {"type": "string"}}, "required": ["display"], "additionalProperties": False}}}, "required": ["candidates"], "additionalProperties": False}
        body = {"model": self.credentials.model, "input": prompt, "store": False,
                "generation_config": {"max_output_tokens": 1600, "thinking_level": "minimal"},
                "response_format": {"type": "text", "mime_type": "application/json", "schema": schema}}
        call = urllib.request.Request("https://generativelanguage.googleapis.com/v1beta/interactions", data=json.dumps(body).encode(), headers={"x-goog-api-key": self.credentials.api_key, "Content-Type": "application/json"}, method="POST")
        try:
            # One bounded retry is useful for a transient incomplete response.
            # It never accepts partial text and never falls back to a different provider.
            parsed = None
            for attempt in range(2):
                with urllib.request.urlopen(call, timeout=self.timeout) as response:
                    payload = json.loads(response.read().decode())
                if str(payload.get("status") or "").casefold() == "incomplete":
                    if attempt == 0:
                        continue
                    raise CandidateProviderError("Gemini stopped before the candidate list was complete. Nothing was added; try again with a smaller request.")
                from publishing.listing_intelligence import _interaction_output_text
                parsed = json.loads(_interaction_output_text(payload))
                break
        except urllib.error.HTTPError as exc:
            raise CandidateProviderError(f"Gemini could not generate candidates (HTTP {exc.code}). Nothing was added.") from None
        except CandidateProviderError:
            raise
        except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            raise CandidateProviderError("Gemini did not return usable structured candidates. Nothing was added.") from exc
        rows = parsed.get("candidates") if isinstance(parsed, dict) else []
        if not isinstance(rows, list):
            raise CandidateProviderError("Gemini returned an invalid candidate list. Nothing was added.")
        return [GeneratedCandidate(str(row.get("display") or ""), "phrase" if " " in str(row.get("display") or "").strip() else "word", {"suggested_group": str(row.get("suggested_group") or "")}, "gemini") for row in rows if isinstance(row, dict)]


class CandidateGenerationService:
    def __init__(self, provider: CandidateProvider | None = None) -> None:
        self.provider = provider or DisabledLocalProvider()

    def preview(self, request: GenerationRequest, *, existing_supply: int, minimum_deficit: int, review_yield: float = .70) -> dict[str, object]:
        remaining = max(0, minimum_deficit - max(0, existing_supply))
        target = min(100, max(0, int((remaining / max(.10, review_yield)) + .999)))
        return {"campaign_id": request.campaign_id, "topic_id": request.topic_id, "puzzle_type": request.puzzle_type,
                "existing_candidate_supply": existing_supply, "minimum_deficit": minimum_deficit,
                "remaining_shortage": remaining, "recommended_request_count": target,
                "provider": self.provider.provider_name, "provider_available": self.provider.available(),
                "explicit_action_required": True}

    def generate(self, request: GenerationRequest) -> GenerationResult:
        if not request.explicit_provider_action:
            return GenerationResult(self.provider.provider_name, request.requested_count, (), (), "explicit_action_required")
        if not self.provider.available():
            return GenerationResult(self.provider.provider_name, request.requested_count, (), (), "provider_unavailable")
        raw = self.provider.generate(request)
        # Callers may provide either display values or already-normalized values.
        # Normalize at this boundary so duplicate protection is not caller-dependent.
        accepted: list[GeneratedCandidate] = []; rejected: list[str] = []; seen = {normalized_value(value) for value in request.exclusion_normalized if normalized_value(value)}
        expected = {"word_search": {"word", "phrase"}, "cryptogram": {"cryptogram_prompt"}, "scramble_trivia": {"trivia"}}.get(request.puzzle_type, set())
        for item in raw[:max(0, request.requested_count)]:
            normal = normalized_value(item.display)
            if not normal or normal in seen:
                rejected.append("blank_or_duplicate"); continue
            if item.content_type not in expected:
                rejected.append("wrong_content_type"); continue
            if request.puzzle_type == "word_search" and len(normal) > 21:
                rejected.append("word_search_too_long"); continue
            if request.puzzle_type == "cryptogram" and len(item.display) > 110:
                rejected.append("cryptogram_too_long"); continue
            if request.puzzle_type == "scramble_trivia" and (not str(item.payload.get("question") or "").strip() or not str(item.payload.get("answer") or "").strip()):
                rejected.append("incomplete_trivia"); continue
            seen.add(normal); accepted.append(item)
        return GenerationResult(self.provider.provider_name, request.requested_count, tuple(accepted), tuple(rejected), "review_ready")

    @staticmethod
    def stable_generated_id(request: GenerationRequest, item: GeneratedCandidate) -> str:
        return hashlib.sha256(f"generated|{request.topic_id}|{request.puzzle_type}|{normalized_value(item.display)}|{item.source_reference}".encode("utf-8")).hexdigest()[:24]
