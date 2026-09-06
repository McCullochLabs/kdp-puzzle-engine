"""Explicitly generate a review-only batch from existing records.

It never changes a source bank or approval state.  A human decision file can
later be supplied to the planner as an in-memory overlay.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from word_intelligence.book_planning import BookPlanner
from word_intelligence.qualification import write_review_batch


def main() -> None:
    parser = argparse.ArgumentParser(description="Write a Phase 3 review batch; no approval is applied.")
    parser.add_argument("--topic", required=True)
    parser.add_argument("--type", required=True, choices=("word_search", "cryptogram", "scramble_trivia"))
    parser.add_argument("--out", required=True)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    planner = BookPlanner.from_project(PROJECT_ROOT)
    topic = planner.engine.taxonomy.resolve(args.topic)
    if not topic:
        raise SystemExit("Topic does not resolve to a canonical Master Library topic.")
    expected = {"word_search": {"word", "phrase"}, "cryptogram": {"cryptogram_prompt"},
                "scramble_trivia": {"trivia"}}[args.type]
    records = [record for record in planner.engine._topic_records(topic, False)
               if record.type in expected][:max(1, args.limit)]
    write_review_batch(args.out, records, topic, args.type)
    print(f"Wrote {len(records)} review-only candidates to {args.out}")


if __name__ == "__main__":
    main()
