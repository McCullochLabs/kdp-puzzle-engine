# Content Intelligence Operator Workflow

This is the simple production path for SladePuzzleCo Puzzle Book Studio. The
technical content library, plan hashes, and proof checks remain behind the
scenes unless you open a detailed report.

## 1. Start with Book Readiness

From the Book Assistant, ask **“What can I make now?”** or choose **Book
readiness** in the production area. The same screen is available from
Publishing Center under **What needs attention?**.

Enter the topic and the exact format you want. **Verified Content** is the
default and recommended option. It means the book will use reviewed,
topic-linked material only. **Legacy-Compatible Content** is an explicit
choice for older material and requires acknowledgement later; the app never
switches to it by itself.

The result tells you whether the exact idea is ready, shows the amount of
reviewed content available, and suggests honest smaller formats when there is
not enough content. It never lowers your requested format without asking.

## 2. Review content when needed

If the exact format is blocked, choose **Create review batch**. This creates a
review-only file in `reports/content_review_batches`. It changes no source
word bank and does not approve anything automatically. Use the existing Word
Review Queue to make individual human approval or rejection decisions.

## 3. Build Safe Plan

When the exact request is ready, choose **Build Safe Plan**. The app checks
current capacity again, selects content deterministically, and saves a plan in
`plans/operator`. A plan records the requested format, seed, selected content,
and source revision. It does not create PDFs or alter an existing package.

If the source library changes later, the plan is shown as **Out of Date**.
Build an updated plan rather than silently replacing the earlier plan.

## 4. Generate and run the Production Check

Use the applicable existing Word Search, Sudoku, Cryptogram, Scramble +
Trivia, or Mixed creator to generate only after reviewing the current plan.
Then run the existing **Production Check / Review & proof** process. It checks
the interior, answers, cover, wrap, package, and factual listing agreement.

Automated production checks do not publish a book and do not replace human
listing edits.

## 5. Final Local Review

After the production check passes, review the interior, answers, front cover,
wrap, listing copy, pricing, and handoff files. Record the review explicitly;
opening a preview alone is not an approval. A compatibility-mode book also
requires an explicit acknowledgement before it can be locally release-ready.

## 6. Ready for Platform Preview

When automated proof, required acknowledgement, and Final Local Review are
complete, the status becomes **Ready for Platform Preview**. This means the
local package is ready for your platform preview and handoff. It does **not**
mean the marketplace has accepted or published the book.

## Existing products

Older packages without a modern Book Plan are shown as **Legacy Package —
Modern Proof Not Available**. They are not silently rebuilt, modified, or
re-labeled. Their marketplace history remains protected.
