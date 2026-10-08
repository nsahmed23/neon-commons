# A new Plan after an observed absence of backend dispatch

This is the separate `/3` continuation of the existing protected adoption Plan
worker. It does not rerun a consumed Plan or invent a lease-release operation.
The original adoption and every stopped Plan retain their exact outcomes,
consumed approvals, manifests, host evidence and common-authority ownership.

The trigger was the retained C18 Plan2 `49e7940c-e541-4560-be0a-ded79575566a`:
its native host stopped after the watchdog reported `service_store_unavailable`.
The broker recorded provider discovery but no backend request or lease. C19
repaired the internal historical opener's unintended schema writes. That repair
does not make Plan2 successful or reusable.

The separately typed `LiveUnacquiredPlanObservation` or
`LaboratoryUnacquiredPlanObservation` must establish the exact stopped phase,
zero backend-role attempts, zero native lease records, unchanged ownership and
consumption, independently authenticated current state, and fresh Graph parity.
The state must be the exact approved adoption successor, unlocked, with empty
lock metadata. An absent lease alone is insufficient. The durable observation
anchor is read-only evidence, not permission to execute or release ownership.

Use the existing module-level `worker_adoption_reconcile.make_manifest(...)`
with that process-held observation
as `completion`. The selected manifest becomes
`native-adoption-recovery-plan/3`. Its signed approval is
`signed-native-adoption-recovery-plan-approval/3`, using the actual NUL-terminated
domain `intune-workbench:native-adoption-recovery-plan-approval:v3\0`.
The existing external signer policy, fixed provider controls, protected host,
broker and dispatcher remain in use. `/1` and `/2` signatures keep their original
meaning and cannot approve `/3`.

The closed `/3` `recovery_binding` contains `resolution_kind` equal to
`unacquired_phase_observation`, `observation_id`, `anchor_sha256`, `phase`,
`ancestors`, `state`, `projection_sha256` and `original_contract_sha256`.
It contains no release operation or lease ID. The same physical authority uses
the additive `adoption_plan_observation_successors` table, whose columns are:

```
successor_operation_id, original_operation_id, successor_manifest_sha256,
prior_operation_id, prior_manifest_sha256, observation_id, anchor_sha256,
prior_phase_json
```

Both this table and the existing release-successor table are checked together.
Duplicate children or parents across them are rejected. The new observation edge
is committed atomically with the separately consumed approval, immutable approval
transcript and dispatch registration before the existing host dispatcher runs.
An insertion failure rolls them all back. Preparing or cancelling an
undispatched Plan creates no consumed edge and never releases original scopes.

Mixed ancestry retains every `/2` release entry's exact shape. A `/3` entry has
the explicit observation kind, child/prior identities and hashes,
`observation_id`, `anchor_sha256`, `prior_phase_sha256` and the exact six-field
`observation_row`. Anchor checks bind both its parsed content and exact file
bytes. The existing 32-edge bound, consumed-child requirement, immutable prior
row hashes and same-transaction ownership checks apply across both edge kinds.

The existing CLI and complete terminal interface provide prepare, review, status,
attach, cancel and stop/recover routes. They do not mint a runtime or import
permission. Only a trusted controller may call `job.run(...)` with the exact
runtime, new signature and sealed observation. For final reconciliation, obtain
fresh identity and call `worker_adoption_plan_observation.refresh(observation_id,
context=..., output=NEW_PATH)`. This preserves the anchor while independently
reading the post-Plan ETag, state and Graph. The exact native no-op artifacts and
fresh proof are checked before only the original scopes are released. The final
classification remains `adopted_verified_execution_unknown`; old execution
attribution stays unknown.

The staged local gate has 48 methods: 34 prior overlapping checks and 14 new
signature, modeled SQL/anchor/ancestry and completion-interface methods. Those
tests do not establish a native `/3` journey or live Azure/Graph evidence. A separate genuine sealed observation-to-full-manifest preflight passed 10
controls at `/tmp/intune-adoption-unacquired-manifest-01/receipt.json`, using a
new copied receiving fixture and stopping before admission/signing/dispatch.
The native Plan3 journey remains unqualified. Native Windows, service-provider/device routes, host
ciphertext/retention custody, AppSec review and accountable organizational pilot
approval remain their own gates. No production permission follows from this
document or a passing local suite.

Replay the focused product scope after integration:

```sh
python -B -m unittest plugin_tests.test_worker_adoption_reconcile_r4 \
  plugin_tests.test_worker_adoption_phase_successor_r4 \
  plugin_tests.test_worker_adoption_unacquired_successor_r4
```

Preserve the before findings: the first staged `/3` producer name was shadowed
by a dictionary; the anchor reader initially admitted reformatted equivalent
JSON bytes; old modeled phase-test manifests omitted schema/operation fields;
and the first atomic fixture accidentally retained its model's cancelled flag.
Their individual receipts distinguish product defects from fixture errors.
