from publishing.ease_of_use import home_summary, next_action


def _book(*, package="", production="Passed", statuses=None):
    return {
        "book_id": "book-1",
        "package_path": package,
        "metadata": {"production_status": production, "files": {}},
        "statuses": statuses or {},
    }


def test_empty_catalog_has_one_create_action():
    result = home_summary([])
    assert result["next"]["kind"] == "create"
    assert result["next"]["label"] == "Create your first book"


def test_attention_comes_before_a_new_book():
    # A broken package is intentionally surfaced before a green-field idea.
    result = next_action([_book(package="C:/missing-package"), _book(production="Passed")])
    assert result["kind"] == "review"
    assert "attention" in result["label"].casefold()


def test_uploaded_book_routes_to_marketplace_review():
    result = next_action([_book(package="C:/missing-package", statuses={"amazon": "Uploaded"})])
    assert result["kind"] == "publish"
    assert "marketplace" in result["label"].casefold()


def test_large_catalog_summary_stays_compact_and_deterministic():
    books = [_book(production="Passed") | {"book_id": f"book-{index}"} for index in range(1000)]
    result = home_summary(books)
    assert result["counts"]["Needs Review"] == 1000
    assert result["next"]["kind"] == "review"
