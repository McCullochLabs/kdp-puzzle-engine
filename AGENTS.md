# AGENTS.md — AI Operating Instructions

This document provides permanent operating instructions and guidelines for AI coding agents working on the **KDP Puzzle Engine / Word Search Creator** codebase.

---

## 1. PROJECT MISSION

This is a production application for creating commercial puzzle books and publishing packages for Amazon KDP, Etsy, IngramSpark, and direct sales channels. 

Existing working functionality must be protected at all times. The primary objective is to maintain a dependable, high-quality, print-ready publishing pipeline.

---

## 2. SAFETY FIRST

- **Never delete working features** merely to simplify implementation or reduce code length.
- **Never rewrite large working sections** unless absolutely necessary and explicitly approved.
- **Prefer small, targeted changes** over sweeping architectural refactors.
- **Preserve backwards compatibility** with existing theme JSON files, saved packages, and catalog databases wherever practical.
- **Do not rename or move major files** without a strong technical reason.
- **Never modify generated output files** (e.g., in `out/`) as a substitute for fixing root bugs in source code.
- **Never modify the `.venv` directory manually** or commit virtual environment files.
- **Never expose or commit credentials**, API keys, passwords, cookies, session tokens, or private account information.

---

## 3. BEFORE MAKING CHANGES

Before implementing a requested feature or bug fix:
1. **Locate and understand the relevant code:** Read the full context of affected modules.
2. **Identify dependencies and related functionality:** Determine if changes affect CLI engines, GUI dialogs, PDF generation, or database models.
3. **Check for existing implementations:** Search the codebase before creating new utilities to avoid logic duplication.
4. **Explain briefly what you intend to change:** Provide a clear, concise plan before executing code modifications.
5. **Run relevant existing tests where practical:** Establish a known baseline before modifying code.

---

## 4. AFTER MAKING CHANGES

After every meaningful code change:
1. **Run relevant tests:** Execute `pytest` via `.venv\Scripts\python.exe -m pytest` on relevant test modules.
2. **Run broader tests:** Run the full test suite (`tests/`) when modifying shared engines, cover tools, or database utilities.
3. **Check for syntax and import errors:** Verify clean execution across modified files.
4. **Confirm feature preservation:** Ensure existing buttons, dialogs, formatting, or command-line arguments were not inadvertently removed.
5. **Report changes transparently:**
   - List exactly which files were modified, created, or removed.
   - Report test commands executed and their pass/fail results.
   - Note any residual risks, technical caveats, or follow-up items.

---

## 5. GUI RULES

- **Preserve Tkinter/ttk:** The desktop GUI is built on standard `tkinter` and `ttk`. Do not replace or introduce alternative GUI frameworks (e.g., PyQt, Electron, web views) unless explicitly instructed.
- **Maintain Workspace Themes:** Preserve all built-in UI themes (`Studio Dark`, `Paper Light`, `Neon Code Rain`, `Midnight Indigo`).
- **User-Centric Design:** Maintain clear, plain-English UI labels, informative tooltips (`HoverHelp`), and guided workflows suited for non-technical publishers.
- **Responsive Execution:** Long-running operations (PDF rendering, package compilation, CC0 downloads) and large JSON parses must run in background threads without freezing the Tkinter event loop.
- **Preserve Existing Dialogs & Tools:** Never remove existing dialogs, builders, previewers, or publishing management tools unless explicitly requested.

---

## 6. PUZZLE ENGINE RULES

- **Deterministic Generation:** Maintain reproducible puzzle generation whenever a random seed is provided.
- **100% Word Placement:** Word search puzzles must place all intended valid words; never silently drop words to make placement succeed.
- **Unique Sudoku Solutions:** Any modification to Sudoku generation must preserve the MRV uniqueness solver guarantee (every puzzle must have exactly one unique valid solution).
- **Accurate Solution Correspondence:** Solution sections and overlay highlighters must match the generated puzzles exactly.
- **Readability & Large-Print Standards:** Preserve grid cell spacing, minimum font sizes, and layout readability across all puzzle formats.

---

## 7. PRINT AND KDP RULES

