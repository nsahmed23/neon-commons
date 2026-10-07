# Read-only recovery attestation for an already unlocked partial outcome

This is design material for the next dependency after the current stranded-lease native journey. The independently reviewed implementation and signature-v2 migration are integrated. This route grants no dispatch authority; a new ordinary exact-plan approval remains mandatory. The existing exact-lease release/completion contract must remain intact.

## Concrete uncovered trigger

An actual native apply can partially change Graph or state, report failure, and still release its native backend lease during normal cleanup. Desired-state reconciliation must retain ownership because the full earlier intent is not established. The existing recovery command correctly requires an existing exact locked lease; manufacturing a release for this already unlocked object would invent evidence or cause an unnecessary mutation. A fresh new native plan needs a separately reviewed path to acknowledge this partial state and succeed the failed operation.

## New read-only evidence capability

Add distinct `LivePartialRecoveryAttestation` and `LaboratoryPartialRecoveryAttestation` types in a new module. Their factory requires the original registered consumed service job, process-held matching backend/reader identities, approved storage capability, and new private evidence location. No JSON factory, arbitrary URL, supplied access token, mutation callback or operation retry is accepted.

Verify the original controller is stopped and the recorded container is actually absent. Verify immutable old manifest/outcome/consumption and all scopes still belong to it in the original common authority database. Preserve original policy files. A current additive policy may admit new exact work under the same authority/jobs roots; report historical mismatch rather than relabeling earlier approval.

Independently read the exact physical state blob and complete selected policy/settings/assignments through the separate authenticated reader. Require unlocked/available lease headers, bounded complete state bytes, valid native state revision, and no unknown/foreign lock metadata. Bind raw state hash, lineage, serial, current ETag, metadata, capture raw/hash/reader identity and original exact failure/scopes. If native planning later changes an ETag, mint a new observation and record that difference without claiming its cause. No metadata clear, lease PUT, Graph mutation, native plan or apply is performed by this factory.

Record the sealed observation's digest and artifact identities in a new append-only table within the *same* service authority database. Label it `already_unlocked_original_state_observed`, not `lease_released`, `converged` or `ready_for_apply`. Preserve each observation, including failures. The capability is nonserializable, bound to this process and a short freshness window; verification rechecks raw artifacts, matching database record, identity freshness, original stopped ownership and exact current state/service facts. It conveys evidence, not permission to transfer a reservation.

## Explicit successor admission

Introduce an explicit versioned transfer variant that admits this new typed attestation, requiring a distinct `recovery_kind=already_unlocked_original_state_observed` discriminator in the signed review document. The existing stranded-lease variant keeps its current exact completion type, signed release linkage and database checks. Never reinterpret an imported release receipt or widen the old completion factory.

The operator reviews the newly observed partial state, new native saved plan and complete successor manifest. The successor's exact backend state preimage and sealed Graph preimage must equal the attestation; selected object and physical state scopes, authority, tenant and profile must be identical. A new independent transfer signature binds all of that evidence. Use the existing atomic transfer/history/cancel-return machinery after the appropriate fixed attestation-record check; no second authority, reservation deletion or alternate native execution engine is introduced. The new operation still requires a separate ordinary exact-plan apply approval.

Cancellation of a prepared successor returns ownership to the original failed job while preserving every signed transfer and observation. A dispatched successor keeps ownership for independent reconciliation. Successful observed desired state remains a separate existing reconciliation path, and device effectiveness remains unestablished.

## Executable acceptance before promotion

Start from a new real native failure fixture that actually released its lease. Retain the failed host/provider result, partial Graph and native state bytes, lease-release request and independently observed unlocked headers. Exercise the attestation API and actual status/attach history, then a new same-authority signed successor, exact saved-plan native execution, independent Graph/backend readback and second no-change plan. Assert that the attestation itself emitted only authenticated reads and made zero lease, metadata or Graph writes.

Required negative oracles: still locked/foreign lease, active controller, existing container, wrong backend or reader principal, partial/denied/paginated Graph coverage, changed state bytes with same ETag, replaced metadata, wrong object/tenant, stale/tampered/serialized capability, mismatched new plan preimage, wrong signature/domain/nonce and concurrent scope contenders. Inspect raw requests and SQLite independently. Preserve original failures and disclose source/artifact identities. Passing this laboratory route establishes neither live platform qualification nor organizational approval.

## Implemented staged API and qualification

The implemented attestation intentionally supports only the original persisted backend revision: exact original state bytes/hash, lineage and serial. It does not admit advanced state14 or a generic new baseline. Those use the separately reviewed committed-state recovery route.

