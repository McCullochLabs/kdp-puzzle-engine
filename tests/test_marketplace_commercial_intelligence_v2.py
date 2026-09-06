import hashlib
from pathlib import Path

from PIL import Image
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from publishing.commercial_intelligence import commercial_assessment
from publishing.commercial_profiles import (
    MARKETPLACE_PROFILES,
    PROFILE_VERSION,
    PUZZLE_PROFILES,
    commercial_warnings,
    infer_archetypes,
    marketplace_fit,
    mini_theme_capacity,
    profile_snapshot,
    puzzle_format_fit,
    unsupported_metric_keys,
)
from publishing.listing_intelligence import local_fallback_content, verified_facts
from publishing.marketplace_merchandising import build_etsy_merchandising_kit, etsy_merchandising_plan
from publishing.commercial_profiles import idea_commercial_guidance


def metadata(**changes):
    value = {
        "title": "1970s Memory Lane Word Search",
        "subtitle": "48 large-print puzzles for seniors",
        "theme": "1970s Nostalgia",
        "puzzle_type": "Word Search",
        "puzzle_count": 48,
        "words_per_puzzle": 12,
        "large_print": True,
        "audience": "Seniors",
        "files": {"print_interior": "interior.pdf", "print_cover": "cover.pdf", "printable_pdf": "download.pdf"},
    }
    value.update(changes)
    return value


def test_profiles_are_versioned_and_cover_every_supported_type_and_market():
    snapshot = profile_snapshot()
    assert snapshot["version"] == PROFILE_VERSION
    assert set(PUZZLE_PROFILES) == {"word_search", "sudoku", "cryptogram", "scramble_trivia", "mixed"}
    assert {"amazon", "etsy", "payhip", "barnes_noble", "ingram", "lulu", "bookvault", "direct"} <= set(MARKETPLACE_PROFILES)
    forbidden = ("search_volume", "monthly_sales", "guaranteed_profit", "rank_probability")
    rendered = str(snapshot).casefold()
    assert not any(term in rendered for term in forbidden)
    assert unsupported_metric_keys(snapshot) == []


def test_fake_metric_fields_are_rejected_even_when_nested():
    assert unsupported_metric_keys({"listing": {"search_volume": 9000}, "guaranteed_profit": True}) == ["guaranteed_profit", "search_volume"]


def test_archetype_and_format_fit_are_explainable_not_demand_predictions():
    archetypes = infer_archetypes(metadata())
    assert [row["id"] for row in archetypes[:2]] == ["senior_large_print", "nostalgia"]
    fit = puzzle_format_fit(metadata())
    assert fit["recommended"][0]["puzzle_type"] == "word_search"
    assert "not demand or sales" in fit["notice"]


def test_marketplace_fit_and_commercial_assessment_are_market_specific():
    meta = metadata()
    fit = marketplace_fit(meta)
    assert fit["amazon"]["fit"] == "Strong Fit"
    assert fit["etsy"]["fit"] == "Strong Fit"
    result = commercial_assessment({"metadata": meta})
    assert result["commercial_profile_version"] == PROFILE_VERSION
    assert len(result["marketplace_strategies"]["amazon"]["amazon_keyword_phrases"]) == 7
    assert len(result["marketplace_strategies"]["amazon"]["category_suggestions"]) == 3
    assert len(result["marketplace_strategies"]["etsy"]["etsy_tags"]) == 13
    assert "NO PHYSICAL PRODUCT" in result["marketplace_strategies"]["etsy"]["digital_disclosure"]
    assert result["marketplace_strategies"]["amazon"]["description_strategy"] != result["marketplace_strategies"]["etsy"]["description_strategy"]
    assert result["marketplace_strategies"]["payhip"]["seo_title"]
    assert result["marketplace_strategies"]["ingram"]["subject_suggestions"]


def test_puzzle_specific_weaknesses_are_reported():
    sudoku = metadata(title="Space Sudoku", subtitle="100 Sudoku puzzles", theme="Space", puzzle_type="Sudoku", puzzle_count=100, large_print=False)
    assert any("cosmetic" in note for note in commercial_warnings(sudoku))
    mixed = metadata(title="Variety Brain Games", puzzle_type="Mixed Brain Games", theme="General")
    assert any("Cohesion" in note for note in commercial_warnings(mixed))
    cryptogram = metadata(title="History Cryptograms", puzzle_type="Cryptogram", theme="History")
    assert any("Rights" in note for note in commercial_warnings(cryptogram))


def test_micro_theme_capacity_reports_breadth_pressure_and_concentration():
    result = mini_theme_capacity(metadata(mini_themes={"Music": ["a"] * 36, "Fashion": ["b"] * 12, "Travel": ["c"] * 12}))
    assert result["breadth"] == 3
    assert result["fallback_concentration_risk"] is True
    assert result["mini_themes"][0]["supportable_puzzles"] == 3


