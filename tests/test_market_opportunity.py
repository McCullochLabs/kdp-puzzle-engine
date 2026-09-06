from __future__ import annotations

import json

from publishing.market_opportunity import MarketOpportunityService

from test_business_automation import _Service, _book


def test_refresh_persists_only_local_derived_opportunities(tmp_path):
    first = _book(tmp_path, "a", "Space Word Search", "Space")
    service = _Service(tmp_path, [first])

    rows = MarketOpportunityService(service).refresh()

    assert len(rows) == 1
    assert rows[0].book_id == "a"
    assert rows[0].evidence_kind == "DERIVED"
    assert rows[0].status == "needs_review"
    saved = json.loads((tmp_path / "data" / "market_opportunities.json").read_text(encoding="utf-8"))
    assert saved["score_notice"].startswith("Local derived")
    assert saved["opportunities"][0]["book_id"] == "a"
    assert "sales" not in " ".join(saved["opportunities"][0]["evidence"]).casefold()


def test_explicit_review_is_preserved_across_refresh(tmp_path):
    service = _Service(tmp_path, [_book(tmp_path, "a")])
    engine = MarketOpportunityService(service)
    row = engine.refresh()[0]

    assert engine.review(row.opportunity_id, "approved") is True
    assert engine.refresh()[0].status == "approved"


def test_load_returns_empty_for_bad_or_missing_file(tmp_path):
    service = _Service(tmp_path, [])
    engine = MarketOpportunityService(service)
    assert engine.load() == []
    engine.path.parent.mkdir()
    engine.path.write_text("not json", encoding="utf-8")
    assert engine.load() == []
