# Separately approved verification after a stopped Plan

This proposal extends the existing Plan-only dispatcher with one distinct
phase-bound manifest, not another executor. Original import lease recovery uses
`native-adoption-recovery-plan/1` and its existing signature unchanged. A fresh
exact `LiveAdoptionPlanRecoveryCompletion` or
`LaboratoryAdoptionPlanRecoveryCompletion` selects v2:

- Manifest `native-adoption-recovery-plan/2`, action `native_first_plan_only`.
- Approval `signed-native-adoption-recovery-plan-approval/2`.
- Signed bytes `b'intune-workbench:native-adoption-recovery-plan-approval:v2\x00' + canonical(payload)`; the delimiter is an actual NUL.
- The existing approver policy, authority database and reservations apply.

`make_manifest(original=..., completion=..., ...)` selects the version from the
exact sealed completion. JSON, a caller boolean, the original import completion
or a signature for the other version cannot supply the new phase authority.
The reviewed `recovery_binding` adds `phase` (kind, operation ID, manifest hash,
registered job root) and the exact `ancestors` list to the existing signed-release,
state and projection facts. `initial_verification` references the old adoption
job; `recovery_plan` references its registered immutable Plan job. The selected
phase's original host, journal, row/outcome hashes and receiving proof are bound
by the separate stopped-Plan release capability. No old import or Plan is rerun. Exact typed phase selectors are resolved before
opening the caller-owned database transaction; their registered phase/original
rows are then rechecked through that same transaction. This avoids constructing
a new ServicePolicy (which initializes schema under BEGIN IMMEDIATE) inside
an existing write transaction.

The new Plan uses fresh private job storage, a fresh ID, a separately signed
approval, the same fixed provider Plan-only controls and the shared strict
no-change output proof. Before dispatch, a single common-authority transaction
consumes the approval, stores its exact transcript, records controller identity
and appends `adoption_plan_successors`. That relation records the selected old
phase, exact old/new manifests and signed recovery operation. An insert failure
rolls back consumption and dispatch. Prepared or cancelled-before-dispatch jobs
create no edge and transfer no ownership.

Only the recovered selected phase and its exact consumed ancestor chain can be
excluded from same-original Plan conflicts. Every edge must match its consumed
child's immutable reviewed v2 manifest, its declared remaining ancestors, the
unchanged prior row and the observed signed-release ledger. A v1 root terminates
the chain. A v2 node with a missing edge, orphan/foreign node, cycle, active
controller, changed outcome, unconsumed child or cancelled-before-dispatch child
fails closed. The maximum is 32 edges; a 33rd edge is refused. A stopped dispatch1
operation may retain a cancellation request, its spent approval and unknown
outcome; that does not permit execution or replace its required separate release.

The original adoption owns its scopes throughout. The old Plan rows/outcomes are
never rewritten. Successful fresh state/Graph proof, strict no-change Plan,
empty metadata and confirmed cleanup allow the existing final reconciliation to
release only the original scopes as `adopted_verified_execution_unknown`. The
original import execution remains unknown. Baseline disposition and ordinary
apply permissions are unchanged.

Existing `adoption recovery-plan-*` and `adoption-plan-*` text/TUI inspection use
the same job class. Review displays the correct versioned signature domain and
exact ancestor/phase facts. No command mints a runtime, signs an approval or
executes a worker. Portable export must explicitly validate the new domain before
claiming support; v1 evidence is never upgraded or relabeled.

The current tests use real independent Ed25519 signatures and constructed common
SQLite histories. Admission/runtime seams in the atomic-recording controls are
explicitly injected; no native phase execution or backend recovery is established
by these tests. Actual native initial-verification and interrupted-recovery-Plan
journeys remain required before qualification of this route.

The retained real-constructor control reproduces nested ServicePolicy locking
before the repair and succeeds with the same exact held phase after it. Its
AdoptionJob/RecoveryPlanJob constructors and SQLite transactions are real; host
stop/outcome and recovery-ledger rows are explicitly modeled. Original before
setup errors, the initial-verification table-root failure and child-at-bound
failure remain separate evidence. These controls add no native execution claim.
