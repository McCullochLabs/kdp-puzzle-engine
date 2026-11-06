from pathlib import Path

from PIL import Image

import cover
from background_generation.index import cover_approval_proof_path


def test_fullsize_draft_render_is_print_dimensions_without_approval_proof(tmp_path, monkeypatch):
    output = Path(tmp_path) / "book_cover_DRAFT.png"
    monkeypatch.setattr("sys.argv", [
        "cover.py", "--title", "Draft Book", "--subtitle", "Review only",
        "--author", "Jordan M. Slade", "--puzzle-count", "80",
        "--difficulty", "Easy", "--format-label", "LARGE PRINT WORD SEARCH",
        "--puzzle-type", "Word Search", "--palette", "nostalgia",
        "--style", "bold", "--out", str(output), "--draft-fullsize",
    ])

    cover.main()

    assert output.is_file()
    assert Image.open(output).size == (2550, 3300)
    assert not cover_approval_proof_path(output).exists()
    assert not output.with_name(output.stem + "_thumbnail.png").exists()
