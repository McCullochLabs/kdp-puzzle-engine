"""Build honest Word Search portfolio plans from the approved Master Library.

Every offered production topic is measured against the full planned series:
two 48-puzzle books plus one 100-puzzle Signature Edition.  The companion
plan file contains deterministic, non-overlapping allocations so future book
creation does not consume a sibling edition's words by accident.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from publishing.word_capacity_plan import build_plan, required_words, unique_words


APP_DIR = Path(__file__).resolve().parent
MASTER = APP_DIR / "word_banks" / "Guided_Builder_Master_Word_Bank.json"
OUTPUT = APP_DIR / "word_banks" / "TOPIC_LIBRARY_READINESS.json"
PLANS = APP_DIR / "word_banks" / "TOPIC_PRODUCTION_PLANS.json"
STANDARD_TARGET = 48 * 12
SIGNATURE_TARGET = 100 * 12


def _topic_sets(bank: dict) -> dict[str, list[str]]:
    topics = bank.get("topics", {}) if isinstance(bank.get("topics"), dict) else {}
    packs = bank.get("topic_packs", {}) if isinstance(bank.get("topic_packs"), dict) else {}
    production = bank.get("production_topic_packs", {}) if isinstance(bank.get("production_topic_packs"), dict) else {}
    sets = {str(name): unique_words(words) for name, words in topics.items() if isinstance(words, list)}
    for name, sources in packs.items():
        if isinstance(sources, list):
            sets[str(name)] = unique_words(word for source in sources for word in topics.get(source, []) if isinstance(topics.get(source), list))
    for name, record in production.items():
        sources = record.get("sources", []) if isinstance(record, dict) else []
        if isinstance(sources, list):
            sets[str(name)] = unique_words(word for source in sources for word in topics.get(source, []) if isinstance(topics.get(source), list))
    return sets


def main() -> None:
    bank = json.loads(MASTER.read_text(encoding="utf-8-sig"))
    topic_sets = _topic_sets(bank)
    records = []
    allocations: dict[str, dict] = {}
    for topic, words in sorted(topic_sets.items(), key=lambda item: item[0].casefold()):
        plan = build_plan(topic, words)
        allocations[topic] = plan
        records.append({
            "topic": topic,
            "proven_words": plan["available_words"],
            "standard_48_puzzle_gap": max(0, STANDARD_TARGET - plan["available_words"]),
            "signature_100_puzzle_gap": max(0, SIGNATURE_TARGET - plan["available_words"]),
            "two_standard_plus_signature_gap": plan["gap"],
            "ready_for_standard": plan["standard_book_ready"],
            "ready_for_signature": plan["signature_ready"],
            "ready_for_portfolio": plan["portfolio_ready"],
            "next_action": (
                "Ready for two standard books plus a 100-puzzle Signature Edition" if plan["portfolio_ready"] else
                f"Hold for expansion: {plan['gap']} more reviewed, topic-linked words are needed for the full planned portfolio"
            ),
        })
    records.sort(key=lambda item: (not bool(item["ready_for_portfolio"]), item["proven_words"], item["topic"].casefold()))
    created = datetime.now().isoformat(timespec="seconds")
    payload = {
        "schema_version": 2,
        "created": created,
        "rules": {"standard_book_words": STANDARD_TARGET, "signature_book_words": SIGNATURE_TARGET,
                  "portfolio_words": required_words(), "portfolio": "Two 48-puzzle books plus one 100-puzzle Signature Edition"},
        "summary": {
            "topics": len(records),
            "ready_for_standard": sum(bool(row["ready_for_standard"]) for row in records),
            "ready_for_signature": sum(bool(row["ready_for_signature"]) for row in records),
            "ready_for_portfolio": sum(bool(row["ready_for_portfolio"]) for row in records),
            "needs_expansion": sum(not bool(row["ready_for_portfolio"]) for row in records),
        },
        "topics": records,
    }
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    PLANS.write_text(json.dumps({"schema_version": 1, "created": created, "rules": payload["rules"], "topics": allocations}, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT} and {PLANS}: {payload['summary']}")


if __name__ == "__main__":
    main()
