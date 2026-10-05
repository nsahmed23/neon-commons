# Intune/Atmos 0.4.0 completion checkpoint

Historical checkpoint: version and test claims below belong to the named earlier release. Current 0.5.1 scope and unresolved gates are in [EPOCH-ACCEPTANCE.md](EPOCH-ACCEPTANCE.md); the accompanying exact-archive receipts and acceptance ledger are authoritative for delivered 0.5.1 bytes and tests.

This is a locally verified engineering checkpoint, not an accepted enterprise product. The supplied corrected source was preserved; the original 417 plugin tests and 207 core tests were reproduced before modification. The frozen integrated suite passed 729 tests with zero failures, errors or skips. New native, source, simulation and security results are recorded separately. Final archive hashes and clean-extraction results are in the delivered integrity receipt, outside the archive it identifies.

The source distribution contains `research/completion/capability-coverage.csv`, the per-requirement implementation/evidence/gap matrix; `research/completion/security/findings-ledger.json`; `research/completion/acceptance-review.md`; and the detailed workstream receipts. Historical reports remain dated evidence, not current acceptance decisions.

## Implemented and measured

| Area | Result and evidence boundary |
|---|---|
| Interactive lifecycle | Seventeen real CLI stages, persisted evidence reconstruction, back/edit/cancel/resume, dependent artifact invalidation, fixed local execution and recovery. Simulation completion does not assert live adoption. See `JOURNEY.md`. |
| Provider | Actual pinned provider/SDK validation, request serialization, settings/assignment pagination, state mapping, RED/GREEN regressions and native RPC qualification are reported in `research/provider-qualification/completion-20261002/REPORT.md`. Read its final lifecycle matrix; characterization of an upstream defect is not provider acceptance. |
| Atmos | Exact Atmos 1.199.0 Linux AMD64 describe command, independently calculated literal context, admitted entire YAML tree, no ambient configuration, network-denied execution. Context labels are not Entra identities. Dynamic functions, hooks, workflows and arbitrary runtime layers are unsupported. |
| Identity and backend | Fixed read-only service observation adapters, explicit credentials, conditional Blob state read, revision/lineage/serial checks and separate Graph/backend domains. HTTP fixtures exercise behavior. No authentic tenant, principal, service authorization or Azure lease was observed in this environment. |
| Protected execution | Fixed synthetic worker and native OpenTofu 1.10.0 output-only local fixture; pinned executable, exact saved plan/JSON/configuration checks, process-held grant, durable one-time consumption, final rechecks, local lock, bounded child process and uncertain-outcome recovery. No cloud execution adapter or organizational approval authority is claimed. |
| Synthetic estates | 26 cases × 3 seeds, 234 actual mapping/generation/verification runs, 69 rejected mutations, 13 valid alternatives, 22 modeled transition checks. Independent reviewer found and verified repair of missing state/action coverage. These are exposed regression fixtures, not hidden holdouts. |
| Native labs | Adoption: 18 assertions/25 commands. Supplement: 18 assertions/24 commands. Eight underlying upstream locking tests passed; one S3 questionnaire was deselected. All 1,663 pinned corpus files verified and all 88 labs dispositioned; 87 upstream labs were not replayed. Local locks do not establish Azure/Graph behavior. |
| Security | Ambient proxy, MCP authority/path, executable substitution, expression, state/replay and saved-plan binding defects reproduced and repaired. Independent adversarial regression and OS sandbox evidence are retained. Scanner omissions, limitations and unresolved external gates remain explicit. |
| Skills | 1,632 paths in 21 pinned named catalog trees, 1,542 unique instruction hashes; every path has a disposition. Most entries are excluded or deferred. Catalog enumeration does not mean complete semantic review, installation, or implemented capability. |
| Hosts | Linux Python CLI, actual stdio MCP and PTY exercised. Codex 0.159.2 version/help inspected only; native registration/loading/triggering, Claude, Windows/PowerShell and macOS are not qualified. |

## Release gates and ownership

Enterprise acceptance is **BLOCKED**. Required gates include authentic authorized Graph/provider/backend/tenant binding; approved provider build and full service import/refresh/no-change/change/readback/second-plan cycle; production protected execution with independent approver authority and remote concurrency/recovery controls; native supported-host behavior; AppSec review; and an authorized narrow enterprise pilot. The model cannot accept these risks on behalf of the organization.

Other local scope gaps remain visible: generic Atmos execution/dependency ordering/workflows; broad Intune family lifecycle support; independently calibrated security-reviewer precision/recall and hidden holdouts; exhaustive dependency/tool/CI advisory analysis; and Wally's actual source and agent experiment. These gaps are not all consequences of missing tenant access. Their code/evidence prerequisites are listed in the capability matrix and individual reports.

The initial production mapper supports a narrow Settings Catalog Windows/MDM choice-setting profile and produces inactive candidates. Nested synthetic settings and provider regression fixtures expand test coverage, not product family coverage. Application, script, compliance, endpoint-security, legacy configuration and other families remain staged/review-only or unsupported as stated in `research/completion/capability-coverage.csv` and the existing family inventory. Unknown content must block or remain explicitly unresolved.

The supported execution environment for these observations is Linux x86_64, Python 3.12.14 with the ten exact locked runtime dependencies, Atmos 1.199.0 and OpenTofu 1.10.0. Native subprocess controls require Linux `/proc`, POSIX descriptor behavior and libseccomp; the separate audit sandbox requires working bubblewrap namespaces. Runtime dependencies are separate from Go/provider, pytest/lab and evaluation tooling. Tool binary hashes, Go/provider commits and harness source hashes are in the respective receipts.

