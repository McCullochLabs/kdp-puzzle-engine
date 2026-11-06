import json
from pathlib import Path

from publishing.listing_intelligence import (
    GeminiCredentials,
    GeminiListingProvider,
    ListingIntelligence,
    ListingProviderError,
    listing_critic,
    validate_output,
    verified_facts,
    apply_listing_intelligence,
    local_fallback_content,
)
from publishing.payhip_product import tags_for


class Provider:
    provider_name="Mock Gemini"
    def __init__(self, result): self.result=result
    def available(self): return True
    def generate_listing(self, facts): return self.result


def book():
    return {"book_id":"brain","metadata":{"title":"Complete Brain Games","subtitle":"100 Mixed Puzzles","author":"Jordan M. Slade","puzzle_type":"Mixed Brain Games","puzzle_count":100,"difficulty":"Mixed","theme":"Brain Games","price":{"payhip":7.99}}}


def good():
    return {"subtitle":"100 mixed brain games","description":"Enjoy 100 mixed puzzle challenges with solutions included in this downloadable PDF.","keywords":["mixed brain games","logic puzzles for adults","printable puzzle collection"],"tags":["brain games","printable puzzles"],"marketing_hooks":["A screen-free brain break"],"short_ad_copy":"A focused puzzle break.","capcut_prompt":"Real cover, mixed puzzle collection, printable PDF."}


def test_local_critic_flags_generic_or_repeated_discovery_copy():
    value = good(); value["description"] = "Short."; value["keywords"] = ["complete brain games", "complete brain games"]
    notes = listing_critic(value, verified_facts(book(), "amazon"))
    assert any("brief" in note.casefold() for note in notes)
    assert any("repeat" in note.casefold() for note in notes)


def test_validator_rejects_hallucinated_count_and_format():
    facts=verified_facts(book(),"payhip"); value=good(); value["description"]="Over 150 puzzles in a paperback shipped to your door."
    valid, issues, _clean=validate_output(value,facts)
    assert not valid and len(issues)>=2


def test_scramble_listing_rejects_separate_trivia_promise(tmp_path):
    value = book()
    value["metadata"].update({"puzzle_type": "Word Scramble + Trivia", "puzzle_count": 60})
    facts = verified_facts(value, "amazon")
    assert "not separate trivia quizzes" in facts["scramble_content_promise"]
    draft = good()
    draft["description"] = "Enjoy 60 Word Scramble + Trivia puzzles with solutions."
    draft["tags"] = ["Trivia Puzzles", "Fact Clues"]
    assert not validate_output(draft, facts)[0]
    record = ListingIntelligence(Path(tmp_path), provider=Provider(draft)).generate(value, "amazon")
    assert "trivia puzzles" not in record["content"]["description"].casefold()
    assert "fact clue" in record["content"]["description"].casefold()
    assert "Trivia Puzzles" not in record["content"]["tags"]


def test_scramble_offline_copy_does_not_reuse_legacy_catalog_tags():
    value = book()
    value["metadata"].update({"puzzle_type": "Word Scramble + Trivia", "puzzle_count": 60,
                              "etsy_tags": ["Trivia Puzzles", "Paperback Book"],
                              "amazon_keywords": ["trivia quiz questions"]})
    content = local_fallback_content(value, verified_facts(value, "etsy"))
    assert "Trivia Puzzles" not in content["tags"]
    assert "Paperback Book" not in content["tags"]
    assert "trivia quiz questions" not in content["keywords"]


def test_payhip_scramble_tags_describe_fact_clues():
    tags = tags_for({"puzzle_type": "Word Scramble + Trivia", "theme": "General Knowledge & Curiosity"})
    assert any("fact clues" in tag for tag in tags)
    assert not any("trivia" in tag.casefold() for tag in tags)


def test_intelligence_caches_validated_provider_copy(tmp_path):
    engine=ListingIntelligence(Path(tmp_path),provider=Provider(good()))
    first=engine.generate(book(),"payhip",enabled=True); second=engine.generate(book(),"payhip",enabled=True)
    assert first["validation"]=="passed" and second["cached"] is True


