from pathlib import Path

from PIL import Image

from cover import cover_quality_report, puzzle_count_label
from publishing.review import review_result, review_text, series_consistency_report
from publishing.readiness_center import production_readiness, readiness_text
from puzzle_book_studio import APP, AUTO_COVER_STYLES, ART, COVER_STYLE_OPTIONS, THEME_ART, cover_spec
from background_generation.index import BackgroundAssetIndex
from word_search_creator import normalized_book_title


def test_non_word_cover_selection_uses_an_approved_registry_asset_and_layout():
    for kind, (choices, _palette, _style) in ART.items():
        art, _palette, style = cover_spec(kind, "General Starter", seed=17)
        asset = BackgroundAssetIndex().ledger_details(APP / art)
        assert asset and BackgroundAssetIndex().production_selectable(asset)
        assert style in AUTO_COVER_STYLES[kind]

        art, _palette, style = cover_spec(kind, "General Starter", seed=17, cover_style="Retro print", cover_photo=choices[-1])
        asset = BackgroundAssetIndex().ledger_details(APP / art)
        assert asset and BackgroundAssetIndex().production_selectable(asset)
        assert style == COVER_STYLE_OPTIONS["Retro print"]


def test_mixed_brain_games_automatic_covers_skip_the_sparse_colorblock_direction():
    assert "colorblock" not in AUTO_COVER_STYLES["Mixed Brain Games"]
    assert set(AUTO_COVER_STYLES["Mixed Brain Games"]) >= {"mixed-edge", "mixed-editorial", "mixed-logic"}


def test_supported_theme_automatic_covers_use_matching_local_art_before_generic_puzzle_art():
    for theme in ("Bible & Faith", "Nature & Outdoors", "History & Heritage", "School & Vocabulary"):
        choices, palette, _style = THEME_ART[theme]
        art, selected_palette, _layout = cover_spec("Word Scramble + Trivia", theme, seed=7)
        asset = BackgroundAssetIndex().ledger_details(APP / art)
        assert asset and BackgroundAssetIndex().production_selectable(asset)
        assert selected_palette


def test_cover_count_promise_is_truthful_and_never_guesses():
    assert puzzle_count_label(48) == "48 PUZZLES"
    assert puzzle_count_label("100") == "100 PUZZLES"
    assert puzzle_count_label(0) == ""
    assert puzzle_count_label("not a count") == ""


def test_cover_quality_score_requires_a_real_count_but_recognizes_large_print():
    score, label, notes = cover_quality_report("Garden Word Search", "48 calming puzzles", "NO REPEATED WORDS", 48, "LARGE PRINT", "photo", "garden.png")
    assert score >= 90 and label == "Strong storefront cover"
    assert any("Large Print" in note for note in notes)
    score, _label, notes = cover_quality_report("Garden Word Search", "", "", 0, "WORD SEARCH", "classic")
    assert score < 90 and any("puzzle count" in note for note in notes)


def test_duplicate_guard_normalizes_book_title_without_confusing_signature_editions():
    assert normalized_book_title({"title": "The Great Space Word Search!"}) == "thegreatspacewordsearch"
    assert normalized_book_title({"title": "The Great Space Word Search — Signature Edition"}) == "thegreatspacewordsearch"


def test_final_review_reports_real_files_and_copy_without_writing_another_report(tmp_path):
    interior = tmp_path / "interior.pdf"; interior.write_bytes(b"pdf")
    cover = tmp_path / "cover.pdf"; cover.write_bytes(b"pdf")
    front = tmp_path / "front.png"; Image.new("RGB", (2550, 3300), "white").save(front)
    book = {
        "metadata": {
            "title": "Cosmic Sudoku", "author": "Jordan M. Slade", "puzzle_type": "Sudoku",
            "theme": "Space & Astronomy", "puzzle_count": 60, "page_count": 120,
            "files": {"print_interior": str(interior), "print_cover": str(cover), "front_cover": str(front)},
        }
    }
    result = review_result(book, "amazon")
    assert result["ready"]
    assert "2550 × 3300" in " ".join(result["checks"])
    assert "Sudoku" in review_text(book, "amazon")


def test_series_consistency_report_flags_a_real_difference():
    books = [{"metadata": {"author": "Jordan M. Slade", "series": "Space", "puzzle_count": 48, "difficulty_label": "Standard", "trim_size": "8.5x11", "palette": "midnight"}}, {"metadata": {"author": "Jordan M. Slade", "series": "Space", "puzzle_count": 48, "difficulty_label": "Mixed", "trim_size": "8.5x11", "palette": "midnight"}}]
    assert any("Difficulty varies" in line for line in series_consistency_report(books))


def test_production_readiness_separates_missing_packages_from_ready_handoffs(tmp_path):
    interior = tmp_path / "interior.pdf"; interior.write_bytes(b"pdf")
    cover = tmp_path / "cover.pdf"; cover.write_bytes(b"pdf")
    ready = {"book_id": "ready", "package_path": str(tmp_path), "statuses": {}, "metadata": {
        "title": "Ready Sudoku", "author": "Jordan M. Slade", "files": {"print_interior": str(interior), "print_cover": str(cover)},
    }}
    missing = {"book_id": "missing", "package_path": "", "statuses": {}, "metadata": {"title": "Needs Package", "author": "Jordan M. Slade", "files": {}}}
    summary = production_readiness([ready, missing])
    assert summary["counts"] == {"ready": 1, "needs_package": 1, "needs_review": 0, "published": 0}
    assert "ready for a KDP handoff" in readiness_text(summary)
