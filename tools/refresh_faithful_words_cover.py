"""Replace the mismatched Faithful Words cover through the shared cover pipeline."""
from __future__ import annotations
import hashlib, json, subprocess, sys
from pathlib import Path
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from publishing import PublishingService
from publishing.package_layout import package_file
from publishing.production_intelligence import finalize_package

FOLDER = ROOT / "out" / "commercial_baseline_731001_faithful_words_large-print_bible_word_search_for_adults"
ART = ROOT / "cover_assets" / "background_photos" / "bible_chapel_v3.png"

def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main() -> None:
    record_path = package_file(FOLDER, "PACKAGE_SOURCE_RECORD.json")
    record = json.loads(record_path.read_text(encoding="utf-8"))
    interior, front = package_file(FOLDER, "interior.pdf"), package_file(FOLDER, "front_cover.png")
    wrap, preview = package_file(FOLDER, "kdp_full_wrap.pdf"), package_file(FOLDER, "kdp_full_wrap_preview.png")
    before = digest(interior); pages = len(PdfReader(str(interior)).pages)
    subprocess.run([sys.executable, str(ROOT/"cover.py"), "--title", record["title"], "--subtitle", record["subtitle"],
        "--author", record.get("author", "Jordan M. Slade"), "--badge", "100 LARGE-PRINT PUZZLES • NO REPEATED WORDS",
        "--puzzle-count", "100", "--difficulty", "Easy to Medium", "--format-label", "LARGE PRINT WORD SEARCH",
        "--puzzle-type", "Word Search", "--palette", "bible", "--style", "photo", "--art", str(ART),
        "--art-focus", "center", "--puzzle-preview-position", "right", "--theme-file", str(ROOT/"themes/Faithful Words Series/faithful_words_large_print_signature_100.json"), "--out", str(front)], check=True, cwd=ROOT)
    back = "Settle into 100 large-print Bible word searches created for peaceful quiet time. Explore faith-inspired vocabulary with clear grids, a gentle easy-to-medium progression, no repeated words, and complete solutions."
    subprocess.run([sys.executable, str(ROOT/"wrap_cover.py"), "--front", str(front), "--pages", str(pages), "--palette", "bible",
        "--title", record["title"], "--author", record.get("author", "Jordan M. Slade"), "--back", back,
        "--back-heading", "A PEACEFUL FAITH-FILLED PUZZLE JOURNEY", "--out", str(wrap), "--preview-out", str(preview)], check=True, cwd=ROOT)
    record.update({"cover_art": str(ART.relative_to(ROOT)), "cover_art_name": ART.name, "palette": "bible", "cover_style": "photo", "cover_visual_revision": "faithful-chapel-v1"})
    record_path.write_text(json.dumps(record, indent=2)+"\n", encoding="utf-8")
    source = json.loads((ROOT/"themes/Faithful Words Series/faithful_words_large_print_signature_100.json").read_text(encoding="utf-8"))
    final = finalize_package(ROOT, FOLDER, source, record["title"], record["subtitle"], pages)
    service = PublishingService(ROOT); service.sync_output_packages()
    matches=[b for b in service.db.list_books() if Path(str(b.get("package_path") or "")).resolve()==FOLDER.resolve()]
    if matches: service.prepare_many([matches[0]["book_id"]], ["amazon","etsy","payhip","barnes_noble"])
    if digest(interior) != before: raise RuntimeError("Interior changed during cover-only refresh.")
    print(json.dumps({"ready": final["ready"], "blockers": final["blockers"], "interior_unchanged": True, "cover": str(front), "wrap": str(wrap)}, indent=2))

if __name__ == "__main__": main()
