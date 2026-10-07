# Native worker provider and Atmos continuation

The new `intune_iac.worker_provider` prepares a closed single-policy project and reviewed worker control files for `worker_host` and `worker_service`. It does not grant approval, authenticate an identity, or dispatch a process. The original IP-denied executor remains unchanged.

`ProviderSpec` binds the provider principal, typed `AzureBackendSpec`, immutable policy ID, source revision/digest, admission digest and the existing narrow Settings Catalog configuration. `WorkerProviderAdapter(spec, lockfile=bytes)` exposes `binding()`, `source_files()` and `control_files(operation, saved_plan=None, credentials=None)`. `publish_files(new_directory, files)` writes a new private durable directory and preserves collisions/failures. Only a process-held `BrokerCredentials` capability can supply native placeholder environment values; its entire authenticated identity/backend/state configuration must match the adapter. Real client secrets stay with the broker. No caller environment, arbitrary command, HCL, backend, provider source or selector is accepted.

The pinned route is Atmos 1.230.1, OpenTofu 1.13.1, and the retained repaired Microsoft365 1.0.0 provider. The generated project disables Atmos YAML functions/templates, automatic init, backend generation and automatic apply approval. Explicit initialization uses the exact supplied lock. Plan, refresh-only observation, readback and second-plan artifacts are distinct. Saved application uses **`--from-plan --planfile /control/approved.plan`** and verifies exact binary bytes immediately before invoking Atmos. The host must pin all native tools, source, control and plan bytes and maintain its read-only mounts. Plan approval and live-precondition checks belong to the service guard.

A native probe found that `--from-plan=/path/plan` attempted a replacement plan instead of the saved plan. It failed at an EOF approval prompt without mutation; the failed output is retained. The separately tokenized route dispatched the actual saved binary plan and passed a native fixture. `show --init-mode=never` is unsupported; fixed `components.terraform.init.mode: never` also prevents automatic init from contaminating JSON outputs. These details are pinned-version findings, not portable command promises.

The generated worker starts the pinned relay, waits for its exclusive `/job/relay.ready` marker, and installs exit/signal cleanup preserving a primary failure. Each dispatch needs a fresh private job directory. It never removes stale readiness evidence. Relay v3 is a new dependency of this generated control; native protocol capture07 used relay v2, and does not qualify v3 merely by association.

## Demonstrated scope

Evidence is under `work/evidence/epoch-20261007-r4/worker-provider/` in the complete work corpus. The following are separate evidence classes; counts must not be added to historical 1,242 or 1,141 test totals.

- `tests-05.txt`: 14 focused Python contract cases pass for closed inputs, source/lock substitution, tenant/principal/state binding, exact saved-plan argv, binary bytes, private publication, and broker placeholders. Earlier failures remain in `tests-01.txt` and `tests-03.txt`.
- `native-provider-offline-01/ASSERTIONS.json`: actual pinned Atmos → OpenTofu → provider initialization, validation and schema RPC with IP networking denied. The selected schema exactly matches `e081e5bf4c7e8ea2c599ef1c65c73bb525a8f9a2d98b66baed6cc1243a91aef3`. Azure backend was explicitly removed for this offline fixture.
- `native-oauth-capture-04/provider/INDEPENDENT-IMPORT-ASSERTIONS.json`: six earlier independent import assertions are preserved and reused, not rerun.
- `native-oauth-capture-07/provider/host/receipt.json`: actual native import, no-change first plan, description-only correction, saved-plan apply, separate policy/settings/assignment reads and no-change second plan completed against a nonforwarding synthetic TLS service. One immutable policy, 32 HTTP requests, no device/service claims.
- `native-oauth-capture-05/backend/host/receipt.json`: a **separate** native Azure backend init/plan observed workspace listing, existing state reads, lease acquisition, lock metadata and release; 23 HTTP requests against synthetic storage, no native state PUT.
- `INDEPENDENT-NATIVE-ASSERTIONS.json`: 26 read-only assertions over the retained lifecycle and backend artifacts, without importing the product normalizer. This overlaps the earlier six import checks. Artifact digests identify exact state, binary plans, request recordings and host receipts. It is not a third lifecycle run.

The TLS recording fixtures are not `EgressBroker` authorization. They never forward to external hosts, use synthetic tokens, and run native tools in the pinned network-none host. The provider lifecycle and Azure backend exercise remain separate. No combined protected native application, real Azure/Graph/Intune authentication, CI approval, interruption recovery, Windows host or device effectiveness is established by these results.