```python
proof = worker_partial_recovery.attest(
    context=exact_original_state_recovery_context, reader=exact_graph_reader,
    service_preimage=sealed_fresh_capture, observation_id=new_uuid, output=new_directory)
transfer = worker_successor.prepare_transfer(
    original_job=original, successor_manifest=new_reviewed_manifest,
    successor_job_root=new_job_directory, recovery_completion=proof,
    service_preimage=sealed_fresh_capture, transfer_id=new_uuid, expires_at=expiry)
worker_successor.execute_transfer(transfer, separately_signed_v2_approval,
    original_job=original, successor_manifest=new_reviewed_manifest,
    recovery_completion=proof, service_preimage=sealed_fresh_capture)
```

The proposed transfer schema is `worker-service-successor-transfer/2`, with signature payload `signed-worker-service-successor/2` and domain `intune-workbench:worker-service-successor-transfer:v2\0`. The signed discriminator is derived exclusively from the exact process-held capability type. `explicit_original_state_lease_release` retains all existing release completion/database checks; `already_unlocked_original_state_observed` checks the new read-only observation record in the same authority. Old v1 signatures are never reinterpreted under the v2 domain; cancellation of historical transferred jobs remains version-independent and preserves consumed nonces.

`already-unlocked-qualified-01` passed 18 checks over an explicitly constructed absent-lease copy, actual bounded TLS reads and Docker absence inspection. `already-unlocked-successor-02` passed 22 checks including nine overlapping negative controls, genuine typed observation, actual signature verification, atomic SQLite transfer, actual CLI cancellation and API recovery. Ownership returned to the original stopped failure, both transfer nonces remained consumed, a reused nonce failed, and a separately signed new nonce admitted only a prepared successor. Zero apply dispatch or remote mutations occurred. Six separate signature/SQL/cancel regression tests use explicitly modeled terminal records; they are not native lifecycle evidence and must not be added to overlapping journey counts.

The first transfer attempt rejected `recovery_state_refresh_not_observed`: a historical plan's refreshed provider timestamp did not match the copied Graph response. The failure and exact source are preserved unchanged. A new actual pinned native read-only plan was prepared over a fresh copy of that explicitly constructed fixture (`worker-provider/already-unlocked-plan-01`), with zero Graph/state writes and ordinary plan lock/metadata cleanup. The passing transfer uses that plan and exact exported state/Graph. This qualifies the staged transfer API but still does not establish an actual failure trigger that naturally released its lease. Actual Windows/live-service/organizational approval remains absent.

Replay in a NEW output location using the retained runtime and validator:

```sh
/workspace/intune-runtime/bin/python -B \
  /workspace/intune-continuation/work/evidence/epoch-20261007-r4/worker-service/already-unlocked-staging/qualify_successor.py \
  /workspace/intune-continuation/work/evidence/epoch-20261007-r4/worker-service/already-unlocked-successor-NEW
/workspace/intune-runtime/bin/python -B \
  /workspace/intune-continuation/work/evidence/epoch-20261007-r4/worker-service/already-unlocked-staging/run_successor_regressions.py \
  /workspace/intune-continuation/work/evidence/epoch-20261007-r4/worker-service/already-unlocked-regression-NEW
```

## Reviewed error-preservation repair and migration

The original staged `274565...` attestation could mask a primary read/durability failure when writing failure.json also failed. The unchanged actual API fault evaluator retained failing-before and passing-after receipts at `already-unlocked-recording-before` and `already-unlocked-recording-after` (10 scoped assertions). The repaired module `9155617702576f24923b110563c936d17e6064cb6f3c18bec47293b9a851f140` rethrows the exact primary, records the secondary code/note, and reports whether a read-only registry row committed. The committed row, original scope ownership, consumed approval and all raw artifacts remain retained after a postcommit error. No serialized receipt becomes a live capability.

The independently reviewed v2 module is `f31aa60b5d19a31d7dc548198e17eaaeac9dd021d5d2ca4d7f554bcba70879a6`. An unexecuted historical v1 transfer requires a new fresh sealed observation and newly reviewed v2 transfer/signature; there is no automatic signature upgrade. Historical signed artifacts and consumed transfer rows remain unchanged, and cancellation/recovery of a historically prepared undispatched successor retains the version-independent ownership-return behavior. Ordinary worker-service apply approval remains `signed-worker-service-approval/1`; only the exceptional ownership-transfer domain changes.

Independent raw review `independent/unlocked-successor-01/RESULT.json` passed 11 assertions over actual v2/v1 signature verification, common authority SQL, retained original ownership/failure/consumption, typed attestation artifact/state, and actual CLI cancellation. Those assertions overlap the producer checks and are not a new aggregate count.
