# Protected service controller (R4)

`intune_iac.worker_service` composes the existing pinned native worker host and HTTPS-over-Unix broker. It does not replace Atmos, OpenTofu or the provider. Prepared files are review material. Live identity, trusted controller run checks, storage protection and fresh Graph preconditions are process-held capabilities; serialized claims cannot construct them.

## Review and execution interfaces

The application exposes `service prepare --manifest FILE --job-root NEW_JOB --policy HOST_POLICY`, plus `service review`, `status`, `attach`, `cancel` and `recover` with `--job-root` and `--policy`. The text terminal retains equivalent `service-review/status/attach/cancel/recover JOB_ROOT POLICY_PATH` commands and checks the active tenant/selected object before consequential actions. No terminal or JSON command creates a live execution runtime. Reopening a terminal never dispatches or retries a plan.

Trusted controller APIs are `make_manifest(...)`, `prepare_job(...)`, `ServiceJob(...).run(signed_receipt, runtime=...)` and explicit process-held `laboratory_runtime(...)`/`live_runtime(...)`. The runtime supplies the admitted upstream, host-private TLS key and certificate, identity-bound placeholder credential vault, fresh preconditions and exact state-write contracts. Native service profiles use the same host/container boundary and engine adapter.

The service operation manifest includes complete source/control/tool bindings, exact saved binary plan digest, provider and Azure backend identity/target bindings, scope ownership, complete broker policy, state contracts, fresh precondition binding, reviewed implementation files and mandatory run/storage capability bindings. `execution_binding_sha256` is a stable operation core used for opaque credential placeholders and broker association. The independently signed manifest binds that core plus the complete resulting policy and payload hashes, avoiding a self-referential hash. It is not claimed that the core digest alone covers the whole signed manifest.

The native run context is closed and reviewable: repository URL, source content/revision, workflow and verifier revisions, run ID and attempt, protected ref, effective inputs, provider lock, and the generated `worker` / `intune-policy` Atmos selectors. Source, input and lock identities must agree with the provider adapter. The operator policy admits the complete manifest digest, including these facts. This local contract does not authenticate a GitHub or Azure DevOps run.

The runtime inventory binds every package Python file, standard-library Python/native extensions, actual interpreter bytes, loaded external Python code, and resolved native mappings. Unknown deleted native mappings fail closed. Only exact deleted private validator copies registered by the pinned authority verifier are excluded; their bytes are separately checked against the mandatory libsodium pin. Static OpenSSL in the qualified interpreter is covered by its executable hash. Preparation accepts a reviewed declared inventory under exact operator admission; execution compares the actual controller inventory. A separate terminal's `status` comparison concerns that observer process and does not re-attest the approved controller. New lazy imports can invalidate execution and require renewed review; this inventory does not replace a reviewed host image or remote CI attestation.

Approvals use the distinct domain `intune-workbench:worker-service-approval:v1` followed by a zero byte and canonical signed payload. The schema is `signed-worker-service-approval/1`; the payload binds operation ID, exact manifest SHA-256, issuer/key/approver, issuance/expiry and nonce. The existing pinned OpenSSL verifier and pinned libsodium public-key validation are reused. Old network-denied laboratory signatures cannot authorize this domain. An independently installed private host policy admits exact manifest hashes and signer/profile bindings; its replay store is outside repository and worker mounts.

## Consumption, scope and recovery

The external SQLite store commits approval consumption and dispatch count before the broker/container starts. A unique operation and issuer/nonce cannot be consumed twice. Scope reservations are derived from tenant plus immutable object identity, covering policy and assignments across stacks, and a separate backend scope. Concurrent collectors or terminals cannot supply execution authority.

A sealed permit rechecks exact operation linkage, expiry, current host policy, cancellation, consumed identity, ownership and process-held runtime checks before broker requests. The controller watchdog also observes cancellation while the native container is idle and stops it through the host's bounded cleanup. Primary outcome and cleanup remain distinct. SIGKILL recovery only stops/removes the recorded labeled container and marks an interrupted dispatch uncertain. It never repeats an operation.