- **Standard Trim Size:** Preserve $8.5" \times 11"$ interior page sizing as the dependable default.
- **Print Geometry & Margins:** Maintain accurate bleeds ($0.125"$), margins ($0.75"$), spine calculation formulas ($pages \times 0.002252"$), and barcode safe clearance zones on full-wrap covers.
- **No Unverified Dimension Changes:** Never alter print dimensions, resolution ($300\text{ DPI}$), or spine formulas without verifying physical KDP specifications.
- **Page-Count Synchronization:** Ensure cover spine calculations use the exact completed physical interior page count (including even-page balancing).
- **Preflight Compliance:** All generated packages must pass preflight checks (`preflight.py`) before publication handoff.

---

## 8. CONTENT QUALITY

- **Trademark & Brand Protection:** Maintain the `REVIEW_REQUIRED_TERMS` filter and never allow protected franchise, character, or celebrity names into automatic pipelines.
- **Vocabulary & Topic Auditing:** Maintain duplicate-word filters, intra-book repetition checks, and topic-fit verification.
- **Integrity Over Convenience:** Never relax or bypass safety checks simply to force a failing word bank or build script to pass.
- **Author & Imprint Separation:** Preserve contributor safety rules (e.g., prevent publishing brand names like "Slade Puzzles" in the author field while keeping them in cover imprint fields).

---

## 9. MARKETPLACE AND PUBLISHING RULES

- **Platform Separation:** Treat Amazon KDP, Etsy, IngramSpark, Lulu, BookVault, Barnes & Noble, and direct stores as distinct distribution channels with distinct metadata and file requirements.
- **No Cross-Platform Assumptions:** Do not assume KDP interior or cover specifications apply directly to IngramSpark, Etsy digital downloads, or other printers.
- **Browser Automation Caution:** Maintain scripts in `publish_tools/` with defensive checks; browser DOMs can change without notice.
- **Non-Destructive Actions:** Never perform live publishing submissions, automated purchases, or destructive account operations without explicit user confirmation.

---

## 10. ARCHITECTURE

The primary components of the codebase include:

- **[`word_search_creator.py`](file:///C:/Users/jorda/Desktop/Word%20Search%20Creator/kdp-puzzle-engine/word_search_creator.py):** Primary desktop GUI application, dialogs, assistant home, and orchestrator.
- **[`puzzle_book_studio.py`](file:///C:/Users/jorda/Desktop/Word%20Search%20Creator/kdp-puzzle-engine/puzzle_book_studio.py):** Standalone studio for Sudoku, Cryptograms, Word Scramble + Trivia, and Mixed Brain Games.
- **[`wordsearch.py`](file:///C:/Users/jorda/Desktop/Word%20Search%20Creator/kdp-puzzle-engine/wordsearch.py):** Core CLI ReportLab PDF generator for word search interiors.
- **[`sudoku.py`](file:///C:/Users/jorda/Desktop/Word%20Search%20Creator/kdp-puzzle-engine/sudoku.py):** Sudoku generator with MRV uniqueness solver and PDF layout.
- **[`cover.py`](file:///C:/Users/jorda/Desktop/Word%20Search%20Creator/kdp-puzzle-engine/cover.py):** 300 DPI front cover generator with dynamic palettes, layout styles, and real puzzle hero overlays.
- **[`wrap_cover.py`](file:///C:/Users/jorda/Desktop/Word%20Search%20Creator/kdp-puzzle-engine/wrap_cover.py):** Full-wrap cover PDF generator with spine math and barcode clearance.
- **[`preflight.py`](file:///C:/Users/jorda/Desktop/Word%20Search%20Creator/kdp-puzzle-engine/preflight.py):** KDP print compliance validator.
- **[`project_checks.py`](file:///C:/Users/jorda/Desktop/Word%20Search%20Creator/kdp-puzzle-engine/project_checks.py):** Whole-project catalog and theme JSON validator.
- **[`publishing/`](file:///C:/Users/jorda/Desktop/Word%20Search%20Creator/kdp-puzzle-engine/publishing):** Multi-marketplace management system, SQLite catalog database (`data/books.db`), and Etsy bundle tools.
- **`publishing/activity_packs.py` / `publishing/activity_pack_ui.py`:** Local printable activity-pack generation and guided Tkinter dialog, separate from commercial-book production gates.
- **`publishing/family_studio.py` / `publishing/studio_assistant.py`:** Family-facing navigation and bounded request interpretation; `studio_providers.py` shares validation across managed ChatGPT-authenticated Codex (`studio_codex.py`), loopback Ollama, and Guide; existing generators, cover approvals, catalog, and publishing gates remain authoritative.
- **`publishing/studio_cover_audit.py`, `studio_theme_recipes.py`:** Read-only measured/visual saved-cover reviews and explicit composite-group recipes/alternatives; no artwork approvals or source-bank writes.
- **`publishing/studio_recovery.py`, `studio_preview.py`, `studio_health.py`:** Versioned unfinished forms in the canonical catalog DB, actual PDF/image previews, and read-only readiness evidence. `tools/check_studio.py` provides the HP/Ollama diagnostic entry point.
- **[`publish_tools/`](file:///C:/Users/jorda/Desktop/Word%20Search%20Creator/kdp-puzzle-engine/publish_tools):** Chrome DevTools Protocol (CDP) browser automation utilities.
- **[`themes/`](file:///C:/Users/jorda/Desktop/Word%20Search%20Creator/kdp-puzzle-engine/themes):** Structured word-search theme JSON library organized by categories.
- **[`word_banks/`](file:///C:/Users/jorda/Desktop/Word%20Search%20Creator/kdp-puzzle-engine/word_banks):** Master vocabulary database, DWYL dictionary source data, and content libraries.
- **[`tests/`](file:///C:/Users/jorda/Desktop/Word%20Search%20Creator/kdp-puzzle-engine/tests):** Automated Pytest test suite.

- **`phone_studio.py`, `publishing/phone_web/`:** Loopback-only family pack workspace; checked planning through `studio_pack_planning.py`, persistent additive project/job tables and worker in `phone_pack_service.py`, actual previews/downloads, explicit bounded Codex assistance. No phone/network exposure or publishing actions. See `docs/PHONE_STUDIO_WORKFLOW.md`.

*Update this section if new major modules or sub-packages are added.*

---

## 11. KNOWN TECHNICAL DEBT

Agents should be aware of the following technical debt:
- **Monolithic UI File:** `word_search_creator.py` is ~6,700 lines long and contains multiple dialog classes and utilities.
- **Placeholder Integration Folders:** Directories under `integrations/` currently contain only `__init__.py` files.
- **Platform-Specific Assumptions:** Certain helper scripts contain hardcoded paths (e.g., `C:\Windows\Fonts` or `/tmp` references).
- **Synchronous JSON Loading:** Large JSON assets (`Guided_Builder_Master_Word_Bank.json`, 14+ MB) are read synchronously in some workflows.

> [!IMPORTANT]
> **Do not attempt broad refactors of these areas solely because they are technical debt.** Refactoring should only be done incrementally when directly relevant to a specific user-requested task.

---

## 12. DEVELOPMENT STYLE

- **Readability Over Cleverness:** Write clean, readable, explicit Python code rather than dense or complex meta-programming.
- **Follow Existing Patterns:** Match established code conventions and design patterns in adjacent modules.
- **Reuse Existing Code:** Check for and reuse helper functions across `word_search_creator.py`, `project_checks.py`, and `cover.py`.
- **Add Targeted Tests:** Write unit tests for new functionality or bug fixes in `tests/`.
- **Self-Documenting Code:** Write comments explaining *why* something is done (design intent, marketplace quirks), not just *what* the syntax does.
- **Minimal Dependencies:** Avoid adding new third-party dependencies unless strictly necessary and approved. No paid external APIs.

---

## 13. USER EXPERIENCE

This software is a practical, everyday publishing production tool for the user. When evaluating implementation choices, prioritize:
- Fewer manual steps and clicks
- Clear, descriptive GUI controls
- Human-readable error messages with suggested fixes
- Automation of repetitive tasks
- Safe recovery paths (backups and validation before commit)
- Low operational overhead and zero recurring costs
- Self-contained local operation

---

## 14. VERSION CONTROL & RECOVERY

- Before initiating risky or sweeping changes, ensure the repository state is clean and recoverable via Git.
- Never overwrite known-good theme files, master databases, or configurations without a verified fallback or backup copy.

---

## 15. AUTHORITY

**The user's explicit current instructions always take precedence over this document.**

If a requested change appears to conflict with one of these protective guidelines, explain the technical context and trade-off clearly before proceeding rather than silently ignoring the user's intent.




Chat integration services: `publishing/studio_chat_creation.py` owns confirmed local creation; `studio_chat_families.py` adapts supported non-Sudoku plans; `studio_chat_revisions.py` and `studio_revision_adoption.py` stage/adopt owned Sudoku changes with original preservation. `studio_theme_catalog.py` provides exact full-content identities and retained source aliases; `studio_project_queries.py` resolves read-only selected-project status and previews. Existing art/content/publishing gates remain authoritative.

`studio_session.py` stores bounded conversation snapshots in existing completed recovery rows and restores canonical book IDs/pending decisions without action replay. `studio_chat_wordsearch.py` adapts checked groups to the unchanged gated Word Search pipeline; `studio_holiday_reuse.py` explicitly reuses the fixed existing holiday candidate after fresh QA without generating a duplicate. Custom hybrid recipes remain unsupported.