## Observed native protocol and remaining integration

Both pinned provider and native backend request tenant-specific MSAL metadata, then `/TENANT/oauth2/v2.0/token`. Observed forms include `claims={"access_token":{"xms_cc":{"values":["CP1"]}}}`, exact role client ID, placeholder client secret, `grant_type=client_credentials`, and the single resource `.default` followed by `openid offline_access profile`. Content type is `application/x-www-form-urlencoded; charset=utf-8`. Backend audience is storage; provider audience is Graph. Dynamic request IDs are not identity evidence. Source inspection alone was superseded by the actual captures, without discarding either.

The provider reads the policy using a slash ID, settings and assignments using quoted IDs, updates the policy using **PUT**, then separately POSTs `/assign`. Both observed mutation bodies use **HTTP chunked transfer encoding**. Capture06 did not decode chunks and failed; capture07 repaired only the fixture decoder. The production broker must implement and independently test a bounded, unambiguous chunk decoder before these actual native writes are supported; it must reject conflicting lengths, unsupported encodings/trailers and oversized bodies. Relaxing its framing checks is not an acceptable workaround.

The backend lists only `/CONTAINER?comp=list&marker=&prefix=KEYenv%3A&restype=container`, reads `/CONTAINER/KEY`, acquires `?comp=lease` with a native proposed UUID and duration `-1`, writes the native base64 Terraform lock metadata, then clears that metadata and releases the same lease. API header was `x-ms-version: 2026-06-06`. Exact container/key, metadata fields, allowed lease transitions and authenticated identity must be bound by the broker/service. A passed local lease fixture does not establish Azure RBAC or lease-loss recovery.

The real description-only provider plan has computed `last_modified_date_time` and `settings_count` unknown after apply. The initial strict native state-write contract rejects unknown values. A reviewed, independently observed computed-field contract is still required for combined Azure-backed application; do not widen arbitrary state writes or claim the integrated path has passed.

Capture03 returned an intentionally malformed synthetic Graph 400 payload and native output said **“Plugin did not respond.”** Its cause is unresolved. Successful later fixtures do not close this negative. Keep `native-oauth-capture-03`, failed capture06, initial AF_UNIX path-length failure, prior automatic-plan attempt and test failures. Host receipts for successful cases prove cleanup only in their stated cooperative local scope.

## Replay and next action

From the project directory:

```sh
python3 -m unittest plugin_tests.test_worker_provider_r4 -v
python3 ../../evidence/epoch-20261007-r4/worker-provider/assert-native-receipts.py
```

The second command is read-only and reasserts retained native artifacts. Native replay scripts preserve their tested fixed fresh-directory names and therefore refuse to overwrite existing evidence. Copy the chosen script to a new evidence attempt, select new short Unix-socket and output directories, retain its exact bytes and receipt, then run only the needed native qualification. Do not rerun the complete maintenance lifecycle merely to replace existing passing receipts.

Next integration order: complete broker framing/lease/computed-state contracts from the observed requests; bind the adapter, host and broker through the service manifest/one-shot authority; run the exact combined fixture with independent mutation/state assertions and negative controls; then prepare the real authorized disposable service route. Platform qualification and organizational production approval remain blocked on the declared external evidence and accountable authorization, independent of local implementation progress.

## Integrated Azure preparation and preserved dispatch failures

The new local fixture in `work/evidence/epoch-20261007-r4/worker-provider/native_service_fixture.py` persists synthetic Graph policy/settings/assignments and exact Azure Blob state bytes, metadata and lease state. It serves only loopback TLS and optional fixed-host Unix CONNECT, without forwarding. It includes a distinct collector principal and explicit direct-assignment source metadata. Its `transport` is a laboratory adapter, not receiving-service authentication.

`prepare_native_service.py` executed the actual pinned Atmos → OpenTofu → provider route using the generated Azure backend: initialization, identity-preserving import, a no-change first plan, and one description correction saved for later approval. There was no Graph mutation. `native-service-prepare-01/receipt.json` records 85 fixture requests and 11 independent assertions; SHA-256 `79dabbcf4fa0b7a86a17fd8edb996ae5b1ceeb20a75c20ce6f4d900b56e4fcd0`. The exact saved plan is 5,850 bytes, SHA-256 `0d1b65680455d197b9a3c90bd747f1f745f82e2194f437a46ecd1e412bc4d767`. Prepared Azure state is serial 13, lineage `77777777-7777-7777-7777-777777777777`, SHA-256 `64589b745c85615f67d689cc918765f7aca6254dd7965c5067bb824824304aa8`. Import's state update is distinct from a policy deployment.

