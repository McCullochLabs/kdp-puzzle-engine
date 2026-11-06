import hashlib
from publishing.puzzle_integrity import verify_manifest

def test_identity_cipher_cannot_be_a_valid_cryptogram(tmp_path):
    pdf=tmp_path/"fixture.pdf";pdf.write_bytes(b"test fixture")
    row={"number":1,"type":"cryptogram","puzzle_page":1,"solution_page":2,"mapping":{ch:ch for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"},"plaintext":"THE QUIET SKY","ciphertext":"THE QUIET SKY","solution_plaintext":"THE QUIET SKY"}
    manifest={"schema_version":1,"pdf_sha256":hashlib.sha256(pdf.read_bytes()).hexdigest(),"puzzle_count":1,"puzzles":[row]}
    assert verify_manifest(pdf,manifest,2)

def test_numeric_scramble_with_no_fact_answer_is_rejected(tmp_path):
    pdf=tmp_path/"fixture.pdf";pdf.write_bytes(b"test fixture")
    row={"number":1,"type":"scramble_trivia","puzzle_page":1,"solution_page":2,"word":"1234","scrambled":"4321","solution_word":"1234","fact_answer":"","solution_fact_answer":""}
    manifest={"schema_version":1,"pdf_sha256":hashlib.sha256(pdf.read_bytes()).hexdigest(),"puzzle_count":1,"puzzles":[row]}
    assert verify_manifest(pdf,manifest,2)
