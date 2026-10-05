# Intune Workbench — 0.7.0 connected observation candidate

This candidate connects captured policy observations, persistent per-collection history, typed reference comparisons, policy-specific device/workflow evidence, and a bounded local collection scheduler. It includes the independently qualified process-cleanup repair from 0.6.2 and the separately tested terminal-checker correction. See [commands, evidence meanings and remaining limits](docs/WORKBENCH.md). Exact artifact receipts determine qualification; older totals below remain historical. Production execution and organizational approval remain blocked.

# Intune Workbench — 0.6.1 process cleanup candidate

This milestone repairs bounded descendant cleanup in the local and provider supervisors. Its exact source, packages and new qualification are tracked separately from the preserved 0.6.0 failure. Platform and organizational approval remain incomplete.

# Intune Workbench — 0.6.0 local engineering candidate

This continuation adds persistent inspection/history, closed-terminal synthetic collection, health/freshness and bounded maintenance using the existing engine and service model. Start with [Workbench commands and limits](docs/WORKBENCH.md). Qualification evidence for this source is separate from the preserved 0.5.1 results below. **Platform qualification and enterprise approval remain incomplete.** No cloud execution authority is added.

# Intune IaC plugin — 0.5.1 engineering epoch

Current release decision: **enterprise acceptance remains BLOCKED**. Version 0.5.1 adds a stateful modeled Intune service, independent semantic preservation checks, complete multi-policy journey data, native Atmos evidence, stronger file/process/durability controls, and new qualification harnesses. See [current scope and acceptance](docs/EPOCH-ACCEPTANCE.md), [connected journey](docs/JOURNEY.md), and [operations and external gates](docs/OPERATIONS-EPOCH.md). The older version descriptions and verification counts below are historical; they do not establish current acceptance. The accompanying exact-archive verification receipts and acceptance ledger are authoritative for the delivered bytes and final tests; [verification history](RELEASE-VERIFICATION.md) does not assert a current final test total.

The product is a terminal wizard for adopting an existing Intune estate into Git-managed configuration. Atmos resolves the repository configuration, OpenTofu plans and manages state, and the Microsoft365 provider supplies the supported resource lifecycle. The local modeled service exists to qualify workflow and failure handling. It does not authenticate a tenant or qualify production mutation. Wally is a separate read-only performance reviewer and grants no execution authority.

A runnable local assistant for reviewing Settings Catalog captures, inspecting Intune and Atmos relationships, and generating independently checked reference projects. It includes an interactive wizard, a fixed action runner with receipts, a typed graph, a read-only Graph collector, an optional CLM judge adapter, and CLI/MCP entry points.

This development release adds repository discovery, source-bound literal Atmos resolution, a repository-first wizard, effective structural graph relationships, and a separate production capture mapping path. A supported plugin capture produces inactive provider candidate files; unknown exporters and unsupported content remain review cases. Active reference generation retains its synthetic scope. A completed local wizard does not establish provider or tenant qualification.

Version 0.3.0 adds a receipt-backed cohort wizard, strict target binding and optional GET-only service observations, actual OpenTofu JSON plan review, local operation/reconciliation simulation, dependency hash locks, and security repairs. Actual upstream provider/SDK tests exposed additional defects; a tested candidate helper patch is supplied in the source release, without changing the published provider binary. Native local Atmos/OpenTofu labs remain available in the source distribution.

This remains an engineering alpha. The [enterprise production goal](docs/ENTERPRISE-GOAL.md) is open, and the [acceptance matrix](docs/PRODUCT-STATUS.md) distinguishes implementation from qualification.


The 0.4.0 completion checkpoint adds a 17-stage lifecycle journey, a seeded synthetic estate generator with independent corruption checks, a pinned native Atmos comparator, explicit MCP filesystem capabilities, and protected local saved-plan execution with durable recovery evidence. The full provider repair and native qualification receipts are retained separately from simulated Graph behavior. See [historical 0.4.0 acceptance](docs/COMPLETION-ACCEPTANCE.md), [complete journey](docs/JOURNEY.md), and [security assurance](docs/SECURITY-ASSURANCE.md). Production Intune execution remains gated; the native execution slice is a fixed local output-only fixture.

To exercise the complete simulated operator route with a fresh session:

```sh
.venv/bin/python scripts/intune-iac.py wizard --journey --journey-mode simulation --session ./journey.json --input examples/supported/input/export.json --context examples/context.json --output ./journey-output
```

`--journey-mode live` constructs review evidence and stops at unmet production gates. Resume without changing the saved mode; changed dependencies invalidate downstream evidence. The read-only Wally evaluation is a separate project and grants no Intune permissions.


## Start

The qualified dependency wheel set is Linux x86_64 with Python 3.12 in a project virtual environment. See [dependency integrity](docs/DEPENDENCIES.md) for offline acquisition and verification. From the extracted plugin directory:

```sh
python3 -m venv .venv
.venv/bin/python -m pip --isolated install --require-hashes --only-binary :all: -r requirements-runtime-linux-x86_64-cp312.lock
.venv/bin/python scripts/intune-iac.py doctor
.venv/bin/python scripts/intune-iac.py wizard --session ./session.json --input examples/supported/input/export.json --context examples/context.json --output ./generated
```

For cohort selection and partial generation, start a separate session with `wizard --guided` and the same input/context/output flags; see [the guided flow](docs/WORKFLOW.md). Legacy sessions retain their original route.