The independent reader capture in `native-service-reader-01` has complete raw coverage and retains setting ID `37`. Its management mapping remains unsupported for the existing ID/assignment mapping and unresolved reference, ownership and provider-qualification gates. Those blockers are preserved; neither the fixture nor normalizer was changed to label them supported.

The signed composition runner is `native_service_journey.py`. It reuses the prepared exact plan in a new copied fixture and new signed operation; it does not replan after approval. Its actual entrypoints are CLI `service prepare/review/status/attach`, process-held `ServiceJob.run`, fresh Graph preconditions, the native network-denied worker with TLS broker, sealed independent Graph/backend readback, `ServiceJob.reconcile`, observation publication, `workbench service-link/views`, and a separately generated second plan.

Preserved attempt 01 rejected `service prepare` because the ambient system libsodium bytes differ from the qualified verifier pin. The replay must use the existing explicit test-host library location, whose digest remains `fe00408090ea084504d7cb0130af56a22554fe299034b864551b65a64ca8a7b5`; no validator hash was weakened. Attempt 02 consumed one signed operation and stopped during native Azure initialization before any broker route or lease dispatch. State and Graph bytes remained unchanged; the stopped container was removed. Its `FAILURE-ANALYSIS.json` has SHA-256 `67d5f2d130d402593c7eabaa76c218165a23c5f3716735dacb51ec2f365032a4`. The broker owner independently reproduced native Go's exact optional CONNECT `User-Agent: Go-http-client/1.1`, which the earlier envelope rejected. This is a transport-integration finding, separate from the stopped malformed-provider-error defect.

From the source root, the prepared-plan composition replay is:

```sh
INTUNE_TEST_VALIDATOR_LIBRARY=/workspace/intune-continuation/work/evidence/epoch-20261005/approval-prerequisite/libsodium.so.23.3.0 PYTHONPATH=. python /workspace/intune-continuation/work/evidence/epoch-20261007-r4/worker-provider/native_service_journey.py NEW_PRIVATE_ATTEMPT_DIRECTORY
```

The runner must use a stable reviewed runtime inventory while preparing and executing its signed manifest. Every failed attempt remains retained; a successful isolated retry does not rewrite prior operation outcomes or close historical provenance/provider findings. These procedures perform only authorized local synthetic-fixture work and cannot establish platform qualification or production approval.

## Qualified local protected native journey and fault controls

`native-service-journey-03` completed the signed protected native path with the prepared Azure-backed binary plan. The broker admitted 33 requests, including exact policy PUT and assignment POST, fresh independently authenticated-interface reads before both writes, observation-bound computed state admission, native state persistence, metadata clearing and lease release. Independent Graph/backend readback released the operation reservation through `ServiceJob.reconcile`. The real text application reopened the same operation through `service attach` and `workbench service-link/views`; the exact raw unsupported observation remains navigable. A separately created native second plan was no-change and preserved state bytes. Its 17 assertions passed; its 181 fixture requests include 85 inherited preparation requests, so only 96 are new. None is real Graph/Azure/CI/device qualification.

The successful receipt is SHA-256 `e10ed6da4841e210b6d8736f34e4c8c4ce084a43a7d03dcfbb8c5aeb9ae614af`. `TESTED-SOURCE-LINKAGE.json` preserves all 67 runtime package files matching the signed manifest and the four local integration harnesses (71 files), SHA-256 `6ace3c9a78616172addccb5c4f14c5b3f88a1b389b7fc1f2a3dc8a17d34dc9de`. This records exact tested working-tree bytes separately from the declared source revision; it does not retroactively assert that uncommitted changes were committed before execution.

