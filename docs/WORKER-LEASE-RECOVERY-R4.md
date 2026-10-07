# Explicit exceptional native lease recovery

`intune_iac.worker_lease_recovery` adds a separate release-only operation. A stopped worker's ordinary approval never authorizes it. This module does not acquire or break leases, clear metadata, write state, mutate Graph, transfer scope ownership, or declare a backend ready for another apply.

## Bounded operating profile

The original real `ServiceJob` must have one dispatch, an `outcome_unknown` or `host_completed_service_unverified` result, no registered controller, the original exact consumed manifest, and all original ownership reservations. Its recorded Docker cleanup must show a stopped/removed container; a new read-only pinned Docker inspection must independently confirm the exact container is absent. Exactly one original native acquire UUID must be recoverable from the bound private broker journal. Any conflicting native lease target or UUID is denied.

A process-held live or laboratory identity binding reauthenticates the original backend tenant/client/principal/subscription/account/state target. A fresh bounded GET supplies the exact original lease UUID and must return the expected locked state, exact state bytes/lineage/serial/ETag, and exact recorded Terraform metadata. Missing or foreign metadata is not silently accepted. Unknown metadata names deny recovery. The `LiveRecoveryContext` always uses fixed native HTTPS transport; laboratory code cannot be promoted by a JSON profile label.

If the original native journal installed lock metadata and has no metadata-clear attempt, a locked recovery read with missing metadata now explicitly fails. A local receiving-fixture counterexample and its repaired result are preserved; this stricter locked-read rule does not block independently observed empty metadata after a later normal plan and unlocked completion.

The current implementation intentionally accepts only the original persisted state revision. A cancellation after a native state write advanced that revision needs a separately reviewed recovery contract; it cannot reuse this release approval. There is no speculative refresh, state rewrite, or lease break fallback.

This boundary has an explicit before/after regression: the retained native cancellation-after-state-write fixture contains authenticated serial 14 while its original manifest declares serial 13. The earlier context admitted that caller-supplied revision; the repaired context rejects its lineage/serial/content binding before a release request. The original fixture, rejected context and source hashes remain in `worker-broker/recovery-original-revision-{before,after}-01`.

## Actual interfaces

- `live_context(job=..., binding=..., backend_credential=..., storage=...)` requires an actual `LiveIdentityBinding` and original `azure_public_pilot` job.
- `laboratory_context(..., upstream=LaboratoryUpstream(...))` is distinct and only admits the native laboratory profile.
- `context.observe(NEW_PRIVATE_DIRECTORY)` performs authenticated reads and the independent host absence check. Its sealed result expires after 30 seconds.
- `prepare(observation, operation_id=NEW_UUID, expires_at=...)` creates exact review material with a lifetime of at most five minutes.
- `RecoveryPolicy(PRIVATE_EXTERNAL_POLICY)` pins verifier/key/profile and explicitly admitted manifest digest. The signature domain is `intune-workbench:native-lease-recovery-approval:v1` followed by NUL. Ordinary execution signatures, booleans and artifact JSON are not recovery authority.
- `execute(manifest, signed, context=..., policy=..., output=NEW_PRIVATE_DIRECTORY)` repeats the independent prewrite observations, consumes the recovery operation and nonce in the **original common service authority**, and persists `dispatch_started` before one empty native `PUT ?comp=lease`, action `release`, exact original UUID and reviewed `If-Match` ETag.
- `observe_uncertain(manifest, context=..., policy=..., output=...)` performs only fresh reads after a lost response. It cannot repeat the PUT or release ownership. An observed unlocked blob is recorded as `release_observed_execution_unknown`; actor attribution remains unknown.
- `completion(...)` creates a nonserializable `LiveRecoveryCompletion` or `LaboratoryRecoveryCompletion`. Its `.verified()` binds the same authority/original outcome/scopes, consumed recovery row, current service policy, authenticated state revision/identity/metadata and private artifact hashes. It is evidence for a separately signed successor transfer, not transfer authorization.

The original common authority serializes recovery even if a caller installs another recovery policy root. A competing approval for the same original operation cannot send a second release. Expiry is checked again after durable consumption immediately before the request. Once the reservation is durable, failures remain spent even if error recording itself fails. Primary cancellation/error is preserved; secondary evidence errors do not authorize replay. Credentials/tokens are not placed in manifests or logs.

A new policy may admit a successor while leaving the original policy file untouched. Read-only completion may then use a newly constructed original `ServiceJob` under that current policy if the authority, original manifest/outcome/journal and scopes remain exact. The historical signed recovery digest is not rewritten.

## Metadata and race limitations

Release-only preserves existing Terraform metadata and reports `backend_ready_for_new_apply: false`. The actual local pinned OpenTofu preparation after release demonstrated that a **normal locked plan** acquires a new UUID, replaces stale metadata, then clears it and releases normally. No exceptional metadata-clear action was necessary. Completion permits independently observed empty metadata after that normal native plan, or the original exact retained metadata; foreign replacement metadata is rejected.

