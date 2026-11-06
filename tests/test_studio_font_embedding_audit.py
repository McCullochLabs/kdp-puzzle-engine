import pytest
from puzzle_book_studio import make_interior
from tools.audit_grade7_production import embedded_text_fonts

@pytest.mark.parametrize("kind",["Sudoku","Cryptogram","Word Scramble + Trivia","Mixed Brain Games"])
def test_all_used_studio_text_fonts_are_embedded(kind,tmp_path):
    pdf=tmp_path/"interior.pdf"
    make_interior(kind,"Embedded Type","Complete answers","Jordan M. Slade",6,"Easy",9124,pdf)
    assert not embedded_text_fonts(pdf)["unembedded_fonts"]

def test_cover_cryptogram_example_matches_its_answer_slots():
    import codecs,inspect,cover
    source=inspect.getsource(cover)
    assert "GUR FXL VF JVQR" in source
    plaintext=codecs.decode("GUR FXL VF JVQR","rot_13")
    assert [len(w) for w in plaintext.split()]==[len(w) for w in "___ ___ __ ____".split()]
    assert plaintext=="THE SKY IS WIDE"
