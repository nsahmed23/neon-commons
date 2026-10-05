# Selected provider completion evidence — 2026-10-02

This is new evidence, separate from the historical `IMPLEMENTATION-REPORT.md`. The registry provider is unchanged. Production generation and provider/service qualification remain inactive. No credentials, tenant mutation, publication or installation of trust were used.

## Current results

| Result | Evidence | Boundary |
|---|---|---|
| Full pinned source and dependency acquisition succeeded | `evidence/acquisition.json`; `evidence/module-verify.txt` | Provider v1.0.0, commit `1718c946b3ae111bb44c7c1d925b3e35b708cb0a`; unmodified go.mod/go.sum; all acquired modules verified |
| Desired regressions fail against unchanged source | `evidence/completion-isolated-red/result.json` and raw Go events | 11 top-level cases fail; 24 failed nodes including subtests; no skips. Tests call actual provider helpers, SDK serializer and configured Kiota HTTP adapter |
| Candidate source behavior passes | `evidence/completion-final-green/result.json` and raw Go events | 14 top-level cases pass; 27 passing nodes; no failures/skips. Includes three new raw assignment-state cases, not present in RED because that API is new |
| Qualification-runner guards pass | `evidence/runner-green.txt` | 16 Python tests; seven new completion/integrity/oracle cases plus nine existing runner guards |
| Exact patch applies | `0002-selected-resource-preservation.patch` | `git apply --check` against the pristine complete pinned checkout succeeds |
| Published baseline native schema/HCL | `evidence/native-baseline-final/result.json` | Full schema RPC succeeds; ordinary and omitted-filter HCL accepted; observed wrapper rejected; null/future instance wrongly accepted; explicit zero filter rejected |
| Actual selected resource native RPC | `evidence/synthetic-rpc-final-green/result.json` | Separate synthetic provider Configure; import preserves exact fixture; ordinary and refresh-only saved plans exit0; 12 GETs including six assignment pages; no writes or live service |
| Actual resource native HCL matrix | `evidence/synthetic-resource-hcl-final/result.json` | All 13 cases meet expectations, including explicit zero/none and rejected zero/include/exclude; separate synthetic provider schema |
| Candidate full production-provider build / schema / HCL | See `NATIVE-STATUS.json` | Kept separate from both helper and synthetic-provider results |

The first RED constructor compilation took several minutes and compiled the real beta SDK models under the host's 8 GiB memory limit, one worker, GOGC=20 and GOMEMLIMIT=5GiB. The successful cached GREEN run uses the same dependency source/toolchain. This is not a fake SDK, AST-extracted constructor or Python reimplementation. Configured HTTP requests used the real Kiota adapter with an in-memory transport and anonymous synthetic authentication; no network service was observed.

## Implemented candidate

`labs/provider-contract/completion-manifest.json` binds every original/candidate file hash. `labs/provider-contract/completion/` contains complete modified/new Go sources with MPL-2.0 license and notice. `full-source-manifest.json` pins 5,724 complete provider build inputs (Go sources, internal assets, module files and license). The full checkout was acquired; documentation is excluded from the build-input list because it is not compiled.

1. **Settings constructor:** validates the complete settings tree before returning anything, rejects unsupported polymorphs including nested unknown/missing types, preserves original IDs instead of renumbering, populates real SDK getters, and overrides SDK serialization with the validated exact JSON. Null references, empty arrays, field values, unknown non-polymorphic observation properties, wrapper fields and array order survive. No default SDK discriminator is manufactured into the outgoing payload. The selected resource uses an error-returning constructor before mutation; legacy entrypoints and unrelated resource profiles are unchanged.
2. **Settings schema/state:** strict bounded JSON parsing rejects duplicate keys, malformed/error/incomplete envelopes, missing/duplicate IDs and null instances. Valid observed nonadjacent IDs and wrapper fields are accepted. The selected Read propagates errors before `resp.State.Set`; it never turns an error envelope into settings or reports old settings as a fresh successful observation. Exact canonicalization sorts object keys only and preserves numbers, arrays, nulls and empties. No positional secret restoration runs on the selected path.
3. **Selected GET path:** the selected resource explicitly calls the new bounded helper for its settings/assignments collections at `/deviceManagement/configurationPolicies`. It invokes the configured Kiota adapter's `Send`, retaining configured authentication, retry and transport middleware, with a bounded response handler. The old shared GET, `makeRequest` and DELETE paths are untouched. HTTP 200 is required; initial `$expand`, full returned query, same origin/path, loop limits, page/body/total/item bounds, duplicate identities and returned count consistency are enforced. Failed later pages return no partial collection. The real configured adapter is exercised while the process-global default transport is forbidden.
4. **Assignment Read wiring:** actual selected resource Read now requests the complete assignments collection through that helper, then validates every raw target/filter before changing the state set. Inclusion/exclusion and group/filter identities are retained; unsupported fields/types and duplicate tuples that would collapse distinct identities fail closed. Empty and omitted assignment configuration stay distinct when the service returns a complete empty collection.
5. **Assignment request wiring:** null assignments produce no assignment POST; unknown/invalid assignments fail before the policy mutation rather than becoming an empty or reduced array. The selected constructor emits explicit filter values, including zero and `none`, instead of silently omitting them. The policy request and assignment request remain separate effects; the misleading atomicity comment was removed. Full request bodies are no longer debug-logged by the selected constructors.

