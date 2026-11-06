# Studio tool audit and simplification

Scope: GitHub baseline `2c48b7134745044781a9d1cdf4f60ea893f6e0aa`, plus the printable-pack addition. This is a source/dependency audit, not verification of the HP's unpushed files or a family usability study.

## Decisions

| Area | Decision | Reason / implementation |
|---|---|---|
| Everyday navigation | Consolidate | Home, Create, My books, Covers, Settings replace the default tool-heavy assistant dashboard. |
| Assistant, Smart Book Setup, Create New Book | Consolidate their entry points | One family request/proposal surface and a card/radio-button book planner. Existing detailed creators remain available in the advanced workspace. |
| Printable packs | Keep | Three-step workflow for idea, activities/vocabulary, then review. Separate activity/answer PDFs and customer ZIP. |
| Word Search / Sudoku / cryptogram / scramble / mixed engines | Keep | A model cannot replace reproducible generation, complete word placement, matching answers, or unique Sudoku solutions. |
| Word intelligence, topic libraries, capacity, source/content checks | Keep; move maintenance behind Advanced | These supply reviewed vocabulary and prevent unsupported claims or repeated content. |
| Cover generation | Keep as the one established pipeline | `background_generation/service.py` and `index.py` manage generated art and approval; `routing.py` selects approved assets; `cover.py` renders covers; `wrap_cover.py` makes wraps. No second artwork generator was added. |
| Cover galleries, layout editor, free-art tools, niche preferences | Keep; consolidate discovery under Covers / Advanced | They have different jobs. Approved artwork, layout, print geometry, and provenance remain separate concerns within one pipeline. |
| Cover approvals and proof records | Keep | AI cannot self-approve generated artwork or replace final human inspection. |
| Publisher catalog / book control center | Keep | `data/books.db` remains authoritative. New library navigation reads existing records rather than creating a second catalog. |
| Preflight, release contract, proof locks and final review | Keep | Their guarantees remain necessary behind a conversational interface. |
| Multi-marketplace exports / Etsy draft-only adapter | Keep; Advanced/book review | Platform-specific requirements and guarded Uploaded/Published statuses must survive simplification. |
| Batch, series, production queues, recovery, snapshots | Keep; Advanced | Important for the owner, unnecessary on the family's starting screen. |
| Repeated dashboard/menu shortcuts | Remove from the default experience | No parallel lists of tools on Home. Legacy shortcuts survive only in the on-demand advanced workspace. |
| Historical root build/rebuild/refresh scripts | Retain as historical tools | Existing PRODUCTION_PATHS.md marks them unsupported for daily production. They are not exposed as new workflows. No deletion is justified by duplicate names alone. |
| Placeholder integrations / planned channels | Keep out of family navigation | Their existence does not establish usable automation. |
| Optional local AI interpreter | Add narrowly | It proposes one supported workflow. No arbitrary tools, filesystem access, shell, installs, uploads, or autonomous publishing. |

## Cover authority

The Covers page opens the existing artwork generator directly for an explicit topic. Book-specific layout work begins by selecting a saved book, keeping its metadata and production route together. Both word-search and non-word book creation still delegate to the established cover-selection, rendering, wrap, and proof boundaries.

A printable pack's plain title/introduction page is not a new artwork pipeline or a KDP cover. It does not bypass cover approval for books.

## What the model replaces

The model can replace the user's need to know which dialog or menu to open, translate everyday language into a proposed workflow, and carry a topic/personalization into its review form. It does not replace engines, libraries, QA, state storage, recovery, or publishing adapters. Removing those because an AI interface exists would remove product functionality and protections.

## Startup and layout repairs

The family interface does not construct the full legacy workspace or scan all themes during startup. Detailed production controls are initialized only when needed. The new pack wizard has fixed navigation below a scrollable page. Cover-generation actions are arranged in two rows rather than one over-wide toolbar; the cover-layout editor uses the existing scrollable form helper.

No engines, source data, approved artwork, historical packages, integrations, or recovery tools were deleted. A future deletion pass should be based on measured reachability and migration coverage, not the number of visible buttons.

## Known limitations

GitHub lacks artwork referenced by existing cover tests and full-theme validation. These were baseline failures, not reasons to weaken approval checks or synthesize replacements. The HP may have those assets locally. Actual Windows startup, saved-project compatibility, printing, and live local-model behavior must be checked on that computer.
