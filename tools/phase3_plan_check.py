"""Small developer utility for deterministic, non-generating plan checks.

Usage examples (never creates a PDF or package):
  python tools/phase3_plan_check.py --topic Gardening --type word_search --count 48 --items 12 --seed 7
  python tools/phase3_plan_check.py --topic "Space & Astronomy" --type cryptogram --count 48 --review legacy_compatible
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from word_intelligence.book_planning import BookPlanner, PlanRequest, save_plan


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or inspect a deterministic Phase 3 Book Plan.")
    parser.add_argument("--topic", required=True)
    parser.add_argument("--type", required=True, choices=("word_search", "cryptogram", "scramble_trivia", "sudoku", "mixed"))
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--items", type=int, default=1)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--review", default="strict_verified", choices=("strict_verified", "legacy_compatible"))
    parser.add_argument("--freshness", default="allow_all")
    parser.add_argument("--general", action="store_true", help="Explicitly permit a general pool; never inferred for a themed plan.")
    parser.add_argument("--approval-input", default="")
    parser.add_argument("--save", default="", help="Optional non-production plan JSON path.")
    args = parser.parse_args()
    planner = BookPlanner.from_project(PROJECT_ROOT, args.approval_input or None)
    result = planner.create(PlanRequest(args.topic, args.type, args.count, args.items, args.seed,
                                        review_policy=args.review, freshness_policy=args.freshness,
                                        general_pool=args.general))
    payload = {"status": result.status, "blockers": result.blockers, "warnings": result.warnings,
               "capacity": result.capacity, "plan": result.plan.to_dict() if result.plan else None}
    if result.plan and args.save:
        save_plan(args.save, result.plan)
        payload["saved_to"] = str(Path(args.save))
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