Azure metadata operations also change the ETag. The first local fixture did not model that transition; its original pass remains scoped to that fixture. The preserved `worker-provider/metadata-etag-before-01/receipt.json` reproduces the resulting read-only completion rejection without a write. Completion now retains exact state bytes, semantic hash, lineage, serial and size while recording both the historical release ETag and the freshly authenticated ETag. It explicitly leaves the cause of an ETag change unestablished. The signed successor must bind the fresh value; release execution's original exact prewrite/`If-Match` checks are unchanged.

Host/controller absence and common ownership constrain local competitors. Conditional GET, `If-Match`, and the exact UUID constrain the eventual request, but this is not a global transaction or proof against independently authorized external lease actors. Real Azure handling of a wrong lease UUID on GET, `If-Match` on release, response loss, and intervening state/lease changes requires the declared service qualification. Local TLS fixtures are not that evidence.

## Retained acceptance evidence

All paths below are under `work/evidence/epoch-20261007-r4/` and record exact tested source/artifact hashes. These are overlapping scoped checks, not a new cumulative suite total.

| Evidence | Scope |
| --- | --- |
| `worker-broker/recovery-success-01/receipt.json` | 14 original local TLS release and negative checks; exact original stopped native operation, one UUID release, no scope release |
| `worker-broker/recovery-timeout-01/FAILURE-ANALYSIS.json` | Preserved failing-before raw `TimeoutError` boundary after effect; durable uncertainty already held |
| `worker-broker/recovery-timeout-readonly-01/independent-corrected-receipt.json` | 12 read-only restart assertions; no second release; original harness's unrelated historical-UUID count failure retained |
| `worker-broker/recovery-completion-01/receipt.json` | 11 fresh sealed completion assertions, tamper/serialization negatives and no PUT |
| `worker-broker/recovery-concurrent-04/receipt.json` | 11 two-controller assertions: actual TLS prewrite synchronization, two real signatures, one release, other approval denied, original fixture unchanged |
| `worker-broker/recovery-concurrent-01` through `03` | Preserved harness failures rejected by main-thread supervision, deleted-mapping and exact source-entrypoint guards; no gate weakening |
| `worker-broker/recovery-expiry-recording-01/receipt.json` | 10 actual TLS prewrite assertions: expiry before remote dispatch plus injected failure-artifact write error; primary error/lease/state/ownership preserved |
| `worker-provider/partial-recovery-release-01` | Independently executed signed release on a new copy of partial-failure receiving fixture; original fixture unchanged |
| `worker-provider/partial-recovery-prepare-01/receipt.json` | 10 actual native locked-plan checks; stale metadata replaced normally, exact persisted state/Graph unchanged, new explicit drift plan |
| `worker-broker/lease-recovery-focused-01/receipt.json` | 11 focused real-signature and hostile response/context checks |
| `worker-provider/partial-recovery-prepare-metadata-01/METADATA-ETAG-RECEIPT.json` | Actual pinned native metadata set/clear advances fixture ETag while preserving exact state bytes |
| `worker-provider/metadata-etag-before-01` and `metadata-etag-after-01` | Preserved completion defect and repaired read-only old/current ETag binding; no release |
| `worker-broker/recovery-original-revision-before-01` and `recovery-original-revision-after-01` | Six assertions each around original serial 13 versus authenticated post-write serial 14; before finding preserved, after denies with no PUT |
| `worker-broker/recovery-missing-metadata-before-01` and `recovery-missing-metadata-after-01` | Six assertions each around unexpected removal of installed native lock metadata; before finding preserved, after denies with no PUT |

Focused replay:

```sh
INTUNE_TEST_VALIDATOR_LIBRARY=/workspace/intune-continuation/work/evidence/epoch-20261005/approval-prerequisite/libsodium.so.23.3.0 \
  python3 -B -m unittest plugin_tests.test_worker_lease_recovery_r4 -v
```

The retained `recovery-staging/qualify_*.py` harnesses contain exact local replay commands and source copies. They deliberately require a new receiving fixture and a still-unspent original operation; **do not rerun a mutating harness against an already-consumed authority**. Read-only completion can be repeated with a new private output directory. Real timeout after-effect and concurrent probes use the actual TLS/native receiving fixture; focused signature tests alone make no transport claim.

## External execution procedure and release blockers

Before any real release, an accountable operator must explicitly authorize this particular exceptional operation, verify the declared original host is stopped, and independently establish the current backend identity/lease/state/metadata using the closed context. Prepare the exact manifest and recovery procedure, obtain a new independent recovery-domain signature, and install only that digest in an external host policy. Verify actual Azure conditional-read/release semantics in an authorized nonproduction profile first. Execute once and preserve independent readback, errors, state/metadata and the still-held original ownership. A lost response moves to read-only investigation, never another release.

The complete declared live identity, service, protected host, organization storage, CI and organizational approval gates remain separate. No real Azure release was performed or authorized by these laboratory results. Organizational production approval is not established by the source review or passing tests.
