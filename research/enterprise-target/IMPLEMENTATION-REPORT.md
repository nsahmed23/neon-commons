# Effective target implementation report

Task 2 of `docs/superpowers/plans/2026-09-30-enterprise-execution.md` is implemented
within the offline/transport contract boundary. Enterprise gate E03 remains open.
No live identity lookup, tenant call, state read, native Atmos invocation or cloud
mutation was performed by this workstream. No new runtime dependency was added.

## Shipped interfaces

```python
inspect_target(document: dict) -> dict
compare_targets(expected: dict, observed: dict) -> dict
collect_azure_observations(document: dict, *, graph_token: str,
                           management_token: str, timeout: int = 10) -> dict
```

Owned files: `intune_iac/target.py`, `plugin_tests/test_target.py`, `docs/TARGET.md`,
and this research directory. Root owns CLI/release integration. The first two APIs
accept the strict `target-evidence/1.0` document and always emit
`execution_authorized: false`, `assurance: supplied_consistency_only`.
Matching 54 binding leaves is a consistency check; timestamps are separately
validated against a five-minute freshness window. Both Intune and backend identity
are explicit; independent backend tenants/principals are not silently conflated.

The collector improves on a comparator by making three fixed TLS GET requests
when explicitly invoked. It observes Graph organization identity and Azure
subscription/storage identity against the binding. It sends opaque bearer tokens
only to the two fixed Microsoft origins. It has no credential acquisition,
redirect, arbitrary URL, listKeys, shell, provider or mutation path. The result
remains a partial service observation: principal/client/federation, effective
Atmos configuration, state blob and single-writer ownership are still unverified.
Reloading serialized JSON does not preserve trust or grant authority.

## Source findings and implementation decisions

Exact raw-source revisions, paths, SHA-256, byte and line counts are in
`source-ledger.json`. Source files and original licenses are under `raw/`.
Their upstream code was inspected, not executed by this workstream. Runtime code
is original Python; no upstream authentication or RDF implementation was copied.

| Pinned source | Inspected behavior | Consequence |
|---|---|---|
| OpenTofu `1ffecd7f37654f92b680a70c838d24fc9a363669` (v1.10.0), Azure `backend_state.go`, 24–28 and 149–155 | Default workspace maps to key; named workspace maps to key plus `env:` plus name. | Validate resolved blob explicitly; generic workspace-directory assumptions are rejected. |
| Same file, 74–138 | `StateMgr` refreshes and may lock/write/persist empty state if state is absent. | Do not expose it as a read-only observation primitive. Collector does not invoke native backend state access. |
| Same revision `backend.go`, 40–197; `arm_client.go`, 46–137 | Environment/config auth inputs and access-key/SAS shortcuts; auth builder supports CLI/cert/secret and enabled MSI/OIDC; storage AAD token is conditional. | Bind separate provider/backend identity and runtime layers. Do not infer Entra identity from repository vars or assume `az account show` authenticates the provider/backend. |
| Atmos `10886fe5b17f034c01e2396c0c47de19575a8065` (v1.199.0), `stack_utils.go`, 15–65 | Workspace may come from templates, patterns, explicit metadata or context; disabled workspaces use default. | Require logical stack, physical selector and workspace separately; no new simplistic logical-name resolver. |
| Same revision `describe_component.go`, 381–508 | `ProcessStacks` receives template/YAML function flags and optional auth manager; the describe path can use auth context. | Arbitrary repository-native describe remains executable input. Inspection here never invokes it. |

One attempted raw acquisition used the nonexistent `api_client.go` path (HTTP404).
The directory listing identified `arm_client.go`, which was acquired and inspected.
The failed attempt and correction remain in the source ledger.

Primary API documentation reviewed on 2026-09-30:

- [Microsoft Graph organization list, v1.0](https://learn.microsoft.com/en-us/graph/api/organization-list?view=graph-rest-1.0): organization collection read and permissions. The collector requires exactly one row and no continuation; extra/missing/denied observations are unavailable.
- [Azure subscriptions get, 2022-12-01](https://learn.microsoft.com/en-us/rest/api/resources/subscriptions/get?view=rest-resources-2022-12-01): subscription ID, tenant ID and enabled state are compared.
- [Azure storage accounts get properties, 2023-05-01](https://learn.microsoft.com/ga-ie/rest/api/storagerp/storage-accounts/get-properties?view=rest-storagerp-2023-05-01): resource identity and primary blob endpoint are compared; no keys requested. English-page retrieval errored; the indexed primary Microsoft API page and selected pinned backend code were available.
- [Microsoft identity access tokens](https://learn.microsoft.com/en-us/entra/identity-platform/access-tokens) and [token purpose guidance](https://devblogs.microsoft.com/identity/access-tokens-and-id-tokens/): Microsoft-owned API access tokens are opaque to clients. A local decode must not authenticate declared client/principal/subject.

## Verification

- Initial implementation-absent test run failed by assertions; original `red-tests.txt`
  contains 34 failures because the first test class layout duplicated inherited tests.
  That layout was corrected before implementation; the final suite has no duplicate
  inherited target tests. No claim is made that 34 distinct scenarios failed.
- First implementation passed 20 tests, including all 54 binding-leaf mutation
  subcases, required-leaf omission/null, wrong origins, malformed IDs/paths,
  federation-kind mismatch, freshness/expired lease, unknown fields and canaries,
  denied/redirect/malformed/oversized/encoded service responses, cross-tenant or
  endpoint mismatch, no secret exception echo, and unchanged inputs.
- Refinement red run had 2 assertion failures: post-validation caller mutation could
  substitute a target and the post-connect transport deadline was absent.
  Bounded snapshots and socket-shutdown deadline fixed both. `refinement-red.txt` is
  retained; no live server was involved.
- Independent security review found Python `$` regex matching allowed a trailing
  newline in some identity/name/hash fields. The new control-suffix test exposed 26
  failing subcases; an independent comparison-snapshot case added one failure.
  C0/DEL string rejection and snapshots for every API fixed all 27. The failing
  receipt is `security-red.txt`.
- Final scoped command:
  `python -m unittest plugin_tests.test_target`: **24 tests passed**, zero failures,
  errors or skips (`green-tests.txt`). Tests exercise real inspection/comparison
  algorithms. HTTP tests replace the connection with a deterministic simulator;
  they are protocol/transport-contract evidence, not observed live TLS or Azure
  authorization qualification.
- At the point this workstream ran the full verifier, the shared checkout passed
  **567 tests**, zero failures/errors/skips, including core regressions. Root's final
  integrated run supersedes this point-in-time receipt. Copy: `full-verifier.json`.

## Open enterprise boundary

No input claim authenticates itself. The collector does not establish principal,
client ID, federation claims, approver identity, backend state lineage/serial,
actual effective repository configuration, writer lease or caller authorization.
Public Azure, regular storage endpoints, pinned tool versions and a restricted
literal naming subset are the only accepted target contract. Sovereign clouds,
custom/private storage origins, SAS/shared-key auth, encrypted-state readback,
native backend/provider execution and host credential adapters remain unsupported.

Network response bytes are bounded. The post-connect deadline covers HTTP headers
and body; DNS remains subject to OS resolver behavior. Enterprise deployment
requires an external supervised process deadline and trusted execution environment.
No total wall-clock guarantee is claimed by this standalone API. No untrusted native
Atmos repository or browser credential/session was evaluated.

The remaining E03 implementation is a qualified credential identity adapter and
protected evidence transport, effective native runtime inspection, state readback,
writer exclusion, and a last-moment context comparison inside the execution host.
The new APIs supply consistency and partial service facts for that boundary; they
must not replace it.
