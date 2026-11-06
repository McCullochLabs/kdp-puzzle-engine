# Printable Activity Pack verification

Baseline: `2c48b7134745044781a9d1cdf4f60ea893f6e0aa`.

Runtime: CPython 3.13.11, 64-bit Linux, with the exact requirements-dev.txt pins.
`python tools/check_runtime.py` passed.

- Targeted engine and activity-pack tests: 43 passed; 2 dialog tests skipped because a desktop display was not available for that run.
- Full tests/: 760 passed, 6 failed, 3 skipped (26.21 seconds).
- All six failing tests were also run against a pristine worktree of the baseline; the same six failed there. They concern missing cover artwork/registry approvals, Gemini credential availability expectations, a Windows-specific font-path assertion, and full-theme validation blocked by missing artwork.
- Generated a personalized six-activity Road Trip pack. Inspected rendered introduction, word-search, scramble, and Sudoku-answer pages; corrected introduction wrapping after inspection. Local pack checks verify PDF page counts/sizes and puzzle/answer correspondence.
- `git diff --check` passed.

This does not constitute Windows GUI testing or a physical print proof. Before merging, run the documented Windows checks in PRINTABLE_ACTIVITY_PACKS.md. No application was installed on the HP and no publishing action occurred.