Local support bounds are 4 MiB per JSON/body, 32 MiB collection input, 128 pages, 10,000 items and a 30-second context deadline per configured request. These are engineering restrictions, not claims about Microsoft service limits. The existing resource validator separately enforces depth 20; the shared parser's defensive ceiling is 128. The configured adapter's own middleware can impose additional time/behavior limits.

## Status by requested gap

| Gap | Status | What remains |
|---|---|---|
| P01 ID/null/empty/unknown-type defects | FIXED_LOCAL for executed constructor/state/schema helper cases | Named synthetic resource RPC import/ordinary/refresh cases pass; other profiles and service roundtrip remain UNQUALIFIED |
| P01 positional secret restoration | UNSUPPORTED_PROFILE on candidate selected path | Secret setting types fail closed; identity-based secure secret handling is not implemented or certified |
| P02 selected collection transport/paging | FIXED_LOCAL within synthetic configured-adapter profile | Real configured auth/retry/redirect/cloud behavior, service snapshot completeness and other legacy helper callers are UNQUALIFIED |
| P03 assignment paging integration | FIXED_LOCAL in helper and named synthetic resource RPC cases | Actual Read wiring and two-page collection executed natively; service replacement/merge, lost responses and assignment identity semantics remain unqualified |
| P03 absent filter observations | UNSUPPORTED_PROFILE | Current Terraform tuple cannot preserve absent versus null; candidate refuses absent filter ID/mode fields rather than inventing zero/none |
| P04 native schema/HCL/config/import/plans | See `NATIVE-STATUS.json` | Native selected-resource import and no-change plans pass with test-only Configure; production provider Configure and tenant lifecycle remain unqualified |
| Registry release/provider installation | UNIMPLEMENTED / unauthorized for this session | Candidate is unpublished; production mapper unchanged |

The selected resource now creates its own assignment schema from the unchanged shared schema and replaces only filter-ID validation. Explicit zero is accepted with `none` (or its omitted default); include/exclude requires a configured non-zero GUID. Published-provider native RED rejected explicit zero; the candidate resource passes the expanded 13-case native matrix and exact explicit-zero import/no-change roundtrip. Other shared-schema callers retain their original behavior. Missing filter properties are not treated as equivalent to explicit nulls or defaults; the synthetic lifecycle fixture covers explicit actual IDs and explicit zero/none, not null-filter lifecycle semantics. Assignment IDs are used for completeness and duplicate detection; the current Terraform assignment tuple does not expose an ID attribute, so independent service identity semantics remain a release gate.

Settings arrays are deliberately not sorted by ID or renumbered. Extra observed settings fields are not removed to manufacture a no-change plan. A real service response that adds, omits, reorders or changes data can still produce drift or be refused. No independent preservation oracle or production mapper gate was weakened.

## Reproduction

Use the exact Go 1.25.8 executable and verified complete provider checkout/module cache recorded in acquisition evidence. Acquisition is separate from execution. The runner strips inherited credential environment, disables downloads, auto-toolchain selection, telemetry and cgo, verifies source and patch identities, and bounds logs/process groups.

```
python scripts/qualify-provider-contract.py --upstream CHECKOUT --go GO --module-cache CACHE --output OUT_RED --completion-profile original
python scripts/qualify-provider-contract.py --upstream CHECKOUT --go GO --module-cache CACHE --output OUT_GREEN --completion-profile patched
python scripts/qualify-provider-contract.py --upstream CHECKOUT --go GO --module-cache CACHE --output OUT_BUILD --completion-profile patched --full-build
```