def test_local_fallback_when_ai_disabled(tmp_path):
    record=ListingIntelligence(Path(tmp_path),provider=Provider(good())).generate(book(),"payhip",enabled=False)
    assert record["provider"]=="Deterministic local listing"


def test_gemini_provider_uses_current_structured_interactions_request(monkeypatch):
    captured = {}
    class Response:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def read(self):
            return json.dumps({
                "status": "completed",
                "steps": [{"type": "model_output", "content": [{"type": "text", "text": json.dumps(good())}]}],
            }).encode()
    def fake_open(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode())
        captured["timeout"] = timeout
        return Response()
    monkeypatch.setattr("publishing.listing_intelligence.urllib.request.urlopen", fake_open)
    provider = GeminiListingProvider(GeminiCredentials("test-key"), timeout=12)
    assert provider.generate_listing(verified_facts(book(), "payhip")) == good()
    assert captured["url"].endswith("/v1beta/interactions")
    assert captured["body"]["store"] is False
    assert captured["body"]["response_format"]["mime_type"] == "application/json"
    assert captured["body"]["generation_config"]["max_output_tokens"] == 1800


def test_local_copy_is_used_only_after_a_configured_provider_fails(tmp_path):
    class FailingProvider:
        provider_name = "Mock Gemini"
        def available(self): return True
        def generate_listing(self, _facts): raise ListingProviderError("service unavailable")
    record = ListingIntelligence(Path(tmp_path), provider=FailingProvider()).generate(book(), "payhip", enabled=True)
    assert record["provider"] == "Deterministic local listing"
    assert record["validation"] == "service unavailable"


def test_local_fallback_uses_specific_discovery_angles():
    vehicle = book(); vehicle["metadata"].update({"title": "Classic Cars Road Trip Word Search", "theme": "Vehicles and Automotive", "puzzle_type": "Word Search"})
    content = local_fallback_content(vehicle, verified_facts(vehicle, "amazon"))
    assert "vintage car brain games" in content["keywords"]
    assert len(content["keywords"]) == len(set(content["keywords"]))


def test_local_fallback_does_not_recycle_contributor_as_keyword():
    value = book()
    value["metadata"].update({"title": "Cat Lovers Large Print Sudoku", "theme": "Cats & Pets",
                              "puzzle_type": "Sudoku", "amazon_keywords": ["Jordan M Slade books"]})
    content = local_fallback_content(value, verified_facts(value, "amazon"))
    assert all("jordan" not in phrase.casefold() and "slade" not in phrase.casefold()
               for phrase in content["keywords"])
    assert any("cat" in phrase.casefold() for phrase in content["keywords"])


def test_cryptogram_keywords_cannot_promise_trivia():
    value = book()
    value["metadata"].update({"title": "American Heritage Cipher Challenge",
                              "theme": "History & Heritage", "puzzle_type": "Cryptogram",
                              "puzzle_count": 60})
    facts = verified_facts(value, "amazon")
    draft = good()
    draft["description"] = "Decode 60 history cryptograms with complete solutions."
    draft["keywords"] = ["american history puzzles", "usa trivia challenge", "code breaking games"]
    valid, issues, _clean = validate_output(draft, facts)
    assert not valid
    assert any("trivia" in issue.casefold() for issue in issues)


def test_sudoku_keywords_cannot_promise_word_finds():
    facts = verified_facts({"metadata": {
        "title": "Road Trip Sudoku", "theme": "Road Trips & Highways",
        "puzzle_type": "Sudoku", "puzzle_count": 100,
    }}, "amazon")
    draft = good()
    draft["description"] = "Solve 100 road-trip Sudoku puzzles with complete solutions."
    draft["keywords"] = ["road trip activity book", "highway travel word find"]
    valid, issues, _clean = validate_output(draft, facts)
    assert not valid
    assert any("different puzzle type" in issue.casefold() for issue in issues)


def test_apply_preserves_explicit_human_description():
    value = book(); value["metadata"]["description"] = "My approved human listing."
    value["metadata"]["human_edited_listing_fields"] = ["description"]
    record = {"provider": "Gemini", "validation": "passed", "content": good()}
    metadata, changed = apply_listing_intelligence(value["metadata"], record)
    assert metadata["description"] == "My approved human listing."
    assert "description" not in changed
