# Interrupted state-only adoption recovery

This is a separate recovery profile for the original `native-state-adoption/1` operation. It does not reuse an import approval, enable ordinary Apply's `OperationTypeInvalid` metadata, or recreate an authenticated reader from saved JSON.

`worker_adoption_projection.py` checks the complete closed original state-contract schema, exact empty baseline bytes and revision, original capture directory with its document/raw-page digests, raw preimage, complete collection coverage, original reader identity, and entire derived successor state. Historical capture parsing remains `graph_capture_unverified`. A newly authenticated exact reader supplies a fresh complete policy/settings/assignments capture. Its original process identity, class, credential observation and PID remain checked. Mapping blockers stay visible.

`worker_adoption_recovery.py` adds these receiving-service and authority requirements:

- Exact registered `AdoptionJob`, separate original approval already consumed, one original import dispatch, complete original scopes in the same physical service authority, no live recorded controller, and matching original host manifest/receipt/outcome plus actual Docker inspection proving that exact container absent.
- Read-only original broker journal inspection with `mode=ro&immutable=1`, `trusted_schema=OFF`, `query_only`, a coherent transaction, no sidecars/hot-journal recovery, bounded rows, no views/orphans, original policy digest, and byte hash before/after. Import metadata must be `OperationTypeInvalid`; the inspector grants no dispatch authority.
- Actual identity-bound Blob GET on the original fixed tenant/backend principal/container/key, using the original exact lease GUID when locked. Original source tree, generated configuration, effective inputs and lockfile must still match signed bindings. Supplied state bytes alone cannot establish this observation.
- `original_baseline` means byte-identical original empty state. `approved_adoption_successor` means the entire rederived native state, original lineage and serial+1, exactly one original state-write attempt and that attempt's exact receiving request-body hash. Other supported state documents classify `unexpected_state`; malformed/oversized state and incomplete/denied Graph evidence fail closed.
- Release preparation requires one of the first two classifications and unchanged fresh Graph. Actor attribution remains unestablished in both cases.

## Exact API and approval boundary

`laboratory_context(...)` accepts `job`, `binding`, `backend_credential`, `storage`, `reader`, `baseline_raw`, `original_capture_root`, `source_root`, and exact laboratory `upstream`. `live_context(...)` has the same arguments without an upstream override and uses the fixed native Azure transport. These produce distinct process-held context types.

`context.observe(new_private_output, require_locked=True)` returns a sealed observation. `prepare(observation, operation_id=NEW_UUID, expires_at=...)` creates the concrete operation for independent review. It cannot mint mutation authority. A separate external `AdoptionRecoveryPolicy` admits the exact manifest and signer. Signature domain is `b'intune-workbench:adoption-native-lease-recovery-approval:v1\x00'`, with an actual NUL byte. Original import, ordinary worker and other recovery signatures are rejected.

`execute(manifest, signed, context=..., policy=..., output=NEW_PRIVATE_DIR)` snapshots the verified receipt once, reacquires fresh independent evidence, durably consumes the recovery before dispatch, and makes at most one exact `PUT ?comp=lease` with action `release`, original lease GUID and reviewed `If-Match`. Original-operation uniqueness is enforced through the common `native_lease_recoveries` table; recovery operation/issuer/nonce are also inserted into the shared `consumed` table. Existing job and adoption verification IDs cannot be reused. No lease acquire, break, metadata clear, state write, Graph write or automatic import retry exists here.

Timeout, cancellation, recording failure or uncertain response leave the approval spent and ownership retained. `observe_uncertain(...)` is read-only and cannot retry the release. `completion(...)` mints distinct Live/Laboratory completion types after independently observing the exact state unlocked. `captured_observation()` returns the fresh typed Graph capture; JSON facts alone are insufficient. Completion may bind a changed ETag after a separately authorized normal native plan, but requires exact state content and original or empty metadata. ETag-change cause is unestablished.

The release-only receipt reports `backend_ready_for_new_apply=false` even when release is observed. Metadata and all original unknown outcomes remain preserved. Baseline completion cannot prove adoption. Successor completion still needs a separately reviewed fresh no-change plan, typed service readback/reconciliation and ownership disposition. The recovery verification phase must preserve the original job status, outcome and dispatch count.

## Qualification and remaining gates

`qualified-recovery-contract-01/command.json` is the exact replay command and environment. Its 27 cases comprise nine historical/fresh-reader projection checks, fourteen real Ed25519 signature/cleanup contracts and four actual registered-job SQLite controls. Recorded journal rows are modeled inputs, not evidence of native dispatch. Counts do not include imported historical TestCases or add earlier overlapping runs.

The initial source review findings and their limits are recorded in `RECOVERY-SOURCE-FINDINGS-01.md`. Actual native interruption after acquisition and after possible state commit, complete prepare/sign/release/readback flows, compound failure recording, replay/concurrency controls and service reconciliation are still pending the new isolated native fixtures. These helper tests do not close those gates.

Real Azure conditional lease-ID/If-Match semantics, authenticated tenant permissions, provider/service/device behavior, external CI attestation, secret-store/runtime protection, AppSec and accountable organizational approval remain separate external requirements. A trusted owner capable of changing the process or private authority can defeat the local boundary; hashes and read-only SQLite are not protection against host compromise. No production release or tenant action is authorized by this implementation or its laboratory policy.
