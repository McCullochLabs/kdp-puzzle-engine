# Content Expansion Campaigns — Phase 2

When you choose **Expand content**, the app first gathers screened candidates
already present in the local content registry. They are saved in
`data/content_expansion_candidates.json` with stable IDs, source content IDs,
topic, target puzzle type, normalized text, provenance, quality tier, and
`generated_unreviewed` status.

This is a review supply, not a source-bank rewrite. Candidates still need an
explicit human approval through the review screen before they count as strict
content. Gemini, external discovery, and any paid API call remain off unless a
future explicit action enables them.
