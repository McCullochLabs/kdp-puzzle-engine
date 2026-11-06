# Phone Studio — checked planning connected

The next implementation slice is complete: the local phone-style interface can now prepare real activity-pack plans against the existing vocabulary bank. It still runs only on the HP at http://127.0.0.1:8765.

## What works

- All 170 distinct topic/group names from the master library are available in the theme selector (82 topics and 110 packs, with overlap).
- Review calls a shared Python planner using the existing word sorter, topic evidence, reader rules and activity-pack validator.
- Review shows actual checked word counts and source groups, plus editorial notes. It never implies that vocabulary checks are publishing approval.
- Insufficient vocabulary stops the plan and offers fewer pages, a different reader setting or another theme. No invented words, repeated filler or unrelated replacements.
- Sudoku-only plans do not load word selection; child-reader topic restrictions still apply.
- Browser drafts continue to save and reopen. Earlier suggestion-only themes remain preserved and require a new explicit library selection.
- In-flight responses are ignored after navigation, and changed form choices cannot receive a stale checked result.
- A one-at-a-time planning gate avoids overlapping heavy selection. A blocked request gets a clear retry message.
- The new POST route accepts only bounded JSON from its exact local origin. File routes remain allowlisted; no arbitrary files or generation commands are exposed.

## Boundaries and next work

No AI provider or generator is called by this planning step. ChatGPT/Codex remains the preferred provider for the upcoming free-form request and judgment integration. Routine selection and validation stay local.

This is not the finished phone release. Authentication, device pairing, HTTPS, actual phone access, shared durable projects, persistent generation jobs, PDF downloads and AI interpretation remain to be connected. Current drafts are browser-local; a checked result is recomputed when reviewed and is not a durable generation job. Original desktop workflows and production gates remain unchanged.

## Verification

Focused planner, endpoint and reader checks: **44 passed in 19.28 seconds**. Tests included actual Space vocabulary for ages 6–8, composite Homesteading selection, unique words, server request validation, concurrency handling, shortages, all-library enumeration and unchanged hashes of the original master/store/editorial files. The browser was used to check the connected workflow; results are recorded below after that check.

## Files

Added `publishing/studio_pack_planning.py` and `tests/test_studio_pack_planning.py`. Updated `phone_studio.py`, `publishing/phone_web/index.html`, `publishing/phone_web/app.js`, `tests/test_phone_studio.py` and the architecture note in `AGENTS.md`. Added this report as `docs/PHONE_STUDIO_PLANNING.md`. No existing engine, catalog schema, artwork approval, provider preference or dependency was modified.

Final compatibility run: **65 passed in 20.33 seconds** (`tests/test_phone_studio.py`, `tests/test_studio_pack_planning.py`, `tests/test_reader_and_balance.py`, `tests/test_activity_packs.py`). Browser verified a six-page Space & Astronomy pack for ages 6–8 with 16 different checked words and saved its choices. Evidence screenshot: `PHONE_STUDIO_CHECKED_PLAN.png` in the delivered outputs. Real-device layout testing and secure phone connectivity remain pending; no claim of phone deployment is made.
