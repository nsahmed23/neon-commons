# Effective target evidence

`intune_iac.target` supplies strict target inspection, whole-binding comparison,
and a fixed read-only public Azure collector. None of these APIs authorizes
execution. The current gate remains **implemented, unqualified for enterprise
execution**. Unit tests use simulated HTTP responses; no tenant call occurred.

## APIs

```python
inspect_target(document: dict) -> dict
compare_targets(expected: dict, observed: dict) -> dict
collect_azure_observations(document: dict, *, graph_token: str,
                           management_token: str, timeout: int = 10) -> dict
```

`inspect_target` accepts `schema_version: target-evidence/2.0` (the current pins), or
`target-evidence/1.0` (the legacy pins, readable for reproduction only), `observed_at`,
and a complete `binding`. It returns `valid`, `status`, `assurance`, fixed
`issues` and `blockers`, and, when valid, `binding_sha256`. Every report carries its document's own
`schema_version` and a `pin_profile`: `current_local_qualification` for 2.0, `legacy_reproduction_only` for
1.0, and none for a document that is unreadable or of an unrecognised version. A 1.0 document is never
upgraded or rewritten as 2.0 by reading it, and a 1.0 document never matches a 2.0 document in a comparison
(`/schema_version` is reported as changed). Inspection and
comparison perform no network or process calls. `execution_authorized` is always
false; a supplied `assurance`, unknown field, null required value, unsupported
cloud, or unrecognized version is invalid. Returned errors contain known field
paths and fixed reason codes, never field values or attacker-provided field names.

`compare_targets` returns `match`, `mismatch`, or `invalid`; valid mismatches
identify every changed binding leaf without disclosing either value. Observation
timestamps may differ because new reads occur later. Every binding leaf, including
the ownership lease expiration, is compared. Both observations must be fresh at
comparison time: no older than 300 seconds and no more than 30 seconds in the
future. Refreshing a timestamp does not authenticate or refresh underlying facts.

The version 2.0 definition is `SCHEMA_V2` in `intune_iac/target.py`; the version 1.0 definition,
`SCHEMA_V1`, is beside it. `research/enterprise-target/target.schema.json` is the version 1.0 schema and
`example-target.json` a deliberately synthetic, expired version 1.0 example: both stay as they were, for
reproduction, and neither describes version 2.0. The embedded runtime schemas are authoritative. The support restrictions are
intentionally narrower than Azure's general naming and authentication support.

## Bound facts

| Section | Required fields and relationship checks |
|---|---|
| Cloud/endpoints | Public Azure only; exact Graph, Entra authority, Resource Manager, and storage audience origins. No alternate hosts, query strings, ports, embedded credentials, or sovereign clouds. |
| Intune identity | Tenant, optional target subscription, principal object ID, client ID, and auth kind; workload federation requires issuer/subject/audience, while certificate/managed identity require a null federation record. |
| Repository | Physical manifest selector **and** logical Atmos stack, component/implementation path, Git revision, dirty-file/source/effective-configuration digests, and runtime layer digest. Declaring these does not evaluate Atmos or environment overrides. |
| Backend | Separate backend tenant/subscription/principal/client/federation; Azure storage resource ID, matching account blob endpoint, container, key, workspace, resolved blob, state lineage/serial/full-state digest. |
| Ownership | Single-writer declaration, writer ID, scope digest, lease ID and future expiration. This is a claim; the module does not acquire or verify a real lock/lease. |
| Toolchain | Version 2.0: Atmos 1.230.1 (SHA-256 `f3b5b42e897a2778678cc1231e7a4e2476773bc61ea2af225586dc4e96408802`), OpenTofu 1.13.1 (SHA-256 `a325c8c2f6834575e440b03c2ba67f94256072754ac7787fea718be6f01fef6a`), microsoft365 1.0.0 and the provider-lock digest; the pair and both digests are the current local qualification in `intune_iac/native_pins.py` and any other value is invalid. Version 1.0 keeps the legacy pair (Atmos 1.199.0, OpenTofu 1.10.0) with free digests. Tool hashes are bound, not established from actual executable bytes here. |

For the pinned OpenTofu Azure backend, the default workspace uses `key`.
A named workspace uses `key + "env:" + workspace`; it is **not** a generic
workspace directory prefix. The storage resource's subscription and account must
agree with the backend subscription and blob endpoint. GUIDs/digests use canonical
lowercase here; noncanonical casing is rejected rather than silently normalized.
State lineage and serial are required and cannot be replaced by configuration
hashes. Backend identity can differ from Intune identity and is compared separately.

Documents are bounded to 64 KiB, 512 value nodes, depth 12, 64 entries per
container and 2,048 characters per string. C0/DEL controls, cycles, non-JSON
values, floats, invalid timestamps and malformed names/IDs are rejected. All
three APIs copy bounded inputs before validation/use; later caller changes do
not substitute a different resource after inspection.

## Read-only service collector

Only an explicit `collect_azure_observations` call performs these three GETs:

1. `https://graph.microsoft.com/v1.0/organization?$select=id`
2. `https://management.azure.com/subscriptions/{backend_subscription}?api-version=2022-12-01`
3. `https://management.azure.com/{storage_resource_id}?api-version=2023-05-01`
   (the resource ID already starts with `/`, so only one slash is transmitted).

It requires exactly one organization without continuation and verifies that
organization ID, subscription ID/tenant/enabled status, storage resource ID and
primary blob origin match the declared target. It neither obtains credentials
nor follows redirects, proxies, cookies, next links, endpoints returned by a
service, or arbitrary URLs. It never calls listKeys, the state blob, Atmos,
OpenTofu, provider processes, or any mutation operation. The Graph token is sent
only to Graph; the management token is sent only to Resource Manager.

HTTPS uses Python's default trusted certificate store with hostname and certificate
verification enabled. Each response is limited to 1 MiB of uncompressed JSON with
unique keys. Non-200/redirect/denied/partial/mismatched responses return
`unavailable`; earlier successful observations remain visible, never a fabricated
empty result. Each successful record contains kind, fixed host, method, collection
time and a fact digest. No bearer token, service payload, exception text, or
identity value appears in ordinary output.

The `timeout` is an integer from 1 to 30 seconds. Socket connect operations use
it; after connection, a deadline shuts down the socket to stop slowly streamed
headers/body. DNS resolution still depends on the OS resolver's limits, so this
API alone does **not** promise a total wall-clock bound. An enterprise execution
host must additionally enforce a supervised process deadline and trusted network,
DNS, certificate store, credentials and runtime. Transport behavior is unit-tested
with a simulated connection; live TLS/authorization/platform qualification remains.

## Authentication boundary

A successful service response shows that the service accepted the supplied bearer
credential for that resource read over the configured TLS connection. It does not
prove that a declared principal, client, federation subject, repository, backend
state, or writer is the actual execution identity. Tokens remain opaque: decoding
Microsoft-owned API access tokens is not an identity-validation mechanism.

Serialized collector output is a report, not an authenticated capability. Loading
it later never establishes authenticity or recency. `inspect_target` only accepts
the strict evidence document, not an observation report or approval receipt.
Independent credential-provider identity evidence, protected collection/approval
handoff, effective Atmos runtime inspection, state readback, real writer exclusion,
and final execution-context comparison remain required. Matching local JSON cannot
satisfy those gates.

The source ledger pins the examined OpenTofu/Atmos source and links Microsoft API
documentation. Native backend `StateMgr` is deliberately not used as a supposedly
read-only collector: the inspected implementation can lock and create empty state
when no remote state exists.
