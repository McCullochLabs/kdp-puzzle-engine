# Printable Activity Packs

Open **Start Word Search Creator → Create → Printable activity pack**. The guided flow has three steps: your idea, activities, and final review.

1. Choose Road Trip, Birthday, Garden, Space, Winter Holidays, or Custom.
2. Set the title and optional recipient or occasion. Edit the vocabulary, using one entry per line or comma-separated entries. Spaces and hyphens are removed inside puzzle words; other invalid entries are reported rather than dropped.
3. Select Word Search, Word Scramble, Sudoku, or a combination. Choose 1–24 activity pages, with at least one page per selected type. Types alternate in the order shown.
4. Supply eight unique words for each page of the most frequent word-activity type. For example, six pages across all three formats need 16 words. Vocabulary does not repeat within one type, but may recur between Word Search and Word Scramble. A Sudoku-only pack needs no vocabulary.
For another library theme, use **Browse all topics**; the Studio automatically selects checked words. Combined themes retain their selected groups in draft recovery. Reviewing words is optional.

5. Set Sudoku difficulty. This setting does not change word-activity difficulty: word searches use all eight directions. Themes and personalization do not alter Sudoku rules or symbols.
6. Optionally review the plan, choose an output folder, and click **Create printable pack**. The generated seed stays visible; reuse the same inputs and seed to reproduce the puzzles.
7. Open the result, inspect both PDFs, and print a sample at Actual Size / 100% on US Letter paper before distribution.

## Output

- `ACTIVITIES.pdf`: introduction and one page per activity.
- `ANSWERS.pdf`: separate introduction and matching numbered answer pages.
- `READ_ME.txt`: printing and review guidance.
- `PRINTABLE_PACK.zip`: the two customer PDFs and printing instructions.
- `PACK_MANIFEST.json`: local plan, seed, puzzle/answer data, PDF hashes, and local proof status. This production record is deliberately excluded from the customer ZIP.

Every creation uses a new folder. Existing packs, source themes, catalog records, and saved books are not overwritten. Pack generation uses local random generators and preserves the established engines' default random behavior.

## Review boundaries

The route checks all intended word-search placements, matching solutions, Sudoku uniqueness, PDF page counts, nonempty pages, and US Letter dimensions. It preserves the application's protected-term filter for automatic vocabulary. These checks do not establish editorial suitability, ownership rights, accessibility, or marketplace approval. Word scrambles can have other valid anagrams; the answer sheets identify the intended answers.

This is a digital-printable workflow. It creates no KDP wrap, commercial book record, approved listing, or publishing submission. Existing book production and proof gates remain the required route for commercial book packages. Trivia, cryptograms, social graphics, marketplace integration, and automated educational claims are outside this first version.

## Development verification

Run under the project's CPython 3.13.15 environment:

```
.venv\Scripts\python.exe -m pytest tests/test_activity_packs.py tests/test_activity_pack_ui.py tests/test_wordsearch.py tests/test_sudoku.py
```

The UI tests require a working desktop display; they skip when one is unavailable. Before merging on Windows, open the dialog from the main application, create a mixed preset pack and a custom personalized pack, verify error messages and responsiveness, open the generated folder, and sample-print. Also verify that ordinary book creation remains available.