Cancellation before any dispatch releases that operation's scope reservations. A dispatched or uncertain operation retains its reservation until independent reconciliation. Reads and safe cancellation/recovery survive implementation upgrades; starting work still requires exact reviewed bytes. Recovery first durably requests cancellation, then refuses competing host cleanup while the recorded controller PID, boot identity and start time still identify an active owner. That controller's watchdog owns cleanup. A failure to archive the final local receipt preserves the already committed external outcome and records an archive failure without authorizing retry.

Native OpenTofu must acquire its own state-blob lease. Holding a separate `LiveBlobLease` on that same blob before native execution would conflict with OpenTofu. The broker observes the native lease and exact Apply lock metadata and requires them before Graph/state writes. External per-object SQLite ownership qualifies only one protected service host. It is not cross-host Azure fencing. Separate coordination-blob ownership and distributed-host qualification remain explicit gates.

`worker_service_readback.collect_live(...)` and its distinct laboratory factory perform a fresh independent read of the exact bound state blob. They require a sealed fresh Graph completion proving approved policy/settings/assignments, the exact reviewed state contract, matching backend identity/target, a fully read response, an unlocked blob and absent Terraform lock metadata. The raw response remains evidence even on a negative result. `ServiceJob.reconcile(sealed_readback)` releases reservations only after these checks and confirmed host cleanup. It never writes or replays the plan. An interrupted execution remains explicitly `service_state_converged_execution_unknown` even if independent readback establishes the intended state; endpoint effectiveness and a second native no-change plan are separate evidence.

For a restart after a known successful host execution whose final receipt could
not be archived, `worker_completed_readback.collect(job_root=...,
policy_path=..., observation=..., output=...)` consumes a fresh sealed
`worker_committed_recovery.RecoveryObservation` collected with
`require_locked=False`. It requires the original approved state, independently
captured complete Graph evidence, an unlocked backend without lock metadata,
the stopped and removed successful host, one consumed dispatch and the retained
scope reservations. The original execution identity and the current observer
implementation digest remain separate; the factory rechecks current observer
code before accepting the capability. It does not require or fabricate an
exceptional lease release after a normal release already occurred.

Retain `capture = readback.captured_observation()` before calling the actual
reopened `ServiceJob(...).reconcile(readback)`. The capture can then be published
to the existing Workbench store and history. Reconciliation checks the original
known outcome again inside the authority transaction and releases reservations
only after valid independent readback. It preserves `host_completed` provenance,
the original committed outcome and existing failure evidence; it does not reapply, create a new
plan, establish endpoint effectiveness or replace the separate native second
plan gate. The local controlled-host tests qualify the factory and real SQLite
transition; native restart/backend/provider/CI qualification remains separate.

The service preserves native lease recovery facts privately before forwarding consequential requests. Stopping a container does not prove an infinite Azure lease was released. Lease recovery requires a separately authorized exact recovery procedure; this controller does not automatically unlock it.

## Explicit successor after a partial failure

A stopped partial outcome retains its object/state reservations. After separately signed exact lease recovery and fresh native planning, `worker_successor.prepare_transfer(original_job=..., successor_manifest=..., successor_job_root=..., recovery_completion=..., service_preimage=..., transfer_id=..., expires_at=...)` prepares a distinct review document. The exact sealed live or laboratory recovery completion must prove a fresh unlocked backend observation; the sealed fresh Graph capture must match the new manifest's reviewed preimage. New state lineage/serial/raw bytes, backend identity/target, tenant/object scopes, authority and profile must match. Newly observed ETag/metadata facts remain visible and bound in the signed transfer, without claiming an unknown ETag-change cause.

`execute_transfer(transfer, signed, original_job=..., successor_manifest=..., recovery_completion=..., service_preimage=...)` verifies the separate `intune-workbench:worker-service-successor-transfer:v1` signature domain, consumes the transfer nonce and atomically registers the new prepared job and moves its exact scope rows in the same external database. It preserves the original failure, outcome, consumed apply and history. It cannot dispatch or approve the new saved plan; that job still needs its own ordinary exact-plan signature, process-held runtime and fresh execution preconditions. There is no JSON/terminal command that performs a transfer or creates its capabilities.