def test_local_fallback_copy_differs_by_marketplace_and_discloses_digital():
    book = {"book_id": "one", "metadata": metadata()}
    amazon = local_fallback_content(book, verified_facts(book, "amazon"))["description"]
    etsy = local_fallback_content(book, verified_facts(book, "etsy"))["description"]
    payhip = local_fallback_content(book, verified_facts(book, "payhip"))["description"]
    ingram = local_fallback_content(book, verified_facts(book, "ingram"))["description"]
    assert len({amazon, etsy, payhip, ingram}) == 4
    assert "NO PHYSICAL PRODUCT" in etsy
    assert "downloadable PDF" in payhip
    assert "professionally organized" in ingram


def _sha(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_etsy_merchandising_uses_real_approved_product_without_overwriting(tmp_path):
    uploads = tmp_path / "01_PRINT_UPLOADS"; previews = tmp_path / "03_PREVIEWS"
    uploads.mkdir(); previews.mkdir()
    interior = uploads / "interior.pdf"
    pdf = canvas.Canvas(str(interior), pagesize=letter)
    for heading in ("PUZZLE 1", "PUZZLE 2", "SOLUTIONS"):
        pdf.drawString(100, 700, heading); pdf.drawString(100, 660, "REAL COMPLETED PRODUCT PAGE"); pdf.showPage()
    pdf.save()
    cover = previews / "front_cover.png"; Image.new("RGB", (1200, 1600), "#20304f").save(cover)
    before = (_sha(interior), _sha(cover))
    target = build_etsy_merchandising_kit(tmp_path, metadata(), approval_verifier=lambda path: (True, "approved", {"asset_id": "approved-1"}))
    assert len(list(target.glob("*.png"))) == 10
    assert (target / "ETSY_MERCHANDISING_MANIFEST.json").is_file()
    assert before == (_sha(interior), _sha(cover))


def test_etsy_merchandising_fails_closed_for_unapproved_cover(tmp_path):
    uploads = tmp_path / "01_PRINT_UPLOADS"; previews = tmp_path / "03_PREVIEWS"
    uploads.mkdir(); previews.mkdir(); (uploads / "interior.pdf").write_bytes(b"pdf")
    Image.new("RGB", (20, 20)).save(previews / "front_cover.png")
    try:
        build_etsy_merchandising_kit(tmp_path, metadata(), approval_verifier=lambda path: (False, "not approved", {}))
    except ValueError as exc:
        assert "not approved" in str(exc)
    else:
        raise AssertionError("Unapproved cover was accepted")


def test_merchandising_plan_is_truthful_and_does_not_imply_shipment():
    plan = etsy_merchandising_plan(metadata())
    assert len(plan["image_plan"]) == 10
    assert plan["verified_facts"]["puzzle_count"] == 48
    assert "NO PHYSICAL PRODUCT" in plan["digital_disclosure"]


def test_controlled_85_concept_stress_never_creates_or_claims_fake_metrics(tmp_path):
    concepts = {
        "word_search": [f"{topic} word search for adults" for topic in ("1970s nostalgia", "gardening", "national parks", "road trips", "birds") for _ in range(5)],
        "sudoku": [f"{variant} Sudoku for seniors" for variant in ("large print", "progressive", "letter", "shape", "expert") for _ in range(3)],
        "cryptogram": [f"{topic} cryptogram collection" for topic in ("history", "inspiration", "mystery", "nostalgia", "faith") for _ in range(3)],
        "scramble_trivia": [f"{topic} scramble and trivia" for topic in ("birthdays", "holidays", "classic cars", "camping", "travel") for _ in range(3)],
        "mixed": [f"{topic} mixed brain games" for topic in ("family", "nostalgia", "travel", "seniors", "hobbies") for _ in range(3)],
    }
    total = 0
    for kind, ideas in concepts.items():
        for idea in ideas:
            result = idea_commercial_guidance(idea)
            total += 1
            assert result["best_format"]["puzzle_type"] == kind
            assert unsupported_metric_keys(result) == []
            assert "no demand" in result["notice"].casefold()
    assert total == 85
    assert list(tmp_path.iterdir()) == []


def test_representative_marketplace_outputs_differ_for_every_puzzle_type():
    for kind in ("Word Search", "Sudoku", "Cryptogram", "Word Scramble + Trivia", "Mixed Brain Games"):
        book = {"book_id": kind, "metadata": metadata(title=f"Travel {kind}", theme="Travel", puzzle_type=kind)}
        outputs = [local_fallback_content(book, verified_facts(book, platform))["description"] for platform in ("amazon", "etsy", "payhip", "ingram")]
        assert len(set(outputs)) == 4
