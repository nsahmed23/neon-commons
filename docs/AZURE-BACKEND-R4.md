# Closed Azure backend adapter

`intune_iac.azure_backend` adds the backend contract required by a protected
execution worker. It does not enable a live apply switch. The existing provider
executor, network denial, identity bindings and Blob lease implementation are
unchanged. No Azure credentials, deployment or tenant mutation were used to
qualify this increment.

The initial profile is Linux x86_64, pinned OpenTofu 1.13.1, Azure public cloud,
explicit client-secret identity, an existing state blob and the default
workspace. The contract rejects alternative clouds, workspace naming, arbitrary
backend options, migration, state push, force unlock and destruction. Broader
identity and workspace profiles require separate implementation and evidence.

```python
from intune_iac.azure_backend import AzureBackendAdapter, AzureBackendSpec

# IdentitySpec and BackendSpec are declarations; neither grants authority.
adapter = AzureBackendAdapter(AzureBackendSpec(
    backend_identity, backend_spec, "coordination/pilot-policy.lock"))
adapter.publish(private_parent / "new-backend-package")
adapter.verify_published(private_parent / "new-backend-package")
```

Publication creates a new owner-private directory and three exact files:
`backend.tf.json`, `backend-binding.json` and `backend-manifest.json`. Files are
created exclusively with mode 0600, fsynced and then their directory and parent
are fsynced. Existing outputs, symlinks, hard-linked files, unexpected files and
changed bytes are rejected. An interrupted publication is preserved for
investigation; it is never silently deleted or overwritten. These controls
assume a trusted worker account/filesystem and do not establish hostile-host
containment or power-loss qualification.

Configuration explicitly selects Entra authentication and disables CLI, MSI,
OIDC and AKS identity fallbacks. The backend secret is absent from configuration
and manifests. `credential_environment(binding, handle)` requires an existing
typed live or laboratory identity binding and the exact backend credential
handle, verifies its identity/target, and returns only fixed backend variables.
It does not read ambient environment variables. The caller must start its child
with a fresh allowlisted environment, never merge the returned dictionary into
ambient environment. Provider credentials remain distinct. A laboratory binding
does not become a live capability, and saved binding JSON grants nothing.

`verify_metadata` checks the actual initialized `.terraform/terraform.tfstate`
backend configuration and separately observed workspace. The cached backend
hash is not treated as authority. The check rejects changed target fields,
auth-route changes, unknown fields and persisted secrets/alternate endpoints.
The pinned 1.13.1 backend schema was inspected to enumerate optional empty
metadata fields; a different engine/schema must not silently reuse this profile.

State has two independent identities: the digest of the exact raw bytes and a
digest of their parsed content. `StateRevision.observe` preserves that
distinction, validates state v4/lineage/serial and requires a strong ETag.
`verify_precondition` compares the exact admitted state and ETag before dispatch.
`verify_transition` permits unchanged state or forward serial movement within
the same lineage, rejecting rollback, changed bytes at the same serial, or
changed bytes with a reused ETag. Its result explicitly establishes neither
execution of the approved plan nor service convergence. Authentication of the
response and independent policy/assignment readback remain worker duties.

The original `BoundContext.recheck()` still requires the original state revision
to remain unchanged. Do not use it to approve a changed post-operation state or
relax it to allow arbitrary evolution. The worker needs a distinct authenticated
identity/target lifetime and explicit precondition/postcondition observations.

Native OpenTofu owns the Azure **state** blob lease. The worker's cooperative
operation lease must use the separately declared existing **coordination** blob;
the adapter rejects identical keys. Wrapping OpenTofu with the original
`BlobLease` on the state blob would contend with OpenTofu's own lease. Neither
lease fences external Graph writers. The worker still needs a durable one-writer
ownership index and must expose residual external-writer races.

Closed native argv suffixes are exposed by `native_command`: init, workspace,
state pull, ordinary/refresh/readback/second plan and exact-descriptor apply.
An admitted worker supplies the pinned executable, cwd, environment, immutable
plan descriptor, authority checks and process supervisor. The adapter never
dispatches these commands itself. Apply takes only `/proc/self/fd/N`; checking
that N refers to the sealed approved bytes is the worker's obligation.

`init` is consequential: a native Azure backend may initialize missing state.
Before it runs, independently authenticate and conditionally read the existing
state and coordination blobs. Reject absence or a changed revision; do not infer
read-only behavior from the command name. Retain native backend locking and
never add `-lock=false`, `-migrate-state`, `-force-copy` or `-reconfigure` to these
closed commands. The readonly dependency lock must already be admitted.

Changed-scope replay:

```text
python3 -B -m unittest plugin_tests.test_azure_backend_r4 -v
```

The R4 `azure-backend` evidence directory retains feature-absence failure,
subsequent attempts, actual filesystem/concurrency tests and native command
help/schema checks. Native schema qualification runs real pinned OpenTofu with
the unchanged seccomp IP denial: generated configuration reaches the denied
backend request; an unknown backend option is rejected during parsing. This is
native configuration evidence, not an authenticated Azure test, native backend
lifecycle, worker isolation, or production approval.

External qualification must use the exact packaged adapter in the final worker:
verify real cached backend identity and state readback, two native writers,
coordination-lease loss, expiry, state advancement after review, interrupted
state writes, and uncertain outcomes. Prepare a fresh reviewed plan after
reconciliation; never retry a previously dispatched mutation or restore remote
infrastructure by restoring a state file. Organizational owners must separately
approve host/egress, secret delivery, state/plan/export encryption, retention,
key recovery and the narrow pilot scope.

## Generated native state admission

`NativeStateWriteContract` now projects a closed expected state from exact baseline
bytes and exported saved-plan JSON. The controller must authenticate both input
hashes and the binary-plan digest through signed operation authority; this API
never grants write permission. The bounded profile is OpenTofu1.13.1 schema4,
fully known updates to existing single root instances, unchanged immutable IDs and
provider schema versions, exact preservation of private/dependency/unknown fields,
unchanged output types/sensitivity, stable lineage and serial+1. Drift, computed
unknowns, module/index instances, imports/moves/creates/deletes and nonempty check
results fail closed. Formatting changes do not change meaning; no state field is
silently omitted. The broker separately admits exact target, identity, headers,
lease contract and one durable dispatch. Native SDK lease/date header qualification
remains a gate; content validation alone is not a live backend integration.

The 24-test focused adapter result is `azure-backend/state-write-contract-02.txt`
(18 existing adapter checks plus six new projection checks, not additive runs).
`state-write-contract-01.txt` preserves a failed negative fixture caused by shared
Python references between planned and changed attributes; independent deep copies
repaired that fixture. `native-state-admission.json` independently admits the exact
before/plan/after bytes produced by real OpenTofu1.13.1 in worker `native-03`, with
input, source and output hashes. This native proof covers the local output fixture,
not a real Azure state PUT, provider resource, service identity or production run.