An existing trusted `--build-cache` avoids recompiling the large generated SDK models. Source tests are bounded at 600 seconds; full builds at 1,800 seconds. Full builds default to one worker; the final build uses two only after the large SDK packages are cached. Native compilation uses `-buildvcs=false` because the reproducible staged inventory intentionally has no Git administrative data; source identity is bound separately by manifests. Complete provider build is not the same as schema RPC or lifecycle qualification.

Two native setup attempts are retained separately: the first incorrectly placed root `package contract` helper tests beside `package main`; the second tried VCS stamping in the inventory-only checkout. Both failed before a meaningful full compile and were repaired in the runner. They are not provider defects or qualification passes. The original no-network sandbox download failed because its proxy endpoint was unavailable; explicitly authorized scoped escalation acquired the public pinned dependencies. No host restriction was bypassed or reconfigured.

Historical receipts and the old helper patch are unchanged. The new patch applies directly to the pristine provider baseline; it is not layered on the historical `0001` patch. No commits were made by this lane. Root owns integration, archive persistence and final acceptance.

## New native baseline findings

The unchanged published v1.0.0 binary was reacquired and verified against both the current release checksum and the previously retained archive/binary digests. No new publisher-trust assertion is made; signature verification was not repeated. OpenTofu 1.10.0 is pinned by executable hash in the native validator.

Ordinary sandbox execution reproduced the unavailable native handshake. The explicitly authorized local-socket escalation succeeded without changing host restrictions. Full `GetProviderSchema` returned 9,359,177 bytes; the selected resource schema is retained. All seven HCL validation calls executed using the actual published provider. Ordinary settings and omitted filters validate; explicit zero filter GUID and include-without-filter-ID are rejected; observed wrapper fields are rejected; null and unknown setting instances are incorrectly accepted. These are native schema/ValidateResourceConfig observations, not AST extraction or lifecycle plans. No provider Configure, ImportResourceState, ReadResource, PlanResourceChange or ApplyResourceChange call is claimed.

Full public schema output remains in the execution workspace with its digest in the receipt; selected schema, all authored HCL inputs, validation outputs and diagnostics are retained in this evidence tree. Native configuration validation does not establish default ordering during PlanResourceChange.

Original exported and private typed-constructor helpers remain unchanged for other resource profiles and their tests. Only the selected resource invokes the new strict lossless entrypoint. The first complete compile exceeded its historical 600-second process bound while compiling generated SDK packages; it was resumed with the same verified cache and a separate 1,800-second full-build bound rather than treated as a terminal dependency blocker.

## Affected-caller isolation audit

Review found the shared legacy constructor/state/validator were also called by EPM, template, reusable-setting and Linux-script resources. The candidate now adds Strict APIs and wires only the selected resource to those APIs. Original legacy function bodies are byte-for-byte unchanged; the existing shared GET/DELETE files are not patched. `evidence/collateral-caller-red-green.json` shows that the initial candidate changed three shared entrypoints and the isolated candidate restores their original bodies. A Python regression verifies original bodies plus actual selected constructor/Schema/Read wiring.

The RED test adapter calls the precise entrypoints used by the original selected resource; the GREEN adapter calls the new entrypoints used by its repaired source. These adapters do not normalize input/output or replace provider behavior. Both execute real provider/SDK code and retain the same preservation assertions, with explicit error propagation and unchanged prior state required on failed observations. The complete helper suite also passes with both original legacy characterizations and the new selected-entrypoint cases; that suite remains narrower than all upstream provider tests.

## Synthetic native resource lifecycle

The separate fixture provider imports the actual final selected resource. Its provider Configure injects a real Kiota Graph client through the resource's normal Configure interface, with anonymous synthetic authentication and an in-memory transport that rejects all non-GET or unknown URLs. This is neither production provider Configure nor a live Graph test. No production authentication bypass or fixture flag was added to the patch.

OpenTofu executes schema, validation, import, state show, ordinary saved plan/show and refresh-only saved plan/show. The final authored configuration includes the explicit zero filter ID. All eight commands return0. The independent fixture oracle compares ID, name, description, platforms, technologies, scope tags, timestamps, setting count, assignment status, exact settings tree (stable ID37, wrapper, null references, empty children) and both assignment/filter tuples. Imported state, ordinary planned values and both saved refreshed snapshots match. Both plans have no effects/drift. The transport trace shows three complete Read cycles and six assignment pages, all GET.

