# Production Orchestrator

The Production Orchestrator is the local source of truth for where a book is in production and what may safely happen next. It coordinates the existing specialist engines; it does not replace puzzle, cover, QA, listing, package, or marketplace code.

## Canonical stages

1. Book idea
2. Feasibility
3. Content plan — human approval required
4. Generation
5. Cover
6. Product QA
7. Listing
8. Package
9. Final review — human approval required
10. Platform preview
11. Marketplace handoff — human action required

Each job is saved atomically in `data/production_jobs/job_<stable-id>.json`. The record contains stage status, evidence, artifacts, errors, and component-specific fingerprints. It never publishes, uploads, purchases, orders, or changes marketplace state.

## Human gates

Content-plan approval, final local review, and marketplace handoff require both an explicit approval and persisted evidence containing a source and evidence ID. Generic book IDs, opening a file, generating a preview, or passing automated QA do not count as human approval.

Final local review is tied to the existing locked production proof in the Publishing database. If that proof is missing or stale, approval is refused.

## Resume and stale behavior

**Continue Production** runs only the next eligible automated stage. It stops at human gates. **Stop** pauses safely without deleting artifacts. **Retry** reruns only a failed or stale stage after its prerequisites remain valid.

A content or plan change makes generation and dependent stages stale. A cover-only change makes the cover and its dependents stale while leaving a valid interior current. Listing-only changes preserve the interior and cover. A missing recorded artifact makes that exact stage and its dependents stale.

The older Production Autopilot remains a compatibility checkpoint used by established generators. It creates/updates the canonical job, but it cannot approve a human gate. It may adopt a plan approval only when the caller supplies real persisted approval evidence.

## Operator index

`ProductionJobIndex` reads only the small job records, not large output trees. It supports filtering by status, puzzle type, blocker text, and priority. The Publishing Center can therefore answer what is waiting without opening every finished package.

## Recovery

A failed stage retains its plain-English reason, error type, retryability, and affected downstream stages. Correct the source problem, retry that stage, and then use Continue Production. Completed upstream stages are not repeated unless their own inputs changed.
