# Phone Studio — Phase 1 plan and prototype

Owner direction: build a simpler family phone workflow, conserve development and routine AI usage, and prefer ChatGPT/Codex when judgment is helpful. Keep provider replacement possible. No live AI calls are needed to test these screens.

## Scope

Deliver a responsive, functioning screen prototype: Home → choose an activity pack → review the plan → save and reopen a browser draft. This is the smallest useful slice for judging whether the family flow feels simpler. Existing desktop functionality, canonical drafts, bank files, artwork approvals and generators remain authoritative and unchanged.

This phase starts implementation, not a production phone rollout. The launcher binds only to 127.0.0.1. It is not reachable from a phone yet. No network/firewall change, accounts, HTTPS, installation manifest, background generation or remote access is included. Those belong to the connected service milestone.

## Screens

1. Home: Create an activity pack, My drafts, a clear prototype notice, and a short AI explanation. Books and cover review are visibly deferred.
2. Your idea: pack name, suggested theme, reader, activities and page count. Theme balance is under one optional disclosure. No vocabulary maintenance or provider controls in the family flow.
3. Review: all chosen fields, automatic-word-selection explanation, save draft. It explicitly says vocabulary has not been checked and no PDFs have been created. There is no pretend generation or download action.
4. My drafts: reopen actual browser-saved choices. Repeat saves update the same draft; a new pack starts a new draft. Storage failure must never report success.

## Design requirements

- Single column at phone widths, no horizontal scrolling, touch controls at least 48px tall, readable contrast and labels.
- Keyboard navigation, visible focus, screen reader status announcements and headings focused on screen changes.
- Plain language and minimal choices. No model names in ordinary activity controls.
- Suggested themes in the prototype only; all eligible bank groups are a connected-service requirement.
- Read actual reader, balance and activity options from existing Python modules. Do not duplicate their rules in a second engine.
- Browser drafts are explicitly temporary, local to the browser, and separate from canonical desktop drafts. No claim of cross-device recovery.

## AI policy for connected implementation

Prefer the existing ChatGPT/Codex adapter for free-form interpretation, difficult theme planning and optional visual cover judgment. Use existing local rules for vocabulary selection, page counts, directions, generation, checks and status. No AI calls on navigation or routine field edits. Retain Ollama and Guide as explicit alternatives; no silent provider fallback. Validate every AI proposal through shared application rules. Cache reviews against the exact files reviewed. Never claim AI alone guarantees an outcome or approves artwork.

## Acceptance checks for this phase

- Open at 390px and desktop width; inspect all screens and touch controls.
- Create a Homesteading plan with a child reader and confirm the review preserves every choice.
- Save, reload, reopen, edit and save again; one draft should be updated.
- Start another plan and ensure the original survives.
- Handle invalid choices and unavailable browser storage without data loss claims.
- Confirm only allowlisted prototype assets/config are served, remote Host requests fail, POST cannot start work, and bank/catalog files are not served.
- Confirm no model or generator has been invoked. Run focused new tests plus existing reader tests; shared engines are unchanged.

## Next implementation slice

1. Extract a small shared activity-pack planning operation using the current sorter and validators, with real shortage messages and all eligible groups.
2. Introduce authenticated project ownership and versioned canonical persistence; migrate a browser draft only through explicit import and validation.
3. Add persistent jobs and safe output downloads. The phone must reconnect after sleep without duplicate generation.
4. Add private HTTPS access, device pairing and real iPhone/Android tests before calling it a usable phone release.
5. Connect existing AI interpretation with ChatGPT/Codex preferred when needed, then add full books and cover review.

No new dependency, paid service or live inference is required for Phase 1. Engineering checkpoints are acceptance-based; no unsupported completion-date or fixed usage promise.

## Run

From the Studio folder: `.venv\Scripts\python.exe phone_studio.py`.
Open `http://127.0.0.1:8765` on the HP. Stop with Ctrl+C. Use `--port` if necessary. An optional `Start Phone Studio Prototype.bat` launcher starts the same service.

## Summary

Phase 1 establishes the simple family workflow and implements a real local screen prototype. It saves actual browser drafts but does not generate puzzles, call AI or provide phone access yet. The next slice connects checked planning and durable jobs before enabling private phone access.

## Implementation evidence

Implemented on 2026-10-21. `tests/test_phone_studio.py` and `tests/test_reader_and_balance.py`: **22 passed**. Browser check confirmed Home → Homesteading plan → ages 9–12 review → save → reload → reopen with all choices retained. Activity defaults were checked and corrected during that trial. A screenshot is saved alongside the delivered plan.

Implemented files: `phone_studio.py`, `publishing/phone_web/index.html`, `publishing/phone_web/style.css`, `publishing/phone_web/app.js`, `tests/test_phone_studio.py`, `Start Phone Studio Prototype.bat`, `docs/PHONE_STUDIO_PHASE1.md`. Updated `AGENTS.md` only to describe the new module. No desktop engine, bank, catalog, existing provider preference or dependency change.

Remaining validation: real 390px/device layout, browser storage failure interaction, repeated-edit/new-draft edge cases and actual family feedback. These are not claimed complete. Real phone connection, canonical shared projects, generation and AI wiring remain the next implementation slices. This turn exercised no live AI provider or generator.