At the preview, enter `generate`; at review, enter `finish`. `save` suspends, and the same command resumes. Use `back`, `edit source`, `edit context`, `edit output`, or `select <policy UUID>` to change a decision. Source and output changes invalidate saved progress. Existing user-edited output is preserved.

To start from an existing Atmos repository and captured export without preparing context JSON:

```sh
python scripts/intune-iac.py repository inspect --root /absolute/path/repository
python scripts/intune-iac.py wizard --session ./session.json --repo /absolute/path/repository --input ./capture/export.json --output ./candidate
```

Select the physical stack manifest, component, and captured policy UUID. The wizard records target intent and reconstructs it on resume. Repository edits invalidate the previous generated result. Dynamic Atmos features produce explicit blockers; see [supported repository semantics](docs/REPOSITORY.md). Capture handling and its remaining provider restrictions are documented in [production mapping](docs/PRODUCTION-MAPPING.md).

On Windows, the virtual environment interpreter is `.venv\Scripts\python.exe`. Native Windows/PowerShell qualification has not been performed.

The launcher resolves its package from its own location, so it also works from another directory with an absolute script path. Plugin loading never installs dependencies automatically.

## Automation

```sh
python scripts/intune-iac.py inspect --input examples/supported/input/export.json --context examples/context.json
python scripts/intune-iac.py generate --input examples/supported/input/export.json --context examples/context.json --output ./generated --state-dir ./attempts
python scripts/intune-iac.py verify --input examples/supported/input/export.json --context examples/context.json --output ./generated
python scripts/intune-iac.py graph build --input examples/supported/input/export.json --context examples/context.json --output ./relationships.json --state-dir ./attempts
python scripts/intune-iac.py graph query --graph ./relationships.json --query assignments
python scripts/intune-iac.py action list
```

Use the virtual environment interpreter in place of `python` if it is not activated. `action preview` binds a proposal to current input bytes without writing files or dispatching an adapter. `action run` executes only one of the registered local operations. No command body or arbitrary shell action is accepted. Unknown write outcomes retain a target lock until inspected.

Exit codes: 0 successful local result; 2 blocked, partial or unavailable capability; 3 invalid request or failed/uncertain operation; 4 output conflict or held simulation lock; 5 missing dependencies; 130 interruption. Wizard completion reports local progress only. A successfully written review artifact can still describe a blocked mapping.

## Capabilities and limits

| Capability | Implemented behavior | Qualification boundary |
| --- | --- | --- |
| Wizard | Repository stack/component/policy selection or prepared context; inspect, preview, generate, review, back/edit/select, save/resume | Rechecks repository, source, context and output; no deployment approval |
| Graph | Scoped policy/setting/assignment/reference identities, provenance, coverage and fixed queries | No invented group membership or effective cohort |
| Atmos | Literal ordered imports, inheritance and supported overrides with value origins; separate effective graph facts | Documented subset only; dynamic functions and unsupported configuration block resolution |
| Runner | Typed local registry plus disposable two-facet operation simulation, write-ahead journal and independent reconciliation | No production import/apply adapter |
| Target | Strict 54-field binding and optional fixed Azure/Graph GET observations | Supplied principal/state/writer/approval remain unverified |
| Plan review | Cross-check prior state, planned values, changes, outputs and unknown effects | Offline OpenTofu1.10 JSON review cannot approve execution |
| Capture | Public Graph beta GET paging with explicit token input, restricted raw pages and honest envelope | Live API not exercised here; tenant is caller asserted |
| CLM | Real HTTP protocol adapter, pinned configuration, bounded input and validated probabilities | Optional service; advisory; learned accuracy/latency unmeasured |
| Generation | Synthetic reference output plus inactive `.tf.txt` candidates from the known production capture adapter | Bounded setting mapping; provider-backed no-change adoption unqualified |
| Host package | Portable, Codex and Claude manifests plus operational skill | Native host load and behavioral benchmark unqualified |
| MCP | Local stdio tools with validated arguments | Subprocess protocol tested; host registration is explicit |

## Details

- [Host installation](docs/HOSTS.md)
- [Wizard](docs/WIZARD.md) and [cohort workflow](docs/WORKFLOW.md)
- [Target evidence](docs/TARGET.md) and [execution/reconciliation](docs/EXECUTION.md)
- [Dependency integrity](docs/DEPENDENCIES.md)
- [Validation CI](docs/CI.md) and [enterprise execution ledger](docs/ENTERPRISE-EXECUTION-LEDGER.md)
- [Relationships and Atmos](docs/GRAPH.md)
- [Repository discovery and resolution](docs/REPOSITORY.md)
- [Production capture mapping](docs/PRODUCTION-MAPPING.md)
- [Action runner and recovery](docs/RUNNER.md)
- [Real Graph capture](docs/CAPTURE.md)
- [CLM setup](docs/CLM.md)
- [MCP setup](docs/MCP.md)
- [Release evidence](RELEASE-VERIFICATION.md)
- [Data handling](docs/DATA-HANDLING.md)

Runtime and source/evaluation distributions are separate. The runtime excludes historical research, test answers and upstream repository copies. The source distribution retains the repaired reference tests and implementation history documents. See THIRD-PARTY-NOTICES.md for provenance; upstream Google Knowledge Catalog and CLM implementations are not vendored into this plugin.
