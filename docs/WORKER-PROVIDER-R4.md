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
