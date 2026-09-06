from pathlib import Path

from publishing.trend_research import TrendResearchService, _http_fallback_note, _json_from_text
import urllib.error


class FakePublishingService:
    def catalog_intelligence(self, _limit, _view):
        return [{"topic_id": "Garden relaxation", "recommended_format": "word_search", "missing_work": ["Choose a cover"]}]


def test_json_reader_accepts_fenced_payload():
    assert _json_from_text('```json\n{"topic":"Birdwatching"}\n```')["topic"] == "Birdwatching"


def test_local_fallback_is_never_presented_as_live_trend(tmp_path: Path):
    result = TrendResearchService(tmp_path, FakePublishingService())._local_proposal("No live evidence")
    assert result.source == "Local catalog fallback"
    assert result.source_urls == ()
    assert "local" in result.buyer_angle.casefold()
    assert (tmp_path / "data" / "trend_research_reviews.json").is_file()


def test_quota_error_has_plain_english_recovery_step():
    error = urllib.error.HTTPError("https://example.invalid", 429, "quota", {}, None)
    note = _http_fallback_note(error)
    assert "quota is exhausted" in note
    assert "resets" in note
