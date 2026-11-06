# Preview, recovery, and local Ollama improvement pass

Starting checkpoint: `cf87db5`. GitHub main was checked during this pass and remains `2c48b7134745044781a9d1cdf4f60ea893f6e0aa`.

## Implemented

- Actual printable-pack PDF previews, including introduction, first activity, and matching answers. Valid form edits refresh the preview using the same seed. Saved catalog PDFs and covers are previewed from their actual files and refreshed on file changes. Rendering is outside the Tk event loop and PDFium access is serialized.
- Selected-book context for the guide/local model. Cover requests keep the selected book identity captured when the request was made, even if selection later changes. Another-version requests start a new plan using the selected topic/type; they do not overwrite an existing product.
- Versioned unfinished forms in the canonical catalog SQLite database. Pack inputs and simple book-editor values/words can be recovered. Pack undo retains all versions. No existing book metadata, publication statuses, source themes, or finished products are overwritten by draft persistence.
- Existing local Ollama discovery. A sole installed local model connects for an unconfigured interface; multiple models require selection and explicit Guide mode remains respected. No downloads, cloud model, paid API, or extra Codex agent is involved.
- Read-only runtime/artwork/model diagnostics in Settings and tools/check_studio.py. An optional explicit inference smoke command is provided for the HP. Missing artwork is reported rather than replaced or automatically approved.
- Actionable GUI callback error reporting, close-time draft flushing, and cancellation of pending dialog callbacks on destruction.
- A short task-based family usability protocol. Actual family testing has not been performed.

## Verification

Runtime: 64-bit CPython 3.13.11, exact requirements-dev.txt pins. Runtime check passed.

Full command: `python <virtual-desktop-runner> -m pytest tests/ -q --disable-warnings`.
Result: **797 passed, 6 failed, 1 skipped** in 26.71 seconds. The six failures are the previously reproduced baseline failures in legacy/approved cover-art selection, Windows Credential Manager availability, a Windows-specific font-path assertion, and missing-artwork theme validation. Production gates were not bypassed to obtain a green result.

Final focused command: `python <virtual-desktop-runner> -m pytest tests/test_studio_recovery.py tests/test_studio_preview.py tests/test_studio_health.py tests/test_family_studio.py tests/test_activity_pack_ui.py tests/test_studio_assistant.py -q`.
Result: **37 passed**, 4.12 seconds. This final run follows the small duplicate-resume and concurrent-undo guards added after the full suite.

`git diff --check` passed. The preview integration test renders actual PDF pages and verifies deterministic image output, rather than a placeholder. Recovery tests reopen SQLite state, preserve invalid intermediate input, undo across versions, and prove existing Published data remains unchanged. Local-AI tests use simulated responses; no live HP model inference was claimed.

## Files changed

Existing: AGENTS.md, CHANGELOG.md, docs/FAMILY_STUDIO.md, publishing/activity_pack_ui.py, publishing/family_studio.py, publishing/studio_assistant.py, word_search_creator.py, and the associated activity-pack/family/assistant tests.

New: publishing/studio_preview.py, publishing/studio_recovery.py, publishing/studio_health.py, tools/check_studio.py, their tests, docs/FAMILY_USABILITY_CHECK.md, and this report.

## Remaining external verification

The HP is not accessible from this workspace. Its actual assets, Windows scaling, local model inference/latency, physical print proof, and uncoached wife/children testing remain unverified. Follow docs/FAMILY_STUDIO.md and docs/FAMILY_USABILITY_CHECK.md on that computer.

This pass is a local code checkpoint. GitHub publishing still requires an authenticated write connection; no remote branch, merge, or HP deployment is claimed.
