# Intune 0.5.1: scope and acceptance

This document identifies the current implementation and its evidence boundaries.
The accompanying exact-archive verification receipts, acceptance ledger and artifact
manifest are authoritative for delivered bytes, tests, source hashes and limitations. Historical counts under `verification/`
retain their original dates and are not current execution results.

The enterprise release gate remains blocked. Local repairs, measured performance
and successful synthetic exercises do not replace supported-host qualification,
independent organizational AppSec review, or an explicitly authorized tenant pilot.

## Implemented local workflow

The 17-stage journey connects repository discovery, complete captured inventory,
selection, preservation, Atmos resolution, generation, adoption, plan review,
approval, execution, readback, reconciliation, convergence and drift handoff.
Each stage reconstructs evidence on resume. Full modeled policy data includes
immutable identities, settings, assignments, exclusions and filters. The modeled
service's independent oracle reads raw captures and does not call the production
normalizer or serializer. Its separate CRUD/fault tests do not imply that adopting
an existing policy must rewrite it.

Actual pinned Atmos execution, native local OpenTofu fixtures and the selected
provider source tests are separately identified in receipts. A local output-only
OpenTofu resource cannot establish Microsoft365 provider RPC, import semantics,
authenticated readback or live Intune convergence. The actual Azure backend
emulator qualification similarly establishes only the recorded emulator profile;
it does not grant Azure access or demonstrate cloud identity/RBAC behavior.

## Support boundaries

| Surface | Admitted or measured scope | Explicit exclusion or remaining gate |
| --- | --- | --- |
| Runtime | Linux x86_64, CPython 3.12, exact ten hash-locked wheels | Other Python/platform wheel sets need separate qualification |
| Native tools | Current local qualification: Atmos 1.230.1 and OpenTofu 1.13.1, exact SHA-256 and artifact byte count | Atmos 1.199.0 / OpenTofu 1.10.0 retained only for legacy reproduction; neither profile establishes production acceptance |
| Provider | Pinned Microsoft365 1.0.0 source and explicitly identified unpublished repairs | Registry release, candidate source and candidate binary are distinct artifacts |
| Settings Catalog proposal | `production-1.2.0` capture adapter; Windows 10/MDM worked privacy choice; direct included/excluded groups and supported filters | See PRODUCTION-MAPPING.md for exact fields; all other families/settings remain unsupported or review-only |
| Source size | 16 MiB file bound; production capture 10,000 total JSON nodes | No truncation, weakened inventory checks or automatic policy loss to fit the budget |
| Synthetic estates | Seeded, replayable bounded estates, with measured workload sizes stated in evidence | Synthetic scale is not a tenant-scale SLA |
| Mutation | Explicitly selected laboratory operations with separately bound plan and approval | Live tenant mutation is not enabled by laboratory success |
| Host security | Tested deterministic command, approval, hardlink, process and durability controls in the stated Linux profile | Cooperative parent filesystem/host assumptions remain; no hostile-host containment claim |
| Wrappers | Bash checks and inactive PowerShell preview: actual Linux 7.6.6 literal argv and pre-emission rejection controls | No active PowerShell deployment wrapper; Windows, reparse points and Git Bash require native qualification; general PowerShell module-loading failures remain unresolved |

## Release-blocking evidence

The host rejected Unix-domain socket creation with `EPERM`; actual provider RPC
must be qualified on an admitted host. In-process resource and HTTP-transport
tests cannot replace this gate. Preserve the failed operation and rerun the
supplied RPC/lifecycle harness unchanged when that prerequisite is present.

Complete live provider/backend identity integration, credential boundaries,
service behavior, native host coverage, and the required AppSec/pilot evidence
remain separately gated. Credible unexplained receipt/state durability findings
remain open until a causal investigation and independent regression close them;
a successful repetition alone does not do so. The delivery's findings ledger is
authoritative for each finding's precise status and evidence.

Security qualification covers the 16 terminal attack families with scoped
assertions, negative controls and visible gaps. Scanner candidates are not
automatically confirmed vulnerabilities, and passing scanner or model output is
not a containment or security-certification result.

Use OPERATIONS-EPOCH.md for installation checks, monitoring, revocation,
uncertain-outcome recovery, incident response, and required pilot records. A
missing mandatory assertion is never converted to a pass by an aggregate count.

The upgraded native tool profile retains the closed inert Atmos repository and resource-free local OpenTofu fixture boundaries. General provider/resource plan review is not widened by output-only version admission. Official release checksums and signatures, prior rejected compatibility attempts, residual advisory matches, and new native replay evidence are retained under `evidence/epoch-20261004/toolchain-upgrade` in the continuation bundle. Existing timings remain tied to their measured source revision; no upgraded native-tool performance claim is inferred.

Current provider source qualification separately runs the actual resource methods against an injected stateful HTTP transport: 12 top-level groups and 55 pass events including subtests. These are not provider RPC or live service tests. Two full updated-binary build attempts failed from exhausted disk space. The third attempt successfully built the complete provider from the same source, with `-ldflags=-s -w` removing symbol/DWARF information and no source-feature reduction. It returned zero with unchanged source; the 410,960,034-byte binary has SHA-256 `415097131c64a47c8435ce9528d050382996cfa4bed38d0960548f160a0b0dd3`. The exact rebuilt binary was re-probed with OpenTofu 1.13.1. Default initialization passed, while schema and validation failed with generic provider-command errors; those failures remain retained. A separate explicit no-credential `TF_LOG_PROVIDER=TRACE` diagnostic passed initialization and captured actual Unix socket `EPERM` for schema and validation, which are classified as blocked in that diagnostic only. The original process controls were unchanged. Six lab observation/trace tests pass; they do not qualify provider RPC. Stripped debug information limits binary diagnostics. The retained manifests distinguish 5,724 staged files and five added candidate patch files. A build or Read-method comparison cannot substitute for actual native import and second-plan convergence.

The PowerShell smart-apostrophe repair has static fail-closed rejection and permitted ordinary-literal Linux execution evidence. An automatic approval review rejected the active malicious after-payload replay; it remains unverified, and the earlier 99-case passing corpus does not qualify the repaired revision. Automatic review also rejected the requested current-native performance follow-up before timing began. Older timing profiles retain their original source and binary identities. Neither restriction is treated as a pass.

All 3,548 original manifest payload hashes remain unchanged in the final input recheck, but an extra generated Python cache file reappeared in the extracted original tree. The exact-file-set check is therefore false. Preserve that anomaly and the supplied original ZIP; do not claim the loose tree was untouched.

The final native smoke evidence is `provider-lifecycle/native-smoke-final.json` and `provider-lifecycle/native-smoke-trace.json` under the continuation evidence epoch. Neither run passed provider schema validation or resource lifecycle. The trace profile records its sole diagnostic environment change and uses no credentials; it is a local diagnostic procedure, not guidance to enable sensitive logging in an authenticated tenant session.
