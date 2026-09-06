import json
from types import SimpleNamespace

from publishing.catalog_intelligence import CatalogIntelligence, CatalogRecord, contains_fake_market_metrics


class FakeDB:
    def __init__(self, books): self.books = books
    def list_books(self): return list(self.books)
    def get_book(self, book_id): return next((row for row in self.books if row["book_id"] == book_id), None)


def book(tmp_path, book_id, title, topic, kind="word_search", series="", package=""):
    source = tmp_path / f"{book_id}.json"
    source.write_text(json.dumps({"title": title, "author": "Jordan M. Slade", "puzzles": [{"words": ["SUN"]}]}), encoding="utf-8")
    return {"book_id": book_id, "source_key": str(source), "package_path": package,
            "statuses": {"amazon": "Not Prepared"}, "metadata": {
                "title": title, "subtitle": f"Puzzles about {topic}", "detected_topic": topic,
                "puzzle_type_id": kind, "audience": "Adults", "series": series,
                "puzzle_count": 48, "production_status": "Passed",
                "cover_art_id": f"art-{book_id}" if package else "",
            }}


def engine(tmp_path, books):
    return CatalogIntelligence(SimpleNamespace(project=tmp_path, db=FakeDB(books)))


def test_catalog_view_and_topic_coverage(tmp_path):
    books = [book(tmp_path, "a", "Garden Calm", "Gardening"), book(tmp_path, "b", "Garden Trivia", "Gardening", "scramble_trivia")]
    catalog = engine(tmp_path, books).catalog(); coverage = engine(tmp_path, books).coverage_map(catalog)
    assert len(catalog) == 2
    assert coverage["Gardening"]["books"] == 2
    assert set(coverage["Gardening"]["formats"]) == {"word_search", "scramble_trivia"}
    assert "sudoku" in coverage["Gardening"]["missing_formats"]


def test_differentiation_is_transparent_and_series_aware():
    common = dict(subtitle="48 garden puzzles", puzzle_type="word_search", topic="Gardening", audience="Adults",
                  production_state="Passed", marketplace_state={}, puzzle_count=48, package_path="",
                  cover_identity="", listing_positioning="", published_or_released=False)
    left = CatalogRecord("a", "Garden Lovers Word Search", series="Garden Collection", **common)
    right = CatalogRecord("b", "Garden Lovers Word Search", series="Garden Collection", **common)
    result = CatalogIntelligence.differentiation(left, right)
    assert result["label"] == "Same Series — Intentional"
    assert result["evidence"]["title_overlap"] == 1.0


def test_opportunities_rank_ready_distinct_local_work_first(tmp_path):
    ready = book(tmp_path, "ready", "Backyard Garden Escape", "Gardening")
    blocked = book(tmp_path, "blocked", "Backyard Garden Escape Two", "Gardening")
    blocked_source = json.loads(open(blocked["source_key"], encoding="utf-8").read())
    blocked_source["quality_review"] = {"production_ready": False}
    open(blocked["source_key"], "w", encoding="utf-8").write(json.dumps(blocked_source))
    rows = engine(tmp_path, [ready, blocked]).opportunities()
    assert rows[0].book_id == "ready"
    assert rows[0].production_readiness == "ready"
    assert rows[1].missing_work


def test_catalog_gap_and_series_extension_are_explained(tmp_path):
    books = [book(tmp_path, "a", "Road Trip Classics", "Road Trips", series="Road Trip Collection")]
    opportunity = engine(tmp_path, books).opportunities(view="series")[0]
    assert "Extend Road Trip Collection" in opportunity.series_opportunity
    assert any("tracked book" in reason for reason in opportunity.reasons)


def test_no_fake_market_metrics_are_emitted(tmp_path):
    payload = engine(tmp_path, [book(tmp_path, "a", "Distinct Nature Puzzles", "Nature")]).analyze()
    assert contains_fake_market_metrics(payload) is False


def test_similarity_candidate_index_avoids_unrelated_pair_noise(tmp_path):
    books = [book(tmp_path, "a", "Garden Lovers Word Search", "Gardening"),
             book(tmp_path, "b", "Garden Lover Word Puzzles", "Gardening"),
             book(tmp_path, "c", "Deep Space Cipher", "Space")]
    findings = engine(tmp_path, books).similarity_findings()
    assert any({row["left"], row["right"]} == {"a", "b"} for row in findings)
    assert all("c" not in {row["left"], row["right"]} for row in findings)