The second correction was an explicitly new restoration operation. `prepare_native_restoration.py` reused the prior independently checked state-14/no-change-plan evidence by exact state bytes, then generated a fresh restoration plan that reversed only the reviewed description. No import or prior lifecycle was repeated. `native_restoration_journey.py` signed and applied the new binary plan `62b5ce1f4483c7d8673a659ed9f45d0427cf0914b8baa332a7ceb152d9b7e3f7`, independently read it back, persisted state 15 and generated a no-change second plan. `native-restoration-journey-01/receipt.json` has SHA-256 `4e1335c982fe3f3c9dae44e3755c2e976055ebc5f5b5bfd723b4f54c709c5b44`. This is a new approval and operation, not replay or resumption of the old mutation.

The following controls each use a separate copied synthetic fixture and a newly signed operation. Their expected operation result is failure/uncertainty; PASS below refers only to the independent negative-control assertions. They do not establish successful deployment, automatic cleanup authority, device effectiveness or host power-loss behavior.

|Retained control|Demonstrated outcome|Receipt SHA-256|
|---|---|---|
|`native-assignment-failure-01` (16 assertions)|Policy PUT accepted, conformant assignment POST denied; policy effect retained, assignment/settings identity preserved, original state bytes retained, lease/metadata and operation reservation retained, no later write or false convergence.|`25d4c51fd49a6faa21d98edad2d126f8cbe6434ebba7f9b280d61da1fcce8537`|
|`worker-broker/native-cancel-acquire-01` (14 assertions)|Actual cancel CLI after native lease acquisition; state and Graph unchanged, uncertain lease result retained, host stopped/removed; recovery inspector grants no release authority.|`f17166cb16fc383195f72e6342b608c655ecaa2bdc67e305079c3057ace947c8`|
|`native-cancel-policy-01` (15 assertions)|Actual cancel CLI after policy commit but before the broker confirms its response; partial policy effect and unchanged backend state remain explicit; no replay/unlock.|`d0e0bbf4ad6a26a2f78f90836cacbc81b7868a954f233027aea10e3552ad2722`|
|`native-cancel-state-evidence-01` (15 assertions)|Actual cancel CLI after state PUT persisted but before broker response evidence; state advances but outcome stays unknown, lock/metadata and reservation remain, no false reconciliation.|`130cd5cd202d7b3c75b1a2db39e9b26827ead6a84675ca6a464290f0b4630308`|

The restoration exercise uses the successful known state; it does not erase or restore the separate partial-failure fixtures. Explicit recovery of their retained native leases and refreshed partial-state baselines requires its own reviewed operation. The existing computed-state profile rejects unreviewed provider refresh drift, so partial-state recovery cannot silently push an errored state file, weaken that gate, or turn refresh-only state adoption into accepted repository intent.

Additional exact local replay entrypoints, using the same explicit validator-library environment as above:

```sh
PYTHONPATH=. python /workspace/intune-continuation/work/evidence/epoch-20261007-r4/worker-provider/native_assignment_failure.py NEW_PRIVATE_ATTEMPT_DIRECTORY
PYTHONPATH=. python /workspace/intune-continuation/work/evidence/epoch-20261007-r4/worker-provider/native_cancel_write.py NEW_PRIVATE_ATTEMPT_DIRECTORY policy
PYTHONPATH=. python /workspace/intune-continuation/work/evidence/epoch-20261007-r4/worker-provider/native_cancel_write.py NEW_PRIVATE_ATTEMPT_DIRECTORY state-evidence
PYTHONPATH=. python /workspace/intune-continuation/work/evidence/epoch-20261007-r4/worker-provider/native_restoration_journey.py NEW_PRIVATE_ATTEMPT_DIRECTORY
```

Counts above describe separate workloads and overlapping assertions, not an additive replacement for the historical 1,242/1,141 suites. The provider malformed-error finding and stopped untested repair remain unresolved; these conformant native paths do not qualify that failure mode or authorize retrying the rejected repair lane.

## Explicit partial-commit recovery qualified locally

The retained assignment-denied operation now has a separate successful continuation on a new copied receiving fixture. The original failure fixture, failed outcome, original policy binding and consumed approval remain unchanged. A newly signed exact-lease release retained the original reservation and state-13 bytes. A fresh native plan independently exposed description/last-modified drift, then proposed restoring the original description. The ordinary computed-state contract still rejects drift; the separate bounded description-recovery contract validates persisted state, provider-refreshed prior state and sealed independent observation separately.

