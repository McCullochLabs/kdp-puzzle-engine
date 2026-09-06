"""Phase 5 operator-status tests: plain-language read model only."""
from __future__ import annotations

from publishing.database import PublishingDatabase
from publishing.operator_status import OperatorStatusService


def _book(book_id="book", package=""):
    return {"book_id": book_id, "package_path": package, "statuses": {"amazon": "Not Prepared"}, "metadata": {"title": "Garden Plan"}}


def test_legacy_book_is_clearly_labeled_without_fake_modern_plan(tmp_path):
    status = OperatorStatusService(tmp_path).product_status(_book())
    assert status.headline_status == "legacy"
    assert "no modern Book Plan" in status.message


def test_uploaded_and_published_marketplace_history_remains_primary(tmp_path):
    service = OperatorStatusService(tmp_path)
    uploaded = _book(); uploaded["statuses"]["amazon"] = "Uploaded"
    published = _book(); published["statuses"]["amazon"] = "Published"
    assert service.product_status(uploaded).headline_status == "uploaded"
    assert service.product_status(published).headline_status == "published"


def test_explicit_final_local_review_is_persisted_separately_from_marketplace_state(tmp_path):
    db = PublishingDatabase(tmp_path / "books.db")
    db.upsert_book("book", "fixture", {"title": "Garden Plan"}, "C:/fixture-package")
    record = db.record_final_local_review("book", "proof-1", "C:/fixture-package", "looked at every page")
    assert record["reviewer_source"] == "human"
    assert db.final_local_review("book", "proof-1", "C:/fixture-package")["note"] == "looked at every page"
    assert db.marketplace_records("book")["amazon"]["status"] == "Not Prepared"


def test_proof_status_requires_final_review_before_platform_preview(tmp_path):
    db = PublishingDatabase(tmp_path / "books.db")
    db.upsert_book("book", "fixture", {"title": "Garden Plan"}, "C:/fixture-package")
    service = OperatorStatusService(tmp_path, db)
    book = db.get_book("book")
    from word_intelligence.book_planning import BookPlan
    plan = BookPlan("plan", "", "sudoku", ["general"], {"puzzle_count": 10, "items_per_puzzle": 1}, 7, "strict_verified", "allow_all", "any", "proof")
    proof = {"proof_id": "proof-1", "package_id": "package", "status": "ready_for_platform_preview"}
    # A Sudoku plan does not depend on an editorial fixture, so this proves
    # the status transition logic independently of content sources.
    assert service.product_status(book, plan=plan, proof=proof).headline_status == "ready_for_final_local_review"
    db.record_final_local_review("book", "proof-1", "C:/fixture-package")
    assert service.product_status(book, plan=plan, proof=proof).headline_status == "ready_for_platform_preview"
