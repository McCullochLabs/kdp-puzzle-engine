from __future__ import annotations

from publishing.capability_audit import ProductionCapabilityAudit

from test_business_automation import _Service, _book


def test_capability_audit_reports_observed_ready_formats(tmp_path):
    book = _book(tmp_path, "sudoku", "Relaxing Sudoku", "Relaxation")
    book["metadata"]["puzzle_type"] = "Sudoku"

    rows = ProductionCapabilityAudit(_Service(tmp_path, [book])).evaluate()

    sudoku = next(row for row in rows if row.name == "Sudoku")
    assert sudoku.status == "GREEN"
    assert sudoku.confidence == "observed"
    assert "1 locally production-ready" in sudoku.evidence[0]


def test_capability_audit_does_not_claim_unobserved_formats_work(tmp_path):
    rows = ProductionCapabilityAudit(_Service(tmp_path, [])).evaluate()

    word_search = next(row for row in rows if row.name == "Word Search")
    assert word_search.status == "UNKNOWN"
    assert word_search.confidence == "insufficient_evidence"
    assert word_search.next_action == "Run a controlled local package test"
