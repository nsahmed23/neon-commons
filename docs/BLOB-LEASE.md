# Azure Blob lease mechanics

`intune_iac/blob_lease.py` implements a host-held lease on one existing Azure Blob. The live factory performs real lease writes only when the operator explicitly creates a backend role from an existing live identity binding and the exact opaque backend credential handle used for that binding. No live Azure lease was attempted during this work. Live lease qualification remains **BLOCKED**.

```python
from intune_iac.blob_lease import backend_role_live, require_live_lease

# binding and backend_credential come from the protected operator host.
# This explicit action permits acquire, renewal, and release on its bound blob.
role = backend_role_live(
    binding, credential=backend_credential,
    expected_etag=observed_strong_etag, timeout=5,
)
with role.acquire() as lease:
    require_live_lease(lease, binding)
    # The host watchdog calls lease.check_active() before and after bounded work.
    # Provider execution remains separately network-denied in this release.
```

The host supplies credentials in memory; neither JSON evidence nor environment variables create a role or capability. The laboratory factory accepts only laboratory bindings and produces laboratory capabilities that live guards reject. Live factories expose no replacement transport, URL, or clock input. The Python process, its dependencies, operating-system trust store, clock, and memory must be protected; these types do not contain a compromised interpreter or privileged same-host attacker.

The fixed operation is HTTPS `PUT` to the identity binding's validated public Azure Storage account, container, and resolved workspace blob, with `?comp=lease`. It uses API version `2023-11-03`, a proposed UUID, and a 60-second lease. Acquisition requires status 201 and the same lease ID; renewal requires status 200 and preserves that ID. Release uses only that owned ID. There are no break, change, delete, create, redirect, retry, or automatic reacquisition operations. Backend tokens use only the Storage audience through the identity binding's bounded token method.

`expected_etag` is optional and must be a quoted strong ETag. When supplied, every lease request sends `If-Match` and checks the returned ETag. Omitting it establishes only the lease ownership observation, without a fresh exact state revision comparison at acquisition. A host needing revision binding must provide a freshly observed ETag and retain the separate state digest, lineage, and serial checks. Lease operations do not restore state or infrastructure.

The local expiry is conservative: 58 seconds from the start of acquisition or renewal, including credential acquisition and network time. `check_active()` renews when at most 30 seconds remain and checks activity again afterward. Renewal refuses an already expired local lease even where Azure might permit renewal. The host must call this guard throughout work; no background renewal thread is started. Identity freshness also remains required: the host's separate identity recheck must preserve the existing observations, and a stale, changed, closed, or inherited-after-fork binding loses local authority.

Each operation has a maximum configurable ten-second request budget. Credential and lease IO share that budget; renewal and release additionally use only the remaining local lease lifetime. The native transport caps concurrent workers at four, response bodies at 4 KiB, and accepted headers at 100 / 16 KiB. A caller deadline includes DNS waiting. A cancelled resolver may finish later and retain its worker slot until it finishes; cancellation prevents it from starting a request. A request already dispatched can succeed remotely after local timeout. Closing a connection cannot undo a request already sent.

Any failed, malformed, delayed, cancelled, or uncertain acquisition yields no capability. An uncertain renewal permanently loses the capability. There is one acquisition attempt per role and no automatic retry. A release result is either `released` or `release_unknown`; subsequent release calls return the same receipt without another request. Once authority is lost, cleanup does not send another lease request. A remote lease may therefore remain until its server-side duration ends, including after an uncertain renewal. The context manager preserves an exception from its body; if the body succeeds but release is unknown, it raises an error.

Evidence is a redacted record of the latest transition. A saved `held` receipt may be stale and is never proof of current ownership. Only the process-held capability's guard can check local activity. The guard returns `None` on success and raises on failure, so a protected host can compose it with its watchdog; it does not authorize execution.

An Azure Blob lease limits writes and deletes of that blob when the service enforces the lease ID. It does **not** fence Microsoft Graph operations, prove exclusive Intune writers, prevent container deletion, grant approval, or make provider execution safe. An external Graph writer can still mutate tenant configuration. Live qualification must exercise real lease/RBAC behavior, competing writers, expiry, interruption, and deployment-specific writer controls before any mutation release gate can pass.

Validation here uses recorded API-contract response fixtures, a separate one-owner state model, and mocked native HTTPS connections. These are executable local tests, not captured tenant traffic and not a live service qualification. The source retrieval record and actual RED/GREEN logs are under `research/production-completion/leases/`.

Primary Microsoft references, retrieved 2026-10-04:

- [Lease Blob](https://learn.microsoft.com/en-us/rest/api/storageservices/lease-blob)
- [Storage API version 2023-11-03](https://learn.microsoft.com/en-us/rest/api/storageservices/version-2023-11-03)
- [Authorize with Microsoft Entra ID](https://learn.microsoft.com/en-us/rest/api/storageservices/authorize-with-azure-active-directory)
- [Conditional headers for Blob operations](https://learn.microsoft.com/en-us/rest/api/storageservices/specifying-conditional-headers-for-blob-service-operations)
