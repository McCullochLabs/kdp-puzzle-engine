# Content Expansion Campaigns — Phase 4

Phase 4 adds one optional live provider: Gemini, reusing the existing Windows Credential Manager entry used by Listing Intelligence. No second secret store is created.

## Operator flow

1. Check a blocked exact Word Search format.
2. Create an expansion campaign. This searches only existing local candidates.
3. Select **Generate new candidates**.
4. Review the preview and external-call notice, then explicitly confirm.
5. Gemini returns structured candidate JSON. The app screens it and stores surviving rows as `generated_unreviewed` with Gemini provenance.

No action is taken while opening a campaign. No provider result is auto-approved, added to source banks, or used to generate a book.

If Gemini is not configured, the button reports that clearly and the local review workflow remains usable.