OpenTofu 1.10.0's no-change refresh-only JSON has an empty planned-values root. The harness verifies its native `prior_state` and the saved plan's `tfstate` refreshed snapshot directly against the fixture; it does not substitute authored configuration or imported state. A Python oracle regression proves six different data losses are rejected. Two earlier harness failures are retained: missing HTTP ContentLength made the SDK read an empty policy, and the first oracle assumed refresh-only JSON always contained planned resources. Neither failure was hidden by relaxing expected state.

The scope does not include Create/Update/Delete RPC, live permissions, concurrency/snapshot guarantees, assignment replacement/merge, secret settings, null-filter lifecycle, all cloud profiles, response-loss recovery or other resource families. No successful local result activates production generation.

## Go dependency inventory

`evidence/provider-go-sbom.json` and the raw `go-list-pinned-modules.jsonstream` record all 113 acquired upstream go.mod dependency pins, each independently resolved offline by Go with Version/Sum/GoModSum checked against the acquisition ledger. Module verification passes and source go.mod/go.sum are unchanged. This is a project JSON inventory, not a claim of an SPDX/CycloneDX document or advisory scan. `go list -m -json all` was attempted offline but requires uncached historical graph metadata; that failure is retained. The inventory does not claim unselected historical graph entries. Native embedded dependencies and executable/toolchain hashes are recorded separately with build evidence.

The final synthetic native run also reproduces and repairs an empty-policy Read defect. Before the guard, a successful empty response let Import report success and continue reading collections; `evidence/synthetic-rpc-empty-policy-red` records the failed refusal assertion. The selected Read now rejects a nil base policy or missing/mismatched immutable policy identity before state mapping or collection reads. The final negative import fails with `Incomplete Policy Observation`, and its trace contains exactly one policy GET. This negative transport switch exists only in the separate synthetic provider, never in production source.

Synthetic state is also retained under explicit `imported-state-evidence.json` names. `evidence/synthetic-state-artifact-map.json` maps each original .tfstate artifact to the exact-byte JSON copy and SHA-256; the source package's existing .tfstate exclusion remains unchanged.

## Final complete provider binary

The final 12-file candidate overlay was built against all 5,724 pinned original build inputs using Go1.25.8, without changing go.mod/go.sum. `evidence/native-full-build-final/result.json` reports exit0; `evidence/native-build-provenance.json` binds the exact final manifest, patch, source inventory, toolchain and binary hashes. The648,888,462-byte Linux/AMD64 executable has SHA256 `28d3af959966dc73ef8c001e8f70b8ac7efc5c394162b51351ea8c8dfc97eb06`; its provider metadata version is `dev`, and it is unpublished. All66 embedded Go dependencies match the113-pin inventory.

The actual full binary's GetProviderSchema and all13native HCL cases pass. `evidence/native-candidate-final/result.json` and selected schema/inputs/diagnostics retain those results. The explicit-zero cases pass only with none/default-none; include/exclude still requires an actual filter GUID. Unknown/null settings fail and observed stable IDs/wrappers validate. The full schema response remains in the execution workspace with its hash in the receipt. No production provider Configure/authentication or tenant operation was performed.

Earlier build setup/time-limit failures, a superseded staging move failure and intentionally stopped single-worker build are retained as failed attempts, not provider defects or terminal blockers. The final complete build and subsequent final-source incremental build both succeeded using the verified cache; neither historical timeout nor helper results substitute for this completed native build.

## Preserved candidate archive

The separate `Microsoft365_Provider_Candidate_Linux_AMD64.zip` review artifact contains the exact final native binary, provider and dependency licenses, README/scope, SHA256SUMS, Go inventory/build provenance/native validation, and the original source archive/patch/manifests. It is outside the plugin runtime/source repository artifact. `evidence/candidate-archive-receipt.json` records exact members, size limits, every streamed member digest and outer ZIP SHA256. No extraction, installation, publication or execution occurs during archival verification. The 255,363,704-byte archive has SHA256 `85781e6a2e3b92612a61313e31f7bda039ebf009692b497c1316972b6f5465db`. All embedded dependency module roots had license/notice files, retained in the archive.

The separate fixture HCL matrix used binary `7da990a21d679b1157d34788ed18cd3e7707c344d2f2052f3605691e7aecf308` (explicit-zero schema before the final Read guard); the final fixture lifecycle used `7b4c58cc2e086643586c399b264869fde47d8336e9dc6a01adc734350d98b142`. These are explicitly separated in NATIVE-STATUS/SUMMARY. The final complete provider binary `28d3af...` independently passes the same13HCLmatrix after all source repairs.
