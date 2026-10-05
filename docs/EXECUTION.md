# Plan review and local execution recovery

The plugin now reads actual OpenTofu `show -json` plans and implements a durable two-step operation protocol against a disposable local fixture. It does not execute Terraform, Atmos, a provider, Azure or Graph. No external adapter is shipped, and no field in a JSON document can authorize one.

## Read-only plan review

`intune_iac.execution.review_plan(document: dict) -> dict` returns `no_change`, `changes_require_review` or `blocked`, plus safe action counts, hashed resource/output/import references, blocker codes and the canonical JSON digest. Every result includes `execution_authorized: false`.

The current inspection baseline is engine version `1.10.0` and JSON format versions `1.0`, `1.1` and `1.2`. Only format `1.2` has actual native corpus evidence here. Unknown engine versions, future format versions and unknown effect fields block review. This deliberately stricter local restriction is not a claim that upstream minor formats are incompatible.

The reviewer accounts for resource changes, drift, outputs, imports, moves, deposed objects, sensitive/unknown masks, deferred/incomplete/errored plans, checks, and declared provisioners. It compares both prior and planned resource/output denominators and known before/after values to the change entries. Prior-state versions and shape are checked; omitting an existing object from both after-side collections still blocks. No-op equality is canonical JSON equality, so `true` and `1` differ. Replacement, destruction, forgetting state, drift, sensitive values, computed unknown values, failed/unknown checks, and unresolved import identity block this conservative slice. A supported update is only a change requiring review.

`no_change` means the supplied supported plan representation contains consistent no-op effects. It does not prove the plan is authentic, fresh, untargeted, refreshed, complete against a real estate, or linked to the actual saved binary plan. JSON omits some runtime context and cannot establish those properties. A future native adapter must acquire the plan itself, bind binary and JSON digests to the same invocation, enforce options, verify the engine/provider/configuration and authenticated target, and check freshness before effects.

Neither raw values nor user-controlled resource addresses, output names or exception messages are emitted by the reviewer. Hashes remain correlation data and should be protected accordingly. The original plan may contain sensitive data and remains the caller's responsibility to retain securely.

## Fixed local operation API

```python
from intune_iac.execution import (
    create_local_fixture, prepare_operation, execute_operation, read_operation,
)
from intune_iac.reconciliation import reconcile_operation

adapter = create_local_fixture(
    "/absolute/new-fixture",
    policy={"id": "same-policy", "setting": "before"},
    assignments=[{"group": "include"}, {"group": "exclude"}],
    desired_policy={"id": "same-policy", "setting": "after"},
    desired_assignments=[{"group": "include"}, {"group": "exclude", "filter": "new"}],
)
request = prepare_operation(adapter)  # Safe hashes; does not execute.
result = execute_operation(request, "/absolute/receipts", adapter=adapter)
observation = reconcile_operation(request["operation_id"], "/absolute/receipts", adapter=adapter)
```

Exact additional signatures:

- `create_local_fixture(root, *, policy, assignments, desired_policy, desired_assignments) -> LocalFixtureAdapter`
- `LocalFixtureAdapter(root)` opens an existing fixture.
- `prepare_operation(adapter, operation_id=None) -> dict`
- `execute_operation(request, state_dir, *, adapter=None) -> dict`
- `read_operation(operation_id, state_dir) -> dict`
- `reconcile_operation(operation_id, state_dir, *, adapter=None) -> dict`

The only accepted adapter is the concrete shipped `LocalFixtureAdapter`, which writes fixed JSON files in a newly created private directory. It does not accept commands, executable paths, subprocess arguments or adapters named in JSON. Its request binds the fixture plan/configuration bytes, the two implementation-module hashes, the fixture's identity and absolute path, and before/desired facet hashes. The fixture plan is a local JSON protocol fixture, not a Terraform saved binary plan. These two plan formats are intentionally not interchangeable.

The two facets are `policy`, then `assignments`; no atomicity is claimed. The fixture requires policy identity to stay unchanged. Its generic assignment arrays demonstrate preservation/recovery mechanics; they do not validate Intune assignment semantics. Fixture and journal directories cannot overlap. Initial directories must be new, values are restricted to 1 MiB, and persisted files are mode `0600` under mode `0700` directories on POSIX.

Before each step the coordinator compares bindings and independently rereads both facets. It durably records `step_started` before dispatch, writes only a snapshot whose hash matches the requested desired facet, independently rereads both files, and then records `step_verified`. Changing the plan after `step_started` cannot substitute different values. A successful result requires both independently observed desired facets and a persisted final receipt.

An atomic target-local directory lock prevents concurrent operations even if callers choose different receipt directories. A lock, owner record, journal directory, or receipt write failure after lock acquisition retains the lock. Abrupt interruption also retains it. Successful completion removes it only after the final receipt is persisted and the lock owner is rechecked. A substituted owner is never removed by the older operation.

## Receipts and reconciliation

The append-only event prefix is closed:

`prepared → policy started → policy verified → assignments started → assignments verified → completed`

Each event is created exclusively, fsynced with its parent directory, and linked to its predecessor's file hash. Reading a journal checks bounds, contiguous numeric filenames, exact event schemas, strict integer sequence numbers, request binding, facet order and observed hash boundaries. Extra raw payloads, impossible transitions, truncation within a record and mismatching hashes are rejected. A valid prefix can still represent interrupted work.

This is local consistency and durability engineering, not authenticated or tamper-proof audit storage. Someone who controls the files can replace an entire consistent history. These routines do not protect against an adversarial local writer racing path operations, physical disk failure or all network-filesystem semantics. They use a cooperative private POSIX filesystem, not a distributed lock. Power-loss behavior has not been tested on deployment filesystems.

`reconcile_operation` rereads artifacts and current state through the fixed adapter. It can report `desired_state_observed`, `matches_precondition`, `partial_effects_observed`, `diverged` or `unknown`. A matching precondition cannot establish that no earlier effect occurred; a desired value cannot establish who caused it. No reconciliation classification authorizes replay or releases the lock. Missing/corrupt evidence, changed bindings or unreadable readback stay unknown. Recovering retained locks is intentionally a manual engineering task while the external adapter is unavailable.

## Remaining enterprise execution boundary

The implementation is useful for inspecting real plan JSON and qualifying the durable orchestration algorithm. It is not a protected production executor. Still required: a qualified native adapter with binary-plan provenance; authenticated cloud/principal and effective backend observation; protected approval delivery and consumption; deployment-native state locking plus distributed operation control; credential isolation; live provider/service readback; restart/power-loss qualification; Windows qualification; and separately authorized pilot evidence. The LLM judge cannot supply any of these controls.

Verification and pinned source decisions are in `research/enterprise-execution/IMPLEMENTATION-REPORT.md`.
