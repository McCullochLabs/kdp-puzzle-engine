# Editorial Content Review

Use **Book Readiness** to check an exact book format. If it is blocked only by
reviewed-content capacity, choose **Create review batch**.

The batch is small, topic- and format-specific, and ranks candidates as:

- **Strong Candidate** — clean, topic-linked, format-safe content.
- **Review Carefully** — useful but needs editorial attention.
- **Poor Candidate** — likely duplicate, too long, incomplete, mechanical, or
  otherwise unsuitable for the selected format.
- **Reject Recommended** — clearly unsafe or invalid; it still requires a
  human decision and is never automatically changed.

Select individual candidates and use **Approve selected**, **Reject selected**,
or **Skip for now**. You may also use A, R, or S while the review window is
open. There is intentionally no Approve All action.

Approvals are stored as an editorial overlay in
`data/content_approval_decisions.json`; source word banks are not rewritten.
An append-only trail is recorded in `data/editorial_review_audit.jsonl` when
you make decisions. The next content check uses that overlay in strict capacity
and changes the content revision used by Book Plans.

Approving enough material changes the status to **Ready to Plan**. It does not
create a plan, generate a book, make a cover, or publish anything automatically.
