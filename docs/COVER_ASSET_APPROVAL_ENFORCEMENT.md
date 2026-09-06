# Cover Asset Approval Enforcement

## Production rule

Every production cover must identify one registered project-generated background whose approval is current for the exact file bytes being used. A generated image is not approved merely because generation completed or because it exists in an approved-looking folder.

Preview-only rendering may show an unapproved candidate for human review. It does not create production approval evidence and cannot be used to create a wrap, lock a proof, pass Product QA, reach Final Review, or open Ready Platform Preview.

## Authoritative record

`cover_assets/generated_background_index.json` is the authoritative asset registry. `background_generation.index.BackgroundAssetIndex` is the sole reader and validator used by production selection.

The supported states are:

- `awaiting_review` — generated and available for review, but unusable in production.
- `approved` — explicitly approved and usable only while its recorded SHA-256 matches the file.
- `rejected` — explicitly rejected and unusable.
- `unknown` — incomplete or unrecognized approval information; unusable.
- `missing` — no registered record or no source file; unusable.

Production eligibility additionally requires project-generated provenance, an accepted classification, an existing source file, and a matching SHA-256 checksum. Folder placement and filenames never grant approval.

## Human approval workflow

1. Generate a background. It is registered as **Awaiting review**.
2. Open the pending image in the Background Generator.
3. Select **Approve** or **Reject** and confirm the choice.
4. Approval moves the candidate to the approved library, records a new checksum, and increments its approval revision.
5. Production selection may now use it. Rejection remains recorded and fail-closed.

There is deliberately no Approve All action and no automatic promotion after generation.

## Enforcement boundaries

Approval is checked independently at each boundary:

- cover recommendation and automatic selection;
- manual package and production-queue selection;
- direct `cover.py` production rendering;
- `wrap_cover.py` full-wrap creation;
- package release-contract validation;
- Product QA and production intelligence;
- release-lock and production-proof lock;
- Final Review and Ready Platform Preview.

The cover renderer writes a fingerprint-bound `<front-cover>.approval.json` proof containing the asset ID, asset checksum, approval state, approval revision, provenance, and rendered front-cover checksum. The wrap and later stages require that proof. Editing either the approved source asset or the rendered front cover invalidates it.

## Failure behavior

Unsafe paths stop with **COVER ART REQUIRED** and explain that an approved matching background must be selected or reviewed. Production does not silently substitute generic art, reuse a stale cache result, or continue with an unregistered local file.

Existing historical packages remain read-only. They are not silently upgraded. A historical package without current approval proof must be reviewed and rendered as a new revision before it can pass the current release contract.

