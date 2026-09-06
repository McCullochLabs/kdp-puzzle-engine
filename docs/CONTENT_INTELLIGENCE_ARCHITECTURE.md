# Content Intelligence Architecture — Phase 1

## Current implemented shape

```text
Legacy Sources
  ├─ Guided_Builder_Master_Word_Bank.json
  ├─ puzzle_content_library.json
  └─ Theme JSON files
        ↓
Backward-Compatible Read-Only Loaders
        ↓
Canonical Content Contracts
  ├─ stable deterministic IDs
  ├─ content types
  ├─ display and normalized values
  ├─ canonical topic references
  ├─ independent review states
  ├─ provenance
  ├─ format-rule hooks
  └─ schema versioning
        ↓
Shared ContentRegistry Interface
        ↓
Existing Word Intelligence and Existing Generators
```

## Public compatibility decision

`word_intelligence` remains the public package. The Phase 1 contracts live
inside it so no production import path changes and no second intelligence
engine is created. A future product-facing name, `Content Intelligence`, may
be introduced through this same package after adapter and planner work is
complete.

## Existing behavior intentionally preserved

- Word Search placement and its 21-letter source validation are unchanged.
- Sudoku generation and unique-solution checking are unchanged.
- Existing `WordRecord`, taxonomy, pool building, quality gates, and
  production truth remain the active production logic.
- Gemini remains optional and is not authoritative for content truth.
- No source JSON, cache, theme, package, publishing record, or marketplace
  history is migrated by Phase 1.

## Cache-manifest foundation

`word_intelligence.cache_manifest` can fingerprint every current store input
and report `fresh`, `stale`, `missing_manifest`, or `unsupported_manifest`.
It does not rebuild or overwrite caches. Cache-aware rebuilding belongs to a
later phase after the UI and background-work strategy are approved.

## Future work, not implemented here

1. Verified per-format capacity.
2. Reservation-aware and cross-series freshness.
3. Deterministic shared book plans.
4. Puzzle-type adapters and themed Mixed planning.
5. Release locks tied to plans and file checksums.
6. UI readiness and recovery improvements.
