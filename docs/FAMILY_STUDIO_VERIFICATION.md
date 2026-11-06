# Family Studio verification

Source baseline: `2c48b7134745044781a9d1cdf4f60ea893f6e0aa`.
Printable-pack checkpoint: `e294693`.

## Environment and results

Used 64-bit CPython 3.13.11 and the exact requirements-dev.txt dependency pins. A virtual X desktop was used for actual Tkinter window construction and interactions; no extra Codex agents or external AI review sessions were used.

- `python tools/check_runtime.py`: passed.
- Full suite under the virtual desktop: **783 passed, 6 failed, 1 skipped**, 25.06 seconds.
- All six failures reproduce on the pristine baseline (see ACTIVITY_PACK_VERIFICATION.md). They concern missing/unapproved cover assets, a Gemini credential expectation, a Windows path assertion, and theme validation blocked by missing artwork. None were bypassed or weakened.
- Final focused UI/assistant tests: **25 passed**. These include two further integration tests added after the full run: opening/returning from the advanced workspace and fitting the cover-generator action buttons.
- Actual desktop smoke: family Home, Covers, three-step pack flow, small-window navigation and text entry; no Tk callback exceptions observed. The legacy workspace stayed uninitialized during initial startup. One smoke launch took approximately 0.067 seconds to create/show the main window on this cloud machine; this is not an HP performance measurement.
- Generated and rendered personalized pack PDFs; inspected representative activity and answer pages and corrected wrapping.
- `git diff --check`: passed.

## Model verification boundary

The interpreter was tested with deterministic requests and simulated Ollama API responses, including invalid JSON, unsupported actions, remote/cloud model filtering, confidence validation, bounded conversation, and redirects. No real model was downloaded, trained, selected on the HP, or tested for inference quality/speed. No paid API or extra Codex session was used.

## Delivery and remaining checks

The HP was not accessed or updated. Windows font scaling, actual saved data/artwork, physical printing, real-model operation, and uncoached family usability remain acceptance checks. Existing GitHub source is missing artwork that may still exist locally on the HP.

The branch could be read locally but a GitHub push dry run failed because this session has no authenticated GitHub write connection. No remote branch, pull request, merge, or deployment was created in this session. Keep the changes isolated and reconcile any unpushed HP edits before applying them.
