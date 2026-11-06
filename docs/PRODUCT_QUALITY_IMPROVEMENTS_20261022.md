# Product quality improvements — October 22, 2026

This work implements the six requested improvements while preserving the existing Tk desktop, production approvals, and print geometry. Existing workspace changes were retained. Nothing was uploaded or published, and no new human approvals were granted.

## Implemented behavior

1. **Complete target placement.** `wordsearch.generate_puzzle` now returns a complete independently checked grid or raises a useful error. Cleaning rejects empty, unsupported, overlong, and normalized duplicate targets. Embedded targets are reused on their physical paths when possible; impossible competing embeddings are rejected. The standard PDF path no longer proceeds after losing targets. Word-list rendering refuses clipping instead of silently overflowing.
2. **Unambiguous grids and filler screening.** Every generated grid is scanned in all eight directions. Target occurrences are deduplicated by physical cells, including palindromes. Each target must occur exactly once. A bounded offensive-string screen is applied before accepting the grid. Retries use the supplied random generator and remain deterministic.
3. **Measured difficulty.** Word-search reports record direction mix, mean word length, grid size, occupied density, overlap, score, and mechanics band. Sudoku is rated by an independent deterministic solver using naked singles, hidden singles, locked candidates, and naked pairs. A rated-generation wrapper retries until the requested band is met or fails clearly; CLI, Studio, holiday, and activity-pack routes use it. Unresolved puzzles are labelled Hard with an explicit statement that they require techniques beyond the supported set. This is not a claim that guessing is necessary. The seventh-grade book uses only fully solved Easy/Medium puzzles.
4. **Honest vocabulary coverage.** Book scoring normalizes repetition, records unknown and unreviewed words, counts only trusted/approved topic links as reviewed evidence, reports coverage, and returns `Unverified` below 95% coverage instead of an apparently certified letter grade. Actual topic/safety failures still produce F. Product QA can surface the same coverage evidence.
5. **Printed-page and reader checks.** pypdf coordinate screens compose text and user transformation matrices and account for effective font scaling. PDFium independently measures glyph extents on all pages. Content-margin screens use the project's established 54-point margin. Reader profiles set grid/word-list minimums; layout-region checks measure glyph heights alongside declared point sizes. Standard solutions have at least 9-point letters. Existing print geometry and printer formulas are unchanged. Unmeasurable vector-only symbols remain a visual-review warning.
6. **Puzzle-to-answer proof.** PDF-bound manifests store intended targets, actual grids/placements, Sudoku givens/solutions, page correspondence, and difficulty evidence. Standard word search, accessible collections, Sudoku CLI, Studio, and holiday interiors write manifests. Studio also records cryptogram substitutions, scramble letters/answers, and mixed-book numbering. Product QA checks manifest math, numbered pages, the exact PDF hash, and actual grid glyph readback. Fresh Studio/word-search builds require the record; legacy packages without one remain visible with a warning. Activity packs retain their existing separate activity/answer PDF hash manifest and now use validated grids and measured Sudoku bands.

Quality-policy revisions are included in production/autopilot fingerprints so saved checkpoints cannot silently reuse older generation or cover-preview behavior. Reader profile changes also invalidate the generation fingerprint.

## Production exercise

Run `build_grade7_combo.py --out <new-directory>` for the reproducible 50-puzzle seventh-grade book. It validates its original source, creates 25 searches and 25 Sudoku puzzles, uses an existing approved middle-school cover asset, generates the actual-page-count wrap, and saves local preflight/QA/audit evidence. It never overwrites an existing output directory.

Run `tools/audit_grade7_production.py <package-directory>` to independently read back grids, inspect embedded text fonts, render every page with Poppler, and write contact sheets and a readable production audit.

The delivered package is `out/Think Search Solve Grade 7 - Audited`. The production audit explicitly explains that Context7 supplies library documentation, while Codex performed the build and artifact inspection. Its substantive open finding is incomplete existing-library vocabulary coverage: 203/300 targets have trusted/approved links, 17 are absent, and 80 are unreviewed. Legitimate subject terms were preserved for teacher review instead of replaced to force a passing score.

## Files changed for this request

- New shared modules: `publishing/puzzle_integrity.py`, `publishing/sudoku_difficulty.py`.
- Engines and checks: `wordsearch.py`, `sudoku.py`, `publishing/product_qa.py`, `word_intelligence/book_quality.py`, `word_intelligence/production_gate.py`.
- Production callers and profiles: `puzzle_book_studio.py`, `word_search_creator.py`, `holiday_combo.py`, `publishing/activity_packs.py`, `publishing/accessible_wordsearch.py`, `publishing/studio_reader_profiles.py`, `publishing/production_orchestrator.py`, `publishing/production_autopilot.py`.
- Cover correction: `cover.py` now shows all nine Sudoku rows on combined covers and labels the word-search crop as an excerpt.
- Book source and builder: `word_banks/grade7_wordsearch_sudoku_50.json`, `build_grade7_combo.py`.
- Tests: new `tests/test_puzzle_integrity.py`; updated `tests/test_wordsearch.py`, `tests/test_word_intelligence_wi2.py`, `tests/test_sudoku_cover_sample.py`.
- Review tools/documentation: `tools/run_quality_review.py`, `tools/audit_grade7_production.py`, this document, and `.gitignore` patterns for local test scratch files.
- Generated: the new book/review directories under `out/`, including the final audited package. Earlier build attempts were retained as evidence; no existing books were overwritten.

Several of these files already had unrelated local edits. This list identifies touched files, not ownership of every difference shown by Git. No existing source files were deleted or moved.

## Validation and limits

New tests cover 100 short-word generation seeds, impossible/duplicate/embedded targets, corruption and filler screening, JSON round-trip directions, stale PDF hashes, solution-page bounds, actual PDF glyph readback, Sudoku technique bands and uniqueness, affine PDF coordinates, combined-cover preview completeness, Studio manifests across four puzzle types, cache-policy invalidation, seventh-grade counts/progression, and vocabulary coverage/repetition normalization.

See the accompanying verification report for final test results. The suite must run through `.venv/Scripts/python.exe`. On this Windows environment, large combined GUI runs can encounter native Tk handle failures; `tools/run_quality_review.py` runs modules separately and keeps all temporary files inside the project. Windows Credential Manager and local socket access may be denied by the execution sandbox; those failures must not be misreported as passing checks or silently fixed by weakening application safeguards.

The offensive-term list is intentionally bounded. Mechanics bands are local measures. Automated text bounds do not replace visual review, teacher review, a physical printed proof, or marketplace preview.
