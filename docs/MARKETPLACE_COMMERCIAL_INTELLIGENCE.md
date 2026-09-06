# Marketplace Commercial Intelligence V2

Marketplace Commercial Intelligence is a read-only planning layer over verified product facts, Content Intelligence, BookPlan, Product QA, the Publishing database, and Listing Intelligence.

It answers five practical questions:

1. What commercial product archetype fits the idea?
2. Which puzzle format best substantiates that promise?
3. Which marketplaces naturally fit the verified product?
4. How should the listing and merchandising differ by marketplace?
5. Is the idea distinct and close enough to production to pursue?

## Authority boundaries

- Content Intelligence owns content capacity and eligibility.
- BookPlan owns approved product facts.
- Production Gate and Product QA own release readiness.
- Cover approval owns permitted visual assets.
- Publishing Database owns catalog and marketplace state.
- Listing Intelligence owns Gemini-first/local-second buyer copy, with local factual validation.
- Commercial Intelligence describes product fit. It cannot override any authority above it.

All `internal_heuristic_points` fields are explainable local planning signals. They are not sales, demand, search-volume, competition, ranking, or profitability metrics.

## Flow

```text
Idea → Archetype → Format fit → Marketplace fit
     → Strict content/catalog evidence → BookPlan → Production
     → Marketplace-specific listing and merchandising → Human review → Handoff
```

No commercial analysis creates a book, calls an external service, publishes a listing, or changes marketplace status.

## Listing Intelligence integration

Gemini receives a compact verified fact sheet and the target marketplace. Its prompt forbids invented counts, product formats, features, market metrics, or approval claims. Local validation rejects factual contradictions. If Gemini is unavailable or unsafe, deterministic local copy remains marketplace-specific.

Human-edited or locked fields remain protected. When product facts change, the application should flag those fields for review instead of silently replacing them.

## Book Assistant

If a plain-English idea does not map directly to a saved theme or creation command, Book Assistant now returns a compact Commercial Fit explanation. It names the likely archetype, best format, alternatives, marketplace fit, warnings, and the next safe step. It does not create anything from that guidance.

