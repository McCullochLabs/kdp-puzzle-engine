# Family activity-pack workflow — implemented

The local web workspace now creates real activity packs, saves projects on the HP, runs durable background jobs, previews actual PDF pages and provides activities, answers and ZIP downloads. Open http://127.0.0.1:8765 on the HP, or run `Start Phone Studio Prototype.bat` in the Studio folder. The launcher keeps its existing filename for continuity.

## Working flow

Create an activity pack → choose reader, theme, activities and length → check the plan → Create my pack. Projects and jobs are saved in additive tables in the existing `data/books.db`; output goes into unique per-job folders under `data/phone_packages`. The original book catalog and desktop draft tables are preserved. My projects reopens choices and earlier completed pack revisions. Browser-era drafts can be explicitly imported without deleting their browser copy.

Repeated Create calls for the same project revision return the existing queued, running or ready job. Each job captures an immutable revision. Concurrent stale edits are rejected instead of overwriting saved choices. A single background worker is protected by a process lock. Closing or reloading a browser does not cancel generation. Queued jobs resume after service restart; an interrupted running job is marked honestly and requires an explicit retry. A completed job remains downloadable after restart. Generation progress names actual stages; no invented percentage is shown.

The worker reruns checked word selection and existing activity-plan validation before using the unchanged generator. The generator verifies PDF page counts, nonempty pages and US Letter page geometry. These are printable activities requiring human review, not publishing-approved books. File endpoints accept only known artifact kinds for ready jobs, with output-root containment checks. Previews render the actual saved PDF and reject out-of-range pages.

## AI access

The Home screen has an optional “Describe an idea with AI help” disclosure and an explicit “Ask ChatGPT/Codex” button. It uses the existing bounded Codex adapter and existing ChatGPT sign-in. There is no automatic provider fallback. AI proposes choices; existing theme, group, reader and generation checks remain authoritative. Navigation, local word sorting, project saves and pack generation do not invoke AI. Failed or unsupported proposals leave the guided buttons available.

No live model requests were made during this implementation verification. The adapter was previously verified in this integration; new routing and failure behavior were tested with controlled provider responses. The actual AI button consumes the existing allowance when a user chooses it. This does not claim a fresh live-model smoke test.

## Verification

- Full regression suite: **1,001 passed in 166.24 seconds**.
- Initial focused run: 62 passed; subsequent full run includes the added complete HTTP workflow and exclusive-worker tests.
- Tests cover immutable job snapshots, edit conflicts, duplicate creation, queued/ready restart persistence, interrupted recovery, failed-job retry, real PDF/PNG/ZIP outputs, path containment and same-origin request checks, and bounded Codex proposals with no fallback.
- Browser created “Family Space Adventure”: six activity pages plus an introduction in each of the two PDFs, ages 6–8 profile, word searches/scrambles/Sudoku. Reloading the page reconnected to the completed job, exposed all three downloads and rendered the real first activity.
- JavaScript syntax and Python imports checked; dependency check passed. No new dependency was added.
- Catalog backed up before adding job/project tables. Original vocabulary, generators, artwork approval and publishing behavior remain unchanged.

## Phone access remains a separate setup

This is a complete local activity-pack workflow, not a deployed phone app. The service deliberately binds only to 127.0.0.1 and rejects other Host origins. It currently represents one trusted local workspace, without family accounts or device pairing; do not expose its port or proxy it publicly.

Secure phone use still needs authenticated device access, private HTTPS routing and real iPhone/Android tests. Tailscale was not found on this HP. No network exposure, firewall change, account enrollment, installation or public publishing was performed. Full puzzle books and cover controls remain later additions.

## Files added or changed

Added `publishing/phone_pack_service.py`, `tests/test_phone_pack_service.py`, and this `docs/PHONE_STUDIO_WORKFLOW.md`. Updated `phone_studio.py`, `publishing/studio_pack_planning.py`, `publishing/phone_web/index.html`, `publishing/phone_web/app.js`, `publishing/phone_web/style.css`, `tests/test_phone_studio.py`, and the module description in `AGENTS.md`. No source files removed.

Actual service restart check also passed: the completed Family Space Adventure job reopened with activities, answers, ZIP links and its real PDF preview intact. The service is left running on the HP.
