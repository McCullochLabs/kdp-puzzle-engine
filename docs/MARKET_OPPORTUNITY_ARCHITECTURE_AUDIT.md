# Market Opportunity Intelligence — Architecture Audit

## Reused systems

- `word_intelligence`: taxonomy, capacity proof, review gates, planning, candidate generation, and topic routing remain the source of truth for what content can be used.
- `publishing/production_gate.py`, `production_proof.py`, and `production_dashboard.py` remain the source of truth for production safety.
- `publishing/business_automation.py` already supplies explainable local opportunity ranking, action queues, digital-product suggestions, and seasonal relevance.
- `publishing/commercial_intelligence.py` already evaluates local buyer-value clarity and marketplace preparation without claiming sales data.
- `publishing/database.py` is the shared SQLite catalog for books, marketplace history, queues, release locks, bundles, and reviews.
- `publishing/listing_intelligence.py` and the existing Gemini credential store remain optional and explicit; no market-research provider will be called automatically.
- `publishing/ui.py` already includes a Publishing Center opportunity tab; any new display should extend it rather than add another main window.

## Extension plan

1. Add a read-only production capability audit that classifies each current generator and publishing component as Green, Yellow, Red, or Unknown with local evidence.
2. Normalize the existing opportunity rows into persistent Market Opportunity records with evidence type (`OBSERVED`, `DERIVED`, `ESTIMATED`, or `UNKNOWN`) and explainable factors.
3. Add an opportunity review gate before a controlled experiment can create a plan or join the existing approved queue.
4. Record experiment observations separately from marketplace status. No sales, ranking, or demand metric may be invented.
5. Feed confirmed local results back into the existing opportunity ranking and family/bundle suggestions.

## Risks and safeguards

- Existing `BusinessAutomation.opportunities()` is catalog-centric, not an external market-data source. Its scores must be labeled as local, derived production guidance.
- Topic capacity and production readiness must never be replaced by a commercial score.
- User-created topic connections are overlays; they must not silently rewrite the Master Library.
- Marketplace history, release locks, source banks, and human-review decisions remain protected by their current systems.
- Resource-heavy generation stays in existing background/queue paths. Opportunity analysis stays local and read-only.

## Migration

All new records will be additive in SQLite or JSON state. Existing books, plans, packages, and marketplace records remain compatible and unchanged.
