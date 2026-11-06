from publishing.editorial_readiness import (
    education_review, intentional_standard_signature_pair, overlap_report,
    nonword_package_issues, source_editorial_issues,
)
from publishing.production_gate import book_gate
import json
import hashlib


def _theme(title, *banks):
    return {"title": title, "puzzles": [{"words": list(bank)} for bank in banks]}


def test_grade_claim_requires_real_editorial_approval():
    source = _theme("Grade 5 Word Quest", ["SCOTLAND", "APPLE"])
    problems = education_review(source)
    assert any("not been editorially approved" in item for item in problems)
    assert any("SCOTLAND" in item for item in problems)
    source["educational_editorial_review"] = {"grade_appropriate": True}
    assert len(education_review(source)) == 1  # suspicious word still needs review


def test_overlap_uses_normalized_words_and_smaller_book_share():
    first = _theme("Cars", ["ROAD TRIP", "CAB", "WINCH"])
    second = _theme("Travel", ["ROAD-TRIP", "CAB", "TENT", "LAKE"])
    row = overlap_report(first, second)
    assert row["shared"] == 2
    assert row["share_of_smaller"] == 0.6667


def test_declared_standard_and_signature_pair_is_recognized():
    standard = {"title": "Faithful Words Word Search", "series": "Faithful Words",
                "detected_topic": "Bible and Faith"}
    signature = {"title": "Faithful Words Signature Edition",
                 "series": "Faithful Words Signature Editions",
                 "detected_topic": "Bible and Faith",
                 "signature_edition": {"enabled": True}}
    assert intentional_standard_signature_pair(standard, signature)
    signature["detected_topic"] = "Gardening"
    assert not intentional_standard_signature_pair(standard, signature)


def test_publishing_gate_shows_specific_editorial_hold(tmp_path):
    path = tmp_path / "book.json"
    path.write_text(json.dumps({"title": "Grade 5", "author": "Author", "puzzles": [{"words": ["APPLE"]}],
                                "quality_review": {"production_ready": False,
                                                   "editorial_hold_reason": "Review the Grade 5 word pool."}}), encoding="utf-8")
    result = book_gate({"source_key": str(path), "metadata": {"title": "Grade 5", "author": "Author"}})
    assert not result["ready"]
    assert "Review the Grade 5 word pool." in result["blockers"]
    assert source_editorial_issues({"source_key": str(path)}) == ["Review the Grade 5 word pool."]


def test_printed_cryptogram_hold_requires_matching_pdf_audit(tmp_path):
    package = tmp_path / "out" / "cipher"
    record = package / "04_REVIEW_AND_RECORDS" / "PACKAGE_SOURCE_RECORD.json"
    interior = package / "01_PRINT_UPLOADS" / "interior.pdf"
    report = tmp_path / "reports" / "NONWORD_EDITORIAL_SALE_READINESS.json"
    record.parent.mkdir(parents=True)
    interior.parent.mkdir(parents=True)
    report.parent.mkdir(parents=True)
    record.write_text(json.dumps({"puzzle_type": "Cryptogram"}), encoding="utf-8")
    interior.write_bytes(b"printed content")
    book = {"package_path": str(package)}
    assert "Run the printed-content" in nonword_package_issues(book)[0]
    report.write_text(json.dumps({"books": [{"folder": str(package),
        "interior_sha256": hashlib.sha256(interior.read_bytes()).hexdigest(),
        "issues": ["Templated messages need rewriting."]}]}), encoding="utf-8")
    assert nonword_package_issues(book) == ["Templated messages need rewriting."]
    interior.write_bytes(b"changed content")
    assert "after this book changed" in nonword_package_issues(book)[0]
