from pathlib import Path

from publishing.package_layout import (
    FOLDERS,
    initialize_package_layout,
    marketplace_handoff_folder,
    missing_core_package_files,
    release_contract,
    package_file,
)


def test_new_package_layout_sorts_files_and_creates_handoffs_only_when_needed(tmp_path):
    package = Path(tmp_path) / "book"
    package.mkdir()
    initialize_package_layout(package)
    assert package_file(package, "interior.pdf", for_write=True) == package / FOLDERS["print"] / "interior.pdf"
    assert package_file(package, "KDP_LISTING_KIT.txt", for_write=True) == package / FOLDERS["listing"] / "KDP_LISTING_KIT.txt"
    assert package_file(package, "front_cover.png", for_write=True) == package / FOLDERS["previews"] / "front_cover.png"
    assert not (package / FOLDERS["handoffs"]).exists()
    assert marketplace_handoff_folder(package, "kdp", create=True) == package / FOLDERS["handoffs"] / "kdp"


def test_core_package_check_reads_both_structured_and_legacy_packages(tmp_path):
    structured = Path(tmp_path) / "structured"; structured.mkdir(); initialize_package_layout(structured)
    for name in ("interior.pdf", "front_cover.png", "kdp_full_wrap.pdf"):
        package_file(structured, name, for_write=True).write_bytes(b"ready")
    assert missing_core_package_files(structured) == []

    legacy = Path(tmp_path) / "legacy"; legacy.mkdir()
    for name in ("interior.pdf", "front_cover.png", "kdp_full_wrap.pdf"):
        (legacy / name).write_bytes(b"ready")
    assert missing_core_package_files(legacy) == []


def test_release_contract_has_one_clear_missing_file_list(tmp_path):
    package = Path(tmp_path) / "book"; package.mkdir(); initialize_package_layout(package)
    for name in ("interior.pdf", "front_cover.png", "kdp_full_wrap.pdf", "KDP_LISTING_KIT.txt"):
        package_file(package, name, for_write=True).write_bytes(b"ready")
    result = release_contract(package)
    assert not result["ready"]
    assert set(result["missing"]) == {"PUBLISHER_PREFLIGHT.txt", "PACKAGE_SOURCE_RECORD.json", "one proof record (PRODUCTION_PROOF_GATE.txt or proof_review/PROOF_REVIEW.txt)", "current production-approved cover proof: cover approval proof is missing"}


def test_legacy_flat_package_stays_readable_and_is_not_reorganized(tmp_path):
    package = Path(tmp_path) / "old_book"
    package.mkdir()
    legacy = package / "interior.pdf"
    legacy.write_bytes(b"existing")
    assert package_file(package, "interior.pdf") == legacy
    assert package_file(package, "KDP_LISTING_KIT.txt", for_write=True) == package / "KDP_LISTING_KIT.txt"
