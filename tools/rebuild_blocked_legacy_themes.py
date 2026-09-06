"""Rebuild blocked legacy themes from clean, verified Master Library pools.

The tool never edits a theme unless its rebuilt in-memory version passes the
same Word Intelligence readiness gate used by production.  Every write gets a
dated, full-file backup.  A source that cannot support a genuine 48-puzzle
book remains untouched and is reported plainly.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def topic_plan(path: Path) -> tuple[str, tuple[str, ...]]:
    """Return one honest display topic and its verified source pools."""
    name = path.name.casefold()
    full = str(path).casefold()
    if any(token in name for token in ("1950", "1980", "1990", "2000")):
        return "Nostalgia Through the Decades", ("Nostalgia Through the Decades",)
    if "christmas" in name:
        return "Christmas & Winter", ("Christmas", "Christmas and Winter", "Holiday and Seasonal Life")
    if "halloween" in name:
        return "Halloween & Autumn", ("Halloween", "Halloween Autumn and Harvest")
    if "american_history" in name or "us_history" in name:
        return "American History", ("American History", "American Heritage")
    if "wwii" in name:
        return "World War II & American History", ("World War II History", "American History")
    if "bible" in name:
        return "Bible & Faith", ("Bible and Faith", "Faith Inspiration and Kindness")
    if "parenting" in name:
        return "Positive Parenting & Family Life", ("Positive Parenting", "Home and Household", "Wellness and Self Care", "Mindfulness")
    if "sports" in name or "golf" in name:
        return "Sports, Hobbies & Outdoor Activity", ("Sports and Hobbies", "Hobbies Crafts and Pastimes", "Outdoor Adventure")
    if "seasonal" in name or "cozyautumn" in name:
        return "Seasonal Celebrations", ("Seasonal Celebrations", "Holiday and Seasonal Life", "Halloween Autumn and Harvest")
    if "pets_100" in name:
        return "Pets & Animal Care", ("Pets and Animal Care", "Cats & Pets", "Dogs & Pets")
    if "horselover" in name:
        return "Horses, Farm & Country Life", ("Farm Country and Rural Life", "Outdoor Adventure")
    if "birdwatching" in name:
        return "Birdwatching", ("Birdwatching", "Birdwatching & Wildlife")
    if "farmanimals" in name:
        return "Farm Animals & Country Life", ("Farm Country and Rural Life",)
    if "worldcountries" in name:
        return "Travel & Geography", ("Travel and Geography", "Travel Road Trips and Getaways", "US Geography and Landmarks")
    if "coffeeandtea" in name or "wineandcheese" in name:
        return "Food, Drinks & Kitchen Life", ("Baking and Food", "Garden to Table")
    if "fishing" in name:
        return "Fishing, Lakes & Outdoor Adventure", ("Outdoor Adventure", "Coastal Lake and River Life", "Nature")
    if "quilting" in name or "sewing" in name:
        return "Quilting, Sewing & Crafts", ("Hobbies Crafts and Pastimes", "Arts Creativity and Making", "Home and Household")
    if "classicliterature" in name:
        return "Classic Literature & Reading", ("Books Reading and Libraries",)
    if "reptiles" in name:
        # The old source was a mixed general-interest file.  The clean
        # replacement is deliberately broadened to the verified wildlife
        # family rather than pretending a 576-word reptiles-only pool exists.
        return "Reptiles, Amphibians & Wild Habitats", ("Nature", "Forest Wildlife and Outdoors")
    if "weather" in name:
        return "Weather & Climate", ("Weather and Climate", "Weather & Climate")
    if "grade_" in name or "grade_school" in name or "middle_school" in name:
        grade = next((f"Grade {number} Vocabulary" for number in range(5, 13) if f"grade_{number}_" in name), "")
        if grade:
            return grade, (grade,)
        if "middle_school" in name:
            return "Middle School Vocabulary", ("Middle School Vocabulary",)
        return "Grade School Vocabulary", ("Grade School Vocabulary",)
    return "General Interest", ("General Interest",)


def clean(word: object) -> str:
    return "".join(char for char in str(word).upper() if char.isalpha())


def write_atomic(path: Path, data: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".rebuild.tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def build_pool(bank: dict, pools: tuple[str, ...], store) -> list[str]:
    """Use only clean, safe terms that the intelligence store recognizes."""
    from word_intelligence.analysis import PuzzleWorthiness, assess_quality
    result: list[str] = []
    seen: set[str] = set()
    for name in pools:
        for item in bank.get("topics", {}).get(name, []):
            value = clean(item)
            record = store.get(value)
            if not value or value in seen or record is None or record.safety_review or record.trademark_review:
                continue
            if assess_quality(record).worthiness not in {
                PuzzleWorthiness.PREFERRED, PuzzleWorthiness.ACCEPTABLE,
                PuzzleWorthiness.SPECIALIZED,
            }:
                continue
            if not (3 <= len(value) <= 21):
                continue
            seen.add(value); result.append(value)
    return result


def rebuild(source: dict, pool: list[str], display_topic: str, pool_names: tuple[str, ...]) -> tuple[dict | None, str]:
    puzzles = source.get("puzzles") if isinstance(source.get("puzzles"), list) else []
    if not puzzles:
        return None, "No puzzles in source"
    counts = [len(item.get("words") or []) for item in puzzles if isinstance(item, dict)]
    original_words = Counter(counts).most_common(1)[0][0] if counts else 12
    target_puzzles = max(48, len(puzzles))
    # A complete standard book is more useful than a fake 100-puzzle
    # Signature edition.  Keep 20-word lists only where the verified pool can
    # truly supply every entry with no repeats.
    words_per = 20 if original_words >= 20 and len(pool) >= target_puzzles * 20 else 12
    if len(pool) < target_puzzles * words_per:
        target_puzzles = 48
        words_per = 12
    if len(pool) < target_puzzles * words_per or target_puzzles < 48:
        return None, f"Only {len(pool)} verified terms; needs at least 576 for a full book"
    data = json.loads(json.dumps(source))
    old_names = [str(item.get("name") or "").strip() for item in puzzles if isinstance(item, dict)]
    rebuilt = []
    for index in range(target_puzzles):
        start = index * words_per
        label = old_names[index] if index < len(old_names) and old_names[index] else f"{display_topic} Puzzle {index + 1}"
        rebuilt.append({"name": label, "words": pool[start:start + words_per]})
    data["puzzles"] = rebuilt
    data["detected_topic"] = display_topic
    data["source_word_bank"] = {"topics": list(pool_names), "rebuilt_from_verified_pool": True}
    data["no_repeat_words"] = True
    signature = data.get("signature_edition") if isinstance(data.get("signature_edition"), dict) else {}
    if target_puzzles < 100:
        signature["enabled"] = False
        signature["candidate"] = False
    data["signature_edition"] = signature
    data["quality_review"] = {"production_ready": False, "verdict": "PENDING_REBUILD_VALIDATION"}
    return data, ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    from word_intelligence.pipeline import load_or_build_store, load_taxonomy
    from word_intelligence.repair import production_readiness
    from word_intelligence.theme_audit import VERDICT_FAIL, audit_theme

    report = json.loads(sorted((ROOT / "out" / "word_intelligence_reports").glob("wi2_validation-*.json"))[-1].read_text(encoding="utf-8"))
    bank = json.loads((ROOT / "word_banks" / "Guided_Builder_Master_Word_Bank.json").read_text(encoding="utf-8-sig"))
    taxonomy = load_taxonomy(ROOT)
    loaded = load_or_build_store(taxonomy, ROOT)
    store = loaded[0] if isinstance(loaded, tuple) else loaded
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_root = ROOT / "backups" / "blocked_theme_rebuild" / stamp
    rows: list[dict] = []
    for item in report.get("themes", []):
        if item.get("verdict") != VERDICT_FAIL:
            continue
        path = Path(str(item.get("file") or ""))
        if not path.exists():
            continue
        source = json.loads(path.read_text(encoding="utf-8-sig"))
        display, pools = topic_plan(path)
        pool = build_pool(bank, pools, store)
        rebuilt, detail = rebuild(source, pool, display, pools)
        row = {"file": str(path.relative_to(ROOT)), "title": source.get("title", path.stem), "topic": display, "pool_terms": len(pool)}
        if rebuilt is None:
            row.update({"outcome": "insufficient_verified_pool", "detail": detail}); rows.append(row); continue
        audit = audit_theme(rebuilt, str(path), store, taxonomy)
        readiness = production_readiness(rebuilt, str(path), store, taxonomy)
        row.update({"verdict": audit.verdict, "ready": readiness["ready"], "puzzles": len(rebuilt["puzzles"]), "words_per_puzzle": len(rebuilt["puzzles"][0]["words"])})
        if audit.verdict == VERDICT_FAIL or not readiness["ready"]:
            row.update({"outcome": "validation_blocked", "detail": str(readiness.get("checks") or {})}); rows.append(row); continue
        row["outcome"] = "rebuilt"
        if args.apply:
            backup = backup_root / path.relative_to(ROOT)
            backup.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(path, backup)
            rebuilt["quality_review"] = {"production_ready": True, "verdict": audit.verdict, "checked_at": stamp, "source": "verified_legacy_rebuild", "topic": display}
            write_atomic(path, rebuilt)
        rows.append(row)
    summary = {"generated_at": stamp, "mode": "apply" if args.apply else "dry_run", "rebuilt": sum(row.get("outcome") == "rebuilt" for row in rows), "blocked": sum(row.get("outcome") != "rebuilt" for row in rows), "rows": rows, "backup_folder": str(backup_root) if args.apply else ""}
    report_path = ROOT / "out" / "word_intelligence_reports" / f"blocked_theme_rebuild-{stamp}.json"
    report_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items() if key != "rows"}, indent=2))
    print(f"REPORT {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
