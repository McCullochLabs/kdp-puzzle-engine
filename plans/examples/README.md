# Phase 3 Book Plan examples

This folder is intentionally separate from `out/` and production packages.
Plans created here are inspection artifacts, not releases or reservations.

Use `tools/phase3_plan_check.py` to create a deterministic local plan from
current content, or `tools/phase3_review_batch.py` to write a human-review
batch. Review batches and approval-input files are explicit: neither tool
rewrites a source bank or marks content as approved.

The stable plan schema is implemented by `word_intelligence.book_planning`.
Each saved plan is validated on load against source revision, capacity proof,
content eligibility, duplicate rules, freshness evidence, and allocation size.
