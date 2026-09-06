# Content Expansion Campaigns — Phase 3

Phase 3 adds a safe, provider-ready candidate-generation boundary. It does not automatically change the Master Library, approve content, alter existing themes, or rebuild products.

## How it works

1. A campaign calculates its measured shortage after the existing review pool is counted.
2. The app can preview the recommended candidate request count, using an explicit review-yield buffer.
3. A provider may be invoked only through an explicit generate action. The default local provider is disabled and makes no external call.
4. Generated output is screened before storage: duplicates, blanks, unsuitable types, overlong word-search entries, overlong cryptograms, and incomplete trivia are rejected.
5. Surviving output is stored as `generated_unreviewed`, with provenance. It is not added to the approved library until a human review decision is recorded.

## Provider safety

The provider contract is intentionally separate from listing-copy intelligence and does not inherit any credentials or external-call behavior. A future provider integration must expose availability, preserve the explicit-action requirement, provide provenance, and return candidates only through this review pipeline.

## Limits

This phase does not promise a complete book from generated candidates. Capacity stays truthful until content is reviewed and approved.
