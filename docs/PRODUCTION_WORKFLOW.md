# Supported Production Workflow

Use Book Assistant or Publishing Center to begin. Word Search, Sudoku, Cryptogram, Scramble + Trivia, Mixed Brain Games, guided, and Publishing Center creation routes connect to the same production truth through their established generators.

`Idea → Feasibility → Approved content plan → Interior → Cover → Product QA → Listing → Package → Final review → Platform preview → Marketplace handoff`

## Operator checkpoints

1. Choose **Continue Production** at the Content Plan gate, review the displayed title, topic, puzzle type, puzzle count, items per puzzle, difficulty, and edition, then approve only if they match your intent.
2. Review every Product QA warning instead of treating it as an automatic failure.
3. At Final Local Review, inspect the locked interior, solutions, front cover, full wrap, listing copy, and warnings.
4. Open the official platform preview and correct any platform-specific issue.
5. Prepare the marketplace handoff, then upload and publish manually on the marketplace.

Opening a review window is not approval. Creating a preview is not approval. A green automated check is not approval.

## What not to use for new books

Root-level historical `build_*.py` and `rebuild_*.py` scripts remain for recovery and audit history. They are not supported new-book entry points and do not supersede the orchestrated UI workflow.

## Safe continuation

Select the tracked book in Publishing Center and choose **Continue Production**. The application resumes the first incomplete, failed, or stale eligible stage, explains blocks in plain English, and stops at every human gate. Use **Stop** to pause safely; use the offered retry only after correcting the reported cause.