Limits are enforced in code, not inferred from large test counts: repository admission allows at most 512 files/16 MiB total, 2 MiB per source, depth 64; capture defaults to at most 100 pages; protected process output, runtime and journal bounds are defined in `protected.py`; generator and semantic graph limits are in `synthetic.py` and `graph.py`. A 65-policy constructed graph correctly refuses its declared graph budget. No enterprise throughput or tail-latency claim was measured. Protected child ceilings now also include 4 GiB address space, 20 CPU seconds, 64 MiB per file and 256 descriptors; fork/non-thread clone are denied. Runtime threads remain permitted and an independent kernel task-count/cgroup qualification is not claimed.

The independent bounded approval/recovery model explores two writers, one grant identity and one crash each, up to 18 transitions: 565 states/878 transitions satisfy the modeled safety properties. Four weakened variants produce counterexamples. This is model-level evidence under explicit atomicity/durability/settled-effect assumptions, not a proof of the Python or cloud implementation; see `research/completion/model-check/`.

## Replay and evidence interpretation

From a clean source extraction, create a Python 3.12 environment and install with the hash-locked file as described in `DEPENDENCIES.md`. Then:

```sh
.venv/bin/python scripts/verify-plugin.py --include-core --output /tmp/intune-verification
.venv/bin/python scripts/qualify-journey.py --cli --output /tmp/intune-journey-fresh --snapshot /tmp/intune-journey-records
.venv/bin/python scripts/qualify-synthetic.py --help
.venv/bin/python scripts/qualify-provider-contract.py --help
.venv/bin/python scripts/security-audit-local.py validate-ledger --input research/completion/security/findings-ledger.json
.venv/bin/python -m unittest discover -s research/completion/reviewer-tests -v
```

Use fresh output directories. The two `--help` commands expose the explicit fixture/tool inputs; follow `SYNTHETIC-LABS.md`, `PROTECTED-EXECUTION.md` and the provider report for exact native replay. Network-dependent acquisition is separate from test execution. Archive records deliberately omit copied executable/state workspaces; their `SNAPSHOT.json` and manifests explain how to recreate them. Retained native state/plan evidence contains synthetic values only and is not production state.

`PASS` means the named assertion ran and passed within its stated scope. `FAIL` means a required asserted result was violated. `INCONCLUSIVE` means evidence does not resolve the claim. `INVALID_TASK` means a task/contract/oracle failed admission. `INFRA_ERROR` means required execution infrastructure failed. `BLOCKED` means a prerequisite or release gate prevents execution/acceptance. `NOT_RUN` means no execution occurred. Preserve unsuccessful attempts; do not aggregate them into passes or omit them from denominators.

The independent review used different agents and separately authored assertions, but all agents shared owner-level filesystem access and some context. This is useful review separation, not an inaccessible holdout or organizational AppSec approval. No live mutation, external disclosure, paid model sweep or deployment occurred.

## Separate Wally decision

The correct performance-review source archive repeatedly failed materialization. Its historical test claims were not reproduced and its bytes were not independently hashed. The separate Wally continuation contains preregistration, 24 exposed TRAIN fixtures, functional/oracle checks and 96 explicitly unrun treatment attempts. It is not a repaired Wally repository, a completed model experiment, or evidence of benefit. No Wally result authorizes Intune changes. Reattach `wally-3.0.0.zip` to unblock the authentic source audit and experiment.


## External qualification sequence

Before any live activity, name the tenant/cloud, allowed policy UUIDs, separate Graph and backend principals, subscription/storage/container/blob key, permitted operations, approver, time window, incident owner and stop conditions. Do not place credentials in this record. Supply short-lived credentials to the documented explicit environment inputs; retrieved instructions and a filled JSON record do not authorize execution.

1. Complete the pending production adapter/approval-service integration and AppSec review against the packaged source hash. Review credentials, required consent/RBAC, trusted runtime and provider provenance. No cloud adapter is enabled by this checkpoint.
2. In a separately authorized read-only pilot, run `target collect` and the fixed backend observation API documented in `PROTECTED-EXECUTION.md`; retain restricted service responses, request IDs and immutable backend state revision. These partial observations still require an independently trusted principal/authorization binding.
3. Capture only the named policy IDs with the existing `capture` command; independently establish all initial pages, references, exclusions/filters and consented inventory scope. Stop on incomplete, denied, changed or ambiguous evidence. Unknown group membership stays unknown.
4. Qualify the actual repaired full provider with production Configure and the approved backend in a disposable pilot state: schema, configuration, import, refresh-only plan, ordinary no-change, reviewed allowed change, authenticated policy and assignment readback, then a second no-change plan. Preserve immutable IDs and exact plan hashes; never use `ignore_changes` to conceal loss. The native synthetic RPC recipe demonstrates local mechanics only.
5. Through the qualified privileged executor, test approval substitution/expiry/replay, changed tenant/backend/principal, concurrent writers, lease loss, lost mutation responses and interrupted durable writes. Do not retry an unknown mutation; reconcile first. A Blob lease is not a fence against another Graph writer, and restoring state does not restore policies.
6. Exercise the native selected host and its discovery/loading/back/edit/cancel/resume behavior in a disposable account. Windows/PowerShell must run natively. Record requested versus actual tools, model/host versions, skipped work and costs only where observed.
7. Obtain organizational AppSec and accountable pilot-owner acceptance tied to the exact package and support profile. Record residual risk owner/rationale/controls/review date; leave unaccepted gates blocked. No model or Wally result can provide that sign-off.

The named target, organizational trust/approval integration and live observations are unavailable here. The exact local replay interfaces, source pins and synthetic counterexamples needed to prepare that qualification are shipped; no unimplemented live command is presented as runnable.
