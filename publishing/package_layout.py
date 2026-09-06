"""One clear, low-clutter folder layout for every newly created book package."""
from __future__ import annotations

from pathlib import Path


FOLDERS = {
    "print": "01_PRINT_UPLOADS",
    "listing": "02_LISTING_INFORMATION",
    "previews": "03_PREVIEWS",
    "records": "04_REVIEW_AND_RECORDS",
    "handoffs": "05_MARKETPLACE_HANDOFFS",
}

FILE_GROUPS = {
    "interior.pdf": "print",
    "kdp_full_wrap.pdf": "print",
    "front_cover.png": "previews",
    "front_cover_thumbnail.png": "previews",
    "kdp_full_wrap_preview.png": "previews",
    "KDP_LISTING_KIT.txt": "listing",
    "KDP_UPLOAD_CHECKLIST.txt": "listing",
    "KDP_COMPLIANCE_REPORT.txt": "listing",
}

# These are the minimum files that prove a local package reached the print
# handoff point.  Keep the check here so the Recovery Center, catalog, and
# future screens cannot disagree about modern versus legacy folders.
CORE_PACKAGE_FILES = ("interior.pdf", "front_cover.png", "kdp_full_wrap.pdf")
RELEASE_CONTRACT_FILES = CORE_PACKAGE_FILES + (
    "KDP_LISTING_KIT.txt",
    "PUBLISHER_PREFLIGHT.txt",
    "PACKAGE_SOURCE_RECORD.json",
)
RELEASE_PROOF_OPTIONS = ("PRODUCTION_PROOF_GATE.txt", "proof_review/PROOF_REVIEW.txt")


def package_file(folder: str | Path, filename: str, *, for_write: bool = False) -> Path:
    """Return a structured path, while continuing to read legacy flat packages."""
    root = Path(folder)
    group = FILE_GROUPS.get(filename, "records")
    structured = root / FOLDERS[group] / filename
    if for_write:
        # Existing packages remain untouched and readable in their original
        # flat layout. New generators call initialize_package_layout first.
        if (root / FOLDERS["print"]).is_dir():
            structured.parent.mkdir(parents=True, exist_ok=True)
            return structured
        root.mkdir(parents=True, exist_ok=True)
        return root / filename
    return structured if structured.exists() else root / filename


def missing_core_package_files(folder: str | Path) -> list[str]:
    """List missing core artifacts while supporting both package layouts."""
    return [name for name in CORE_PACKAGE_FILES if not package_file(folder, name).is_file()]


def has_core_package_files(folder: str | Path) -> bool:
    return not missing_core_package_files(folder)


def release_contract(folder: str | Path, *, proof_files: tuple[str, ...] = RELEASE_PROOF_OPTIONS) -> dict:
    """One layout-aware final contract shared by every puzzle package."""
    required = RELEASE_CONTRACT_FILES
    missing = [name for name in required if not package_file(folder, name).is_file()]
    # Word Search produces a human proof bundle; other puzzle creators write
    # a formal proof gate. Either proves the same release-review step ran.
    if proof_files and not any(package_file(folder, name).is_file() for name in proof_files):
        missing.append("one proof record (" + " or ".join(proof_files) + ")")
    front = package_file(folder, "front_cover.png")
    if front.is_file():
        try:
            from background_generation.index import verify_rendered_cover_approval
            approved, reason, _proof = verify_rendered_cover_approval(front)
        except Exception as exc:
            approved, reason = False, f"cover approval could not be verified ({type(exc).__name__})"
        if not approved:
            missing.append("current production-approved cover proof: " + reason)
    return {"ready": not missing, "required": required, "missing": missing}


def package_root_for_artifact(path: str | Path) -> Path:
    """Find a package root from a saved stage artifact in either layout."""
    value = Path(path)
    parent = value.parent if value.suffix else value
    return parent.parent if parent.name in FOLDERS.values() else parent


def package_subfolder(folder: str | Path, group: str, *, create: bool = False) -> Path:
    root = Path(folder)
    target = root / FOLDERS[group]
    if create:
        target.mkdir(parents=True, exist_ok=True)
    return target


def initialize_package_layout(folder: str | Path) -> None:
    """Create the four normal book folders; handoffs appear only when requested."""
    root = Path(folder)
    for group in ("print", "listing", "previews", "records"):
        (root / FOLDERS[group]).mkdir(parents=True, exist_ok=True)


def proof_folder(folder: str | Path, *, create: bool = False) -> Path:
    target = package_subfolder(folder, "records", create=create) / "proof_review"
    if create:
        target.mkdir(parents=True, exist_ok=True)
    legacy = Path(folder) / "proof_review"
    return target if target.exists() or not legacy.exists() else legacy


def marketplace_handoff_folder(folder: str | Path, marketplace: str, *, create: bool = False) -> Path:
    root = Path(folder)
    target = package_subfolder(root, "handoffs", create=create) / marketplace
    if create:
        target.mkdir(parents=True, exist_ok=True)
        return target
    legacy = root / marketplace
    return target if target.exists() or not legacy.exists() else legacy


def package_layout_readme(title: str) -> str:
    return f"""{title}
{'=' * max(24, len(title))}

START HERE
• 01_PRINT_UPLOADS — the interior and KDP cover PDF. Upload these only to Amazon KDP.
• 02_LISTING_INFORMATION — copy-ready title, description, keywords, categories, and price guidance.
• 03_PREVIEWS — front-cover and full-wrap images for your own review. Do not upload these as print files.
• 04_REVIEW_AND_RECORDS — one place for automated checks, proof notes, and asset records.
• 05_MARKETPLACE_HANDOFFS — Payhip files are created with a completed package. Other marketplace folders appear when you choose Prepare in Publishing Center.

Nothing in this package is published automatically. Always use the marketplace's final upload preview before release.
"""
