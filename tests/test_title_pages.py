from publishing.title_pages import STYLE_LABELS, TitlePageSpec, puzzle_motif, select_style, theme_motif


def test_scramble_title_page_shows_fact_clues_not_separate_trivia():
    from io import BytesIO
    from pypdf import PdfReader
    from reportlab.pdfgen import canvas
    from publishing.title_pages import render_title_page

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    render_title_page(pdf, TitlePageSpec("The Curiosity Cabinet", puzzle_type="Word Scramble + Trivia"))
    pdf.save()
    content = PdfReader(buffer).pages[0].extract_text()
    assert "WORD SCRAMBLES + FACT CLUES" in content
    assert "WORD SCRAMBLE + TRIVIA" not in content
    assert "WORD" in content


def test_all_manual_styles_resolve():
    for key in STYLE_LABELS:
        assert select_style(TitlePageSpec("Test", style=key)) == key


def test_signature_and_large_print_automatic_rules():
    assert select_style(TitlePageSpec("Premium", edition="Signature Edition")) == "signature"
    assert select_style(TitlePageSpec("Easy", topic="Nature", large_print=True)) in {"modern_minimal", "classic_frame", "corner_art"}


def test_theme_and_puzzle_motifs_are_truthful():
    assert theme_motif("Space and Planets") == "space"
    assert theme_motif("Gardening and Homesteading") == "garden"
    assert theme_motif("Grade 5 Vocabulary") == "learning"
    assert puzzle_motif("Sudoku") == "number_grid"
    assert puzzle_motif("Cryptogram") == "cipher"
    assert puzzle_motif("Word Scramble + Trivia") == "word_tiles"
    assert puzzle_motif("Mixed Brain Games") == "mixed"
