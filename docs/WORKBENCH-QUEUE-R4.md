# Persistent maintenance review annotations

`workbench queue` retains evidence-based findings. Review metadata is a separate
immutable chain per tenant, immutable object ID and finding type. Recording an
owner, rationale, review date, exception expiry or linked proposal never resolves
a finding, approves an exception, authorizes execution or changes policy state.

Use a bounded JSON input:

```json
{
  "schema_version": "workbench-queue-review-input/1",
  "tenant_id": "TENANT_UUID",
  "object_id": "OBJECT_UUID",
  "finding": "ownership_unknown",
  "owner": "Endpoint operations",
  "rationale": "Confirm the declared stack writer before reviewing a change.",
  "review_due": "2026-11-01T12:00:00Z",
  "exception_expiry": "2026-11-02T12:00:00Z",
  "linked_proposals": []
}
```

```bash
python3 -B scripts/intune-iac.py workbench queue-amend \
  --root PRIVATE_STORE --input REVIEW_JSON --expected-prior none
python3 -B scripts/intune-iac.py workbench queue-review \
  --root PRIVATE_STORE --object OBJECT_UUID --finding ownership_unknown
python3 -B scripts/intune-iac.py workbench queue-review-history \
  --root PRIVATE_STORE --object OBJECT_UUID --finding ownership_unknown
```

The first amendment requires `--expected-prior none`. Each subsequent amendment
requires the exact current artifact SHA-256. The store compares that prior and
appends under one `BEGIN IMMEDIATE` transaction. Two concurrent callers using the
same prior cannot both advance the chain. A retry with an old prior is a conflict;
read the current chain before preparing another amendment. Earlier owner values,
rationales, dates, source-file SHA-256 and proposal references remain inspectable.

Allowed object findings are `observation_stale`, `collection_incomplete`,
`reporting_incomplete`, `ownership_unknown`, `ownership_conflicting_claims`,
`ownership_stale`, `ownership_unclaimed` and `ownership_elsewhere`. The global
`no_complete_observations` finding uses `object_id: null` and omits `--object` in
inspection commands. Object-bound annotations retain the existing store's
observed/pending-object identity requirement. This is a review overlay, so a
finding disappearing from the generated current queue does not delete its review
history or prove that the annotation caused a repair.

Owner is a bounded string or null, and rationale is required bounded plain text.
Dates are timezone-aware ISO timestamps or null. An exception expiry requires a
review date no later than that expiry. Past dates are retained and shown as overdue
or expired. Both dates are metadata only: no exception approval is inferred from
a future expiry. Owner identity and recorder identity remain unverified local
annotations, distinct from cross-stack ownership evidence.

`linked_proposals` can contain up to 32 unique typed references:

```json
{
  "kind": "maintenance_operation",
  "operation_id": "EXISTING_OPERATION_ID",
  "approval_digest": "EXACT_APPROVAL_DIGEST"
}
```

Each reference must match an existing same-object operation record and the actual
retained maintenance plan, tenant, store and plan digest. The recorded relationship
means the local proposal identity was verified **at recording**. It does not
approve the proposal, extend its expiry, execute it or certify its later success.
Unsupported external proposal types are rejected. Global findings cannot link an
object operation. Changed, missing, wrong-tenant or wrong-object proposals fail
before append.

Writer ownership comes from the latest bounded cross-stack ownership index,
with per-object immutable IDs, independent object/assignment claims, selected
repository-intent scope, freshness and completeness. A source `owner` string is
retained separately as `source_owner_claim`; it never establishes a writer or
suppresses a finding. The `owner` field is explicitly a human review assignee,
with `owner_role: human_review_assignee`, and is populated by review annotations.
`writer_ownership` remains separate even when a reviewer has been assigned.

Fresh conflicting claims, stale evidence, no writer found in complete fresh
scopes, and a writer elsewhere have distinct finding codes. Missing/incomplete
scope evidence remains `ownership_unknown`; it cannot prove no writer. Known
`owned_here` removes only the ownership review finding, not unrelated collection
or reporting findings. Ownership artifacts and repository intents are read once
per queue call and claims indexed by object, avoiding a full artifact scan for
every object. All claims remain scoped local evidence without execution authority.

When an evidence change changes a finding code, prior annotations remain in the
old finding's immutable history. They are not automatically transferred to the
new finding or silently deleted. For example, assigning a reviewer to
`ownership_unknown` does not assign that reviewer to a later
`ownership_conflicting_claims` finding.

The queue displays review owner, rationale, dates, current review artifact and
linked proposals without suppressing original evidence reasons or changing
`action_state` and `automatic_remediation`. History is bounded by the existing
store's 1,000-row and query-byte limits; exceeding a bound fails rather than
silently truncating the chain. Same-user writable SQLite history is not an
independently protected audit anchor. Native host and organizational review
identity qualification remain separate gates.
