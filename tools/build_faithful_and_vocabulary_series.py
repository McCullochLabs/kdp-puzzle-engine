"""Build the Faithful Words Signature Edition and Vocabulary Ladder series."""
from __future__ import annotations

import json
import random
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import word_search_creator as studio
from tools.build_commercial_baseline import build_word_search

MASTER = ROOT / "word_banks" / "Guided_Builder_Master_Word_Bank.json"
THEME_DIR = ROOT / "themes" / "Faithful Words Series"
AUTHOR = "Jordan M. Slade"


def clean(values):
    seen, result = set(), []
    for value in values:
        word = re.sub(r"[^A-Z]", "", str(value).upper())
        if 3 <= len(word) <= 21 and word not in seen:
            seen.add(word)
            result.append(word)
    return result


def faithful_theme() -> Path:
    master = json.loads(MASTER.read_text(encoding="utf-8-sig"))
    pool = clean(master["topics"]["Bible and Faith"])
    # Deterministic mixing prevents alphabetic-looking puzzle lists while
    # preserving the reviewed, explicitly Bible-linked source pool.
    random.Random("faithful-words-signature-2026").shuffle(pool)
    chosen = pool[:1200]
    if len(chosen) != 1200:
        raise RuntimeError(f"Bible and Faith has only {len(pool)} usable reviewed words; 1200 required.")
    sections = (
        "Faith and Encouragement", "People and Places", "Prayer and Worship",
        "Wisdom and Virtues", "Stories and Journeys", "Hope and Gratitude",
        "Fellowship and Service", "Promises and Purpose", "Peace and Reflection",
        "Spiritual Growth",
    )
    data = {
        "title": "Faithful Words: Large-Print Bible Word Search for Adults",
        "subtitle": "100 Faith-Inspired Puzzles for Women, Seniors, and Peaceful Quiet-Time Solving",
        "author": AUTHOR,
        "audience": "Adults and Seniors",
        "series": "Faithful Words Signature Editions",
        "palette": "bible", "recommended_palette": "bible",
        "cover_style": "photo", "recommended_cover_style": "photo",
        "cover_badge": "100 LARGE-PRINT PUZZLES • NO REPEATED WORDS",
        "cover_imprint": "Slade Puzzle Co.",
        "no_repeat_words": True, "difficulty_label": "Easy to Medium",
        "detected_topic": "Bible and Faith",
        "signature_edition": {
            "enabled": True, "puzzle_target": 100,
            "passport_title": "Faithful Words Journey",
            "achievement_title": "Signature Edition",
            "achievement_message": "A peaceful journey through faith-inspired words.",
            "facts_title": "PAUSE AND REFLECT",
            "fact_cards": [
                "Quiet word puzzles can offer a gentle pause for reflection and focus.",
                "Biblical books include poetry, history, wisdom, letters, and accounts of faith.",
                "Words of hope, gratitude, service, and fellowship connect many biblical themes.",
            ],
        },
        "source_word_bank": {"name": "Guided Builder Master Word Bank", "topics": ["Bible and Faith"], "selection_policy": "Reviewed topic links only; unique; 3–21 normalized letters"},
        "puzzles": [],
    }
    for index in range(100):
        section = sections[index // 10]
        data["puzzles"].append({"name": f"{section} {index % 10 + 1}", "section": section, "words": chosen[index*12:(index+1)*12]})
    THEME_DIR.mkdir(parents=True, exist_ok=True)
    path = THEME_DIR / "faithful_words_large_print_signature_100.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    errors, _, _ = studio.quality_gate(path, 731001)
    if errors:
        raise RuntimeError("Faithful Words source failed: " + " | ".join(errors))
    return path


def main() -> int:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    plans = [{
        "theme": faithful_theme(),
        "title": "Faithful Words: Large-Print Bible Word Search for Adults",
        "subtitle": "100 Faith-Inspired Puzzles for Women, Seniors, and Peaceful Quiet-Time Solving",
        "seed": 731001,
    }]
    reserved_path = ROOT / "data" / "word_reservations.json"
    reservation_data = json.loads(reserved_path.read_text(encoding="utf-8-sig")) if reserved_path.is_file() else {"books": []}
    reserved = {word for book in reservation_data.get("books", []) for word in book.get("words", [])}
    master = json.loads(MASTER.read_text(encoding="utf-8-sig"))
    for grade in range(5, 13):
        path = ROOT / "themes" / "Vocabulary Ladder Collection" / "Grades 5 to 12" / f"vocabulary_ladder_grade_{grade}.json"
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if grade > 5:
            canonical_words = {word for puzzle in data.get("puzzles", []) for word in clean(puzzle.get("words", []))}
            pool = [word for word in clean(master["topics"][f"Grade {grade} Vocabulary"])
                    if word not in reserved and word not in canonical_words]
            random.Random(f"vocabulary-ladder-grade-{grade}-2026").shuffle(pool)
            chosen = pool[:576]
            if len(chosen) != 576:
                raise RuntimeError(f"Grade {grade} has only {len(pool)} fresh reviewed words; 576 required.")
            data.update({
                "title": f"Vocabulary Ladder: Grade {grade} Word Quest",
                "subtitle": f"48 themed vocabulary word searches for Grade {grade} reading, spelling, and word confidence",
                "author": AUTHOR, "series": "Vocabulary Ladder: Grade-by-Grade Word Quest",
                "cover_badge": "48 THEMED PUZZLES • NO REPEATED WORDS", "no_repeat_words": True,
                "source_word_bank": {"name": "Guided Builder Master Word Bank", "topics": [f"Grade {grade} Vocabulary"], "selection_policy": "Reviewed grade-linked words, excluding finalized-book reservations"},
            })
            data["puzzles"] = [
                {"name": f"Grade {grade} Word Quest {number:02d}", "words": chosen[(number-1)*12:number*12]}
                for number in range(1, 49)
            ]
            production_dir = ROOT / "themes" / "Vocabulary Ladder Collection" / "Production Series"
            production_dir.mkdir(parents=True, exist_ok=True)
            path = production_dir / f"vocabulary_ladder_grade_{grade}_fresh.json"
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            reserved.update(chosen)
        errors, _, _ = studio.quality_gate(path, 731100 + grade)
        if errors:
            raise RuntimeError(f"Grade {grade} source failed: " + " | ".join(errors))
        plans.append({
            "theme": path,
            "title": f"Vocabulary Ladder: Grade {grade} Word Quest",
            "subtitle": f"48 themed vocabulary word searches for Grade {grade} reading, spelling, and word confidence",
            "seed": 731100 + grade,
        })

    results = []
    for plan in plans:
        expected = ROOT / "out" / f"commercial_baseline_{plan['seed']}_{studio.WordSearchCreator._safe_filename(plan['title']).lower()}"
        if expected.is_dir() and (expected / "01_PRINT_UPLOADS" / "interior.pdf").is_file() and (expected / "01_PRINT_UPLOADS" / "full_wrap.pdf").is_file():
            results.append({"title": plan["title"], "package": str(expected), "theme": str(plan["theme"]), "reused_completed_package": True})
            continue
        folder = build_word_search(plan)
        results.append({"title": plan["title"], "package": str(folder), "theme": str(plan["theme"])})

    from publishing import PublishingService
    service = PublishingService(ROOT)
    service.sync_output_packages()
    for result in results:
        folder = Path(result["package"]).resolve()
        matches = [b for b in service.db.list_books() if Path(str(b.get("package_path") or "")).resolve() == folder]
        if not matches:
            raise RuntimeError(f"Publishing Manager did not register {folder.name}")
        book = matches[0]
        result["book_id"] = book["book_id"]
        result["handoffs"] = service.prepare_many([book["book_id"]], ["amazon", "etsy", "payhip", "barnes_noble"])

    report = ROOT / "reports" / f"FAITHFUL_AND_VOCABULARY_SERIES_{stamp}.json"
    report.write_text(json.dumps({"created_at": stamp, "results": results}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(report), "results": results}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