`partial-recovery-journey-02` used a new exact binary plan (`bf65ab9c1876dc6054389ed7c59eb5b98945d9c59e67debdfb8b2bfe61568828`) and the original authority database. A separately signed temporary successor was prepared and cancelled through the text CLI; cancellation returned ownership to the failed predecessor without erasing the consumed transfer. A different transfer then assigned the scopes to the final new operation. Its own exact-plan signature authorized one native execution, followed by independent Graph/backend readback, reconciliation, observation publication, text views and a no-change second native plan. Final state advanced once to serial 14. The old failed outcome was not rewritten.

The journey passed 20 scoped assertions and four transfer rejection controls; its 328 recorded fixture requests include 219 inherited requests (109 new). Receipt SHA-256: `32d472afd17ed99e600df12c0de73d55dddc840622a2fe6d12b986992ac99af4`. A separate evaluator importing no product implementation passed 18 overlapping literal JSON/SQLite/raw-byte assertions, including an exact entire-state projection, preserved settings/nulls/IDs/filter/exclusion metadata and correctly marked new laboratory captures; `INDEPENDENT-ASSERTIONS.json` SHA-256 `2ca532ee97d5214ad1c1c2bec649b6fef215c2407de379d6c2656a105307af16`. Do not add these overlapping counts. The exact 73 package files and four tested harnesses are archived under `tested-source`; source linkage SHA-256 `421f5856072e50446b4b97d83651369f87ee92872bbbbb41662ad671e976552b`.

The stricter synthetic Blob fixture now changes ETag on metadata set/clear. Its actual native plan demonstrated both transitions with unchanged state content. The earlier completion rejected this case; `metadata-etag-before-01` preserves that failure. The repaired read-only completion binds old and current ETags while requiring identical state bytes, semantic hash, lineage, serial and length, exact identity/target and independently unlocked known metadata. It does not attribute the ETag change to an actor, relax mutation If-Match checks or claim real Azure evidence. Attempt `partial-recovery-journey-01` also remains failed: an evidence-only policy helper admitted only the ordinary contract. A separate recovery helper repaired that harness integration; no product gate was weakened.

This covers description-only partial-commit recovery at the stated local native protocol scope. The separate cancellation-after-state-write fixture has state 14 against an original state-13 approval, and the exact original-state release gate correctly rejects it. Recovery of that advanced state requires a separately reviewed final-state verification/release path. Other drift families, real Azure/Graph/CI/native Windows/device qualification, the stopped malformed-provider-error defect and organizational approval remain open.

Recovery authorizations are one-use. Replaying the successful fixture against its already-consumed original authority is intentionally rejected. A complete local replay uses a **new failed-operation seed** and new evidence directories; it reuses the already qualified initial import/no-change preparation rather than repeating it:

```sh
INTUNE_TEST_VALIDATOR_LIBRARY=/workspace/intune-continuation/work/evidence/epoch-20261005/approval-prerequisite/libsodium.so.23.3.0 PYTHONPATH=. python -B /workspace/intune-continuation/work/evidence/epoch-20261007-r4/worker-provider/native_assignment_failure.py NEW_FAILED_SEED
INTUNE_TEST_VALIDATOR_LIBRARY=/workspace/intune-continuation/work/evidence/epoch-20261005/approval-prerequisite/libsodium.so.23.3.0 PYTHONPATH=. python -B /workspace/intune-continuation/work/evidence/epoch-20261007-r4/worker-provider/release_partial_fixture.py NEW_RELEASE NEW_FAILED_SEED
PYTHONPATH=. python -B /workspace/intune-continuation/work/evidence/epoch-20261007-r4/worker-provider/prepare_partial_recovery_strict_metadata.py NEW_PREPARATION NEW_RELEASE
INTUNE_TEST_VALIDATOR_LIBRARY=/workspace/intune-continuation/work/evidence/epoch-20261005/approval-prerequisite/libsodium.so.23.3.0 PYTHONPATH=. python -B /workspace/intune-continuation/work/evidence/epoch-20261007-r4/worker-provider/native_partial_recovery_journey.py NEW_FINAL NEW_FAILED_SEED NEW_PREPARATION NEW_RELEASE
```

The explicit path-parameter adapter was added after the retained successful run; its syntax was checked, while the tested original runner bytes remain archived. No second full recovery was run merely to inflate counts. The independent result evaluator replays against the retained qualified directory with `python -B .../assert_partial_recovery_result.py .../partial-recovery-journey-02`.
