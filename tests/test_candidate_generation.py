from __future__ import annotations

from word_intelligence.book_planning import BookPlanner, PlanRequest
from word_intelligence.candidate_generation import CandidateGenerationService, GeneratedCandidate, GenerationRequest, GeminiCandidateGenerationProvider
from word_intelligence.capacity import ContentCapacityEngine
from word_intelligence.content_contracts import ContentRecord, FormatRules, Provenance, QualityStatus, TopicReference, deterministic_content_id, normalized_value
from word_intelligence.content_registry import ContentRegistry
from word_intelligence.expansion_campaign import ExpansionCampaignService
from word_intelligence.taxonomy import TopicTaxonomy


class FixtureProvider:
    provider_name = "Fixture provider"

    def __init__(self, rows):
        self.rows = rows
        self.calls = 0

    def available(self):
        return True

    def generate(self, request):
        self.calls += 1
        return self.rows


def test_candidate_generation_requires_an_explicit_action():
    provider = FixtureProvider([GeneratedCandidate("MARTINI", "word")])
    service = CandidateGenerationService(provider)
    request = GenerationRequest("campaign", "nightlife", "word_search", 1)

    result = service.generate(request)

    assert result.status == "explicit_action_required"
    assert provider.calls == 0
    assert service.preview(request, existing_supply=2, minimum_deficit=10)["recommended_request_count"] == 12


def test_word_search_generation_screens_bad_candidates_without_approval():
    provider = FixtureProvider([
        GeneratedCandidate("MARTINI", "word", source_reference="fixture"),
        GeneratedCandidate("martini", "word"),
        GeneratedCandidate("A VERY LONG PHRASE THAT EXCEEDS THE PUZZLE GRID LIMIT", "phrase"),
        GeneratedCandidate("SHAKER", "trivia"),
        GeneratedCandidate("OLIVE", "word"),
    ])
    service = CandidateGenerationService(provider)
    request = GenerationRequest("campaign", "nightlife", "word_search", 5, ("olive",), explicit_provider_action=True)

    result = service.generate(request)

    assert result.status == "review_ready"
    assert [item.display for item in result.accepted] == ["MARTINI"]
    assert set(result.rejected) == {"blank_or_duplicate", "word_search_too_long", "wrong_content_type"}


def test_generated_candidates_are_stored_as_review_only(tmp_path):
    taxonomy = TopicTaxonomy.from_master_bank({"topics": {"Nightlife": ["MARTINI"]}})
    registry = ContentRegistry()
    record = ContentRecord(
        deterministic_content_id("word", "MARTINI", source_id="fixture"), "word", "MARTINI", normalized_value("MARTINI"),
        (TopicReference("nightlife", "primary", 100, "legacy_unreviewed"),), format_rules=FormatRules(),
        quality=QualityStatus("legacy_unreviewed", "verified", False, False), provenance=Provenance("curated", "fixture"),
    )
    registry.add(record)
    planner = BookPlanner(ContentCapacityEngine(tmp_path, taxonomy, registry, cache_state={"state": "fresh"}))
    request = PlanRequest(taxonomy.resolve("Nightlife"), "word_search", 1, 1)
    campaign = ExpansionCampaignService(planner, tmp_path).create(request)
    store = ExpansionCampaignService(planner, tmp_path)

    stored = store.store_generated(campaign, [GeneratedCandidate("COCKTAIL SHAKER", "word", source_reference="fixture")])
    rows = store.load_candidates()

    assert stored == 1
    assert rows[0]["status"] == "generated_unreviewed"
    assert rows[0]["provenance"] == "generated:fixture"
    assert not registry.get(rows[0]["candidate_id"])


def test_gemini_provider_is_unavailable_without_shared_credentials():
    provider = GeminiCandidateGenerationProvider(credentials=None)
    # A missing saved key means the UI can show an honest no-provider state;
    # constructing the adapter itself cannot make a network request.
    if provider.credentials is None:
        assert not provider.available()


def test_explicit_no_credentials_never_reads_the_user_vault(monkeypatch):
    from publishing.listing_intelligence import GeminiCredentials
    def forbidden():
        raise AssertionError('Explicit None must not access credentials.')
    monkeypatch.setattr(GeminiCredentials,'load',forbidden)
    assert not GeminiCandidateGenerationProvider(credentials=None).available()


def test_denied_automatic_credentials_leave_local_review_available(monkeypatch):
    from publishing.listing_intelligence import GeminiCredentials
    from integrations.wincred import WinCredError
    def denied():
        raise WinCredError('load',5)
    monkeypatch.setattr(GeminiCredentials,'load',denied)
    provider=GeminiCandidateGenerationProvider()
    assert not provider.available()
    assert 'denied credential access' in provider.unavailable_reason


def test_explicit_credentials_are_preserved_without_loading(monkeypatch):
    from publishing.listing_intelligence import GeminiCredentials
    monkeypatch.setattr(GeminiCredentials,'load',lambda: (_ for _ in ()).throw(AssertionError('Unexpected credential access')))
    supplied=object()
    provider=GeminiCandidateGenerationProvider(credentials=supplied)
    assert provider.credentials is supplied and provider.available()