The new exact plan need not have been known before the failure. A new private operator policy can admit the old and new exact manifests under the same authority and jobs roots. Original policy bytes and `policy-binding.json` remain unchanged; reopening with the current policy visibly reports the historical mismatch. Read-only history permits that evolution, while actual execution still requires the current exact reviewed admission. Fresh recovery completion links the earlier signed recovery record without relabeling it.

Cancelling or recovering an undispatched successor atomically returns its reservations to the original failed operation. It does not erase outstanding partial-failure obligations. The transfer stays recorded as `returned_without_dispatch`, retaining its consumed nonce, signature and both histories. Another successor requires another new signature/nonce. Once the successor has dispatched, cancellation keeps its reservations for independently established reconciliation or another explicit recovery. Both `service status` and `attach` expose linked original/successor/recovery IDs and the private transfer/approval artifact paths through durable events; the UI creates no authority.

The staged focused scope preserves six passing signature/SQLite/cancel assertions over explicitly modeled stopped/consumed records and eight readback regressions at `worker-service/successor-qualified-01`. Actual sealed transfer and native recovered-plan execution have separate native journey evidence. Those scopes must not be confused or added together.

## Profiles and evidence

`native_docker_laboratory_tls` uses an actual pinned native Docker worker, fixed static relay, Unix CONNECT, verified synthetic TLS and a literal acceptance client. `native_docker_laboratory_protocol` preserves actual SDK public hostnames but still permits only the distinct laboratory upstream and laboratory identities. Neither profile establishes real Azure/Graph authorization or device effectiveness. `azure_public_pilot` requires native identity, credential, reader/precondition and upstream capability types; it cannot be enabled by changing a JSON label.

`worker-service/development-03/RECEIPT.json` preserves the first 11 passing service assertions against their exact source hashes. The connected case used actual Ed25519 signing and verification, actual Docker isolation, relay v3, verified synthetic TLS, a literal OAuth exchange, exact PUT body and separate GET readback. The final service status deliberately remained `host_completed_service_unverified`: that fixture is not the Microsoft 365 provider. Negative assertions covered forged authority/runtime JSON, signer/expiry/domain mismatch, changed payload/policy, cancellation, missing host protection, changed preconditions and overlapping object ownership. Historical component evidence and later native provider composition have their own scopes; overlapping tests must not be summed.

The first test harness omitted static OpenSSL compression libraries and accidentally discovered 27 imported broker tests; it did not run the new service tests. The next harness used the host's different default libsodium and correctly failed the unchanged validator pin. Replay uses the already retained exact validator through `INTUNE_TEST_VALIDATOR_LIBRARY`; no security gate was relaxed. Later entrypoint qualification initially invoked an absent package `__main__`; the actual application script must be used. Preserve these attempts and their receipts rather than counting them as passes.

The isolated `worker-service/qualified-07` attempt retains 27 passes and three failures: first verification lazily loaded libseccomp after the reviewed inventory, preparation compared the controller inventory with a separate CLI observer, and an assertion assumed OpenSSL was a shared extension although this interpreter embeds it. The repairs preload the existing seccomp library before review, keep execution comparison separate from preparation, and assert the actual interpreter linkage. The successor focused scope is 19 service, eight independent-readback and three runtime-identity tests. These overlap earlier scopes and must not be added to them. Actual pinned Atmos/provider/Azure-protocol composition and its retained failures are recorded separately by the native service journey.

## External production gates

Trusted run and storage bindings attest installed host-controller checks. They do not claim GitHub/Azure DevOps authentication or certify encryption from a supplied boolean. The organization must provide actual run identity verification, an approved quota-bounded encrypted job/scratch/artifact store, key custody/recovery and retention evidence, reviewed TLS broker interception trust, independent signer and least-privilege identities. Laboratory storage is private plaintext and is explicitly unqualified for the production profile.

Actual native provider/backend lifecycle evidence, independent authenticated policy/settings/assignment readback, state transition and convergence, native host/CI routes, device checks, AppSec findings and accountable organizational approval remain distinct release gates. The provider malformed-error crash finding remains open unless a separately authorized repair and exact replacement artifact evidence close it. No new production credentials, deployment or tenant mutation is performed by this local qualification.
