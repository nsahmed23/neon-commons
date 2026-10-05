# Intune Workbench: Technical Execution Handoff

**Audience:** ChatGPT Work / Codex, GPT-6 Sol or Astra at the selected effort level  
**Prepared:** 2026-10-04  
**Document status:** Consolidated continuation specification reconciled to the supplied Work-session transcript and open-source qualification dossier; preserves the original executed offline reference  
**Scope:** Terminal-first Intune adoption, maintenance, history, monitoring, GitHub Actions/Azure integration, and Wally-assisted engineering

## 0. Start here: execution directive

Continue the existing project. Read its applicable `AGENTS.md`, execution directives, source manifests, and acceptance ledger first. Preserve existing fixes and valid evidence. Reconcile this document against the latest workspace rather than overwriting a newer implementation with these examples.

The required product is a persistent engineering workbench for authorized endpoint/platform engineers:

> Understand existing Intune configuration, preserve it during IaC adoption, prepare company-authorized changes, observe deployments, investigate discrepancies, and maintain configuration through a visual terminal workflow.

Complete all useful local implementation and qualification. Missing external credentials must not stop offline UI, history, policy semantics, synthetic integration, or failure testing. External deployment, enrollment, credential provisioning, and paid resources require the applicable authorization. Do not weaken an acceptance gate to manufacture a successful release.

This document does **not** authorize production changes. The embedded code never contacts a service. Its local approval file is deliberately synthetic and is not a security authority.

### 0.1 What is executable versus proposed

| Label | Meaning |
|---|---|
| Executed reference | Appendix A's standard-library Python lab was run when this document was prepared; receipt is in section 18 |
| Command example | Exact shell syntax to run a named tool; installed version, scope, and prerequisites must be checked |
| Workflow template | Authored YAML requiring repository review and native workflow testing |
| Integration contract | Interface the receiving agent must implement or map to existing code; not a claim that a CLI already exists |
| Reported evidence | Results transcribed from another work session; inspect original artifacts before accepting |
| External gate | Requires a supported host, actual GitHub service, or authorized Azure/Intune environment |

Do not introduce invented `intune-iac` subcommands as if already implemented. Find the real CLI, use its help and existing runbooks, and publish a command mapping. The only new commands guaranteed by this document are those in Appendix A.

### 0.2 Three independent finish lines

1. **Laboratory complete:** supported product journeys work end to end with explicit synthetic service data.
2. **Platform qualified:** supported hosts and actual GitHub/Azure/Intune paths have been exercised.
3. **Production approved:** the organization accepts security, permissions, operations, support, and pilot evidence.

Never collapse these labels into “production-ready.”

The new research decisions and execution corrections in Appendix C govern tool selection and integration. Section 19 is the consolidated continuation instruction. No additional broad research cycle is required before repository reconciliation and useful local implementation.

## 1. Baseline reconciliation

**Latest update:** reconciled against the user's merged 32-screenshot Work-session transcript, ending with successful archive reconstruction checks and an interrupted final response. The transcript is secondary evidence. This document does not claim direct inspection of that other workspace or its final artifacts.

### 1.1 Latest reported candidate state — supersedes earlier status

The final provider binary reportedly built successfully from unchanged final source. Describe it as a **built, integrity-verified candidate with resource-method evidence**, pending artifact reconciliation; native RPC and production qualification remain separate. The exact source ZIP finished with **967 passes, zero failures/errors, and one explicit required host-prerequisite skip**. The strict release result remains unsuccessful. Do not restart compilation or repeat completed repairs solely because earlier instructions describe them as pending.

| Area | Latest reported result | Required continuation |
|---|---|---|
| Actual provider resource methods | 55 named checks across 12 lifecycle groups; assignment-clearing regressions failed before repair and passed afterward | Preserve source/harness/toolchain linkage and exact receipts; these are not provider RPC tests |
| Full provider build | Successful final binary; digest recorded; both disk-limited failed attempts retained | Locate the final binary and build receipt; do not rebuild without a relevant change or evidence gap |
| Native provider RPC | Binary installs into isolated OpenTofu fixture; generic handshake failure followed by diagnostic replay showing Unix socket creation denied with EPERM | Keep original failure and diagnostic evidence separately; rerun the exact binary on an authorized compatible host |
| Intune ZIPs | Integrity and clean-extraction checks passed; extracted runtime passed six functional checks | Deliver the exact tested archives and identify their digests |
| Exact source ZIP suite | 967 passes, zero failures/errors, one required skip | Supersedes the earlier 947-pass result for this artifact; do not convert skip into acceptance |
| Reproducibility | Source/runtime ZIPs reportedly rebuild byte-for-byte from clean extraction | Retain rebuild commands and comparison receipts |
| Independent package review | 23 Intune archive checks and 19 provider binary archive checks passed | Associate each review with the archive actually delivered |
| Provider distribution | Build command/source linkage and licenses for 66 runtime modules included | Preserve dependency and license inventory with artifact provenance |
| PowerShell | Linux assertions followed by Unicode quote repairs and review | Locate final packaged-revision repair evidence; native Windows remains a separate gate |
| Vulnerability analysis | Symbol extraction failed; function-shaped results retained as advisory matches | Do not infer function reachability or a clean security result |
| Workspace integrity | Original uploaded ZIP and 3,548 declared payload hashes intact; historical extra file causes loose-tree failure; cache reappearance unresolved | Keep archive integrity distinct from loose-tree/workspace durability; retain findings and narrow reproductions |
| Interruption evaluator | One script omitted from tested source ZIP; exact bytes and reconstruction instructions supplied separately | Verify supplement hashes and replay path without silently modifying the already-tested ZIP |
| Wally | 87 of 96 reviews completed, nine timeouts, no demonstrated benefit; no candidate promoted | Preserve this result; Wally remains optional and must not block product delivery |
| Handoff | Final response interrupted after reconstruction work | Confirm final evidence index, continuation package, and saved deliverables; the UI error alone does not establish artifact failure |

**Current position:** local candidate closure (M1) is substantially demonstrated by reported evidence, with final delivery confirmation outstanding. The transcript does not demonstrate completion of connected maintenance, native GitHub delivery, persistent dictionary/relationship/history views, or scheduled fleet operations (M2–M5). Enterprise qualification (M6) remains blocked by the applicable host, durability, security-review, and tenant/device-pilot gates.

### 1.2 Earlier baseline — retained as historical context

The earlier reported continuation included 947 passing tests and one required host-prerequisite skip, semantic-model repairs, native-tool exercises, Azure-backend emulator tests, and provider lifecycle repairs. These are **reported**, not independently revalidated by this handoff.

| Area | Reported progress | Receiving-agent obligation |
|---|---|---|
| Preservation | Settings/targeting replaced hash-only state; bool/int, pagination, multi-policy selection defects repaired | Inspect complete fixture values and independent preservation checks |
| Navigation | Back/cancel/resume/interruption/fresh approval/readback | Confirm the connected user journey, not just isolated methods |
| Atmos/OpenTofu | Saved-plan execution and no-change second plan | Record actual resource/provider/backend and tool digests |
| Provider | Missing-ID, partial-create, assignment, incomplete-readback repairs | Reconcile final regression results with rebuilt binary |
| Backend | Azurite contention/restart/convergence | Keep emulator and Azure results separate |
| Terminal | PTY timings, cancellation, memory, PowerShell checks | Resolve later Unicode-quote findings; Linux PowerShell is not Windows qualification |
| Release | Required prerequisite skip remains | Keep strict gate unsuccessful until fulfilled |
| Wally | Real comparisons; no established candidate advantage | Measure usefulness, do not assume it |

### 1.3 Resume from completed work

1. Locate the latest `CHECKPOINT.md`, delivery/results documents, release manifests, acceptance ledger, and packaging receipts. Use actual paths discovered in that workspace.
2. Confirm which exact archives are already saved and tested, including the evaluator supplement. Finish the interrupted delivery before initiating another broad implementation cycle.
3. Verify that source, binary, test harness, dependency pins, and delivered artifact digests agree. Reuse valid existing evidence; rerun only when a relevant change or unresolved discrepancy requires it.
4. Keep blocked native RPC and platform gates explicit. A compatible execution host is required; do not bypass this host's execution restrictions.
5. Preserve the current engineering engine and advance the user-facing maintenance journey described in sections 4–11.

The 11-case reference lab in Appendix A is educational scaffolding and a source of contract examples. It does not replace the project's existing implementation, add 11 passes to its suite, or qualify that implementation. Likewise, adopting dsoxlab is optional: the project already exercises observable state through resource methods, extracted-runtime checks, and archive reconstruction. Add a framework only when it closes a named gap.

Create/update a ledger with columns:

```csv
requirement_id,description,status,evidence_class,source_revision,artifact_sha256,test_id,result_path,environment,limitation,next_action
```

Allowed status values: `NOT_STARTED`, `IMPLEMENTED`, `PASS`, `FAIL`, `BLOCKED`, `UNSUPPORTED`, `NOT_APPLICABLE`. A `PASS` always has a stated scope. A required blocked/skipped case cannot satisfy a release gate. `NOT_APPLICABLE` requires a reason and scope decision.

### Runbook R01 — inspect without executing unknown content

**Prerequisites:** extracted, trusted working copy; no credentials required. **Effects:** reads only.

Bash:

```bash
pwd
rg --files -g 'AGENTS.md' -g '*ACCEPTANCE*' -g '*MANIFEST*' -g '*receipt*' -g 'pyproject.toml' -g 'package.json' -g 'go.mod'
git status --short
git rev-parse HEAD
python3 --version
```

PowerShell:

```powershell
Get-Location
rg --files -g 'AGENTS.md' -g '*ACCEPTANCE*' -g '*MANIFEST*' -g '*receipt*' -g 'pyproject.toml' -g 'package.json' -g 'go.mod'
git status --short
git rev-parse HEAD
python --version
```

A source ZIP may have no Git metadata. Record that fact and use its verified manifest; do not invent a revision. Read discovered instructions before running tests: native IaC tests may create infrastructure. Verify downloaded archives against authoritative expected digests and safe extraction rules before executing their contents.

**Output:** reconciled baseline ledger and an exact list of commands safe to run locally.

## 2. Responsibilities and trust boundaries

Managed changes follow: terminal → GitHub review/Actions → Atmos → OpenTofu → qualified provider → Graph → Intune.

| Component | Owns | Must not become |
|---|---|---|
| Git | Desired configuration, reviewed history | Store for tokens, state, or unrestricted plans |
| Atmos | Effective stack/component orchestration | An excuse to assume engine/provider parity |
| OpenTofu | Plan and managed-resource state | Endpoint success authority |
| Provider | Qualified resource lifecycle | Universal Graph lifecycle guarantee |
| Graph reader | Authorized discovery/readback/report retrieval | A second configuration writer |
| Project database | Observations, lineage, decisions, history | Competing desired-state controller |
| Artifact storage | Protected captures, plans, receipts | Public CI attachment bucket |
| TUI | Interaction, explanation, status | Authorization boundary |
| AI | Optional explanation and assistance | Credential holder or permission authority |
| Wally | Development review and improvement suggestions | Mandatory runtime dependency |

One declared writer per object and assignment collection. A user possessing a credential does not establish the correctness of target, operation, approval, or artifact. Company credential issuance is retained; post-issuance handling remains a product responsibility.

Adoption means representing existing identity and behavior. Functional cleanup is separate. Preserving a policy's settings while dropping an exclusion is an adoption failure.

## 3. Repository layout and integration contracts

Respect an existing valid repository layout. The following is a suggested development structure, not a mandate to reorganize it:

```text
workbench/
  engine/                  # reuse current engine rather than rewriting it
  terminal/                # presentation client over typed operations/events
  adapters/                # Graph, provider, GitHub, source-export formats
  contracts/               # versioned schemas
  lab/                     # synthetic services and fixtures
  tests/                   # independent assertions and protected holdouts
  scripts/                 # shared local and CI entrypoints
  .github/workflows/       # repository-native delivery
  docs/runbooks/
  evidence/                # sanitized local evidence; protected elsewhere as needed
```

### 3.1 Typed operation example

This is a proposed contract. It contains no credential values.

```json
{
  "schema_version": "1",
  "operation_id": "synthetic-operation-001",
  "kind": "PLAN_REVIEW",
  "effect_class": "PLAN_WITH_PROVIDER_READS",
  "target": {
    "tenant_id": "synthetic-tenant",
    "cloud": "synthetic",
    "component": "intune-configuration",
    "stack": "lab",
    "backend_ref": "lab-backend"
  },
  "provenance": {
    "repository_revision": "synthetic-revision-1",
    "source_inventory_digest": "sha256:REPLACE_WITH_COMPUTED_DIGEST",
    "provider_lock_digest": "sha256:REPLACE_WITH_COMPUTED_DIGEST"
  },
  "execution": {"mode": "emit_only", "credential_ref": null},
  "evidence_class": "synthetic"
}
```

Implement schema validation and reject unexpected versions. Classify operations semantically: read, local write, provider-backed plan, state mutation, live mutation, authorization change, device action, diagnostic collection. A `test`, wrapper, or hook may mutate resources despite its name.

### 3.2 Presentation events

```json
{
  "schema_version": "1",
  "operation_id": "synthetic-operation-001",
  "sequence": 7,
  "event": "collection_progress",
  "collection": "assignments",
  "completed": 12,
  "total": null,
  "coverage": "partial",
  "evidence_class": "synthetic"
}
```

Store event sequence and durable checkpoint separately from animation frames. A spinner means activity. Percentages require a known denominator. Cancellation states are `requested`, `stopped`, and `outcome_uncertain`. Never animate endpoint success from Graph acceptance alone.

## 4. Laboratory architecture and limits

| Layer | Exercise | Cannot establish |
|---|---|---|
| Static | YAML/schema/command/pin validation | Service-side enforcement |
| Script integration | Actual shared scripts with synthetic event inputs | GitHub event semantics |
| Local Actions runner | Supported features of the installed runner | Unsupported platform controls |
| Stateful synthetic service | Failures, coverage, retries, partial outcomes | Actual Graph semantics |
| Backend emulator | Its implemented storage/lease behavior | Actual Azure authorization |
| Native tools | Pinned binaries on known fixtures | Unexercised providers or operating systems |
| Native GitHub | Authorized disposable repository | Actual Intune delivery |
| Authorized tenant/devices | Selected real service and endpoint paths | Universal policy-family support |

`act` documents incomplete compatibility, including ignored job permissions/environments/concurrency and missing OIDC support [S1]. Recheck the installed version; do not count locally modeled approvals as GitHub protected-environment tests.

Microsoft Learn's old free Concierge sandboxes are retired [S3]. Do not use them as a test prerequisite or repeat their historical session/cleanup promises. An Azure subscription does not itself provide all Intune licensing or device evidence. The separate Intune trial guide describes its own setup and conditions [S4].

### Runbook R02 — execute the self-contained offline example

**Prerequisites:** Python 3.10+ standard library. **Effects:** creates a new disposable local directory only. **Network:** none. **Credentials:** none.

Save Appendix A's Python block as `lab.py` in a disposable working directory. It is a reference illustration to integrate with the existing engine, not a replacement for that engine.

Bash:

```bash
python3 lab.py selftest
python3 lab.py init --root reference-run-01
python3 lab.py health
python3 lab.py plan --root reference-run-01
python3 lab.py approve --root reference-run-01
python3 lab.py apply --root reference-run-01
python3 lab.py verify --root reference-run-01
```

PowerShell (stop after any unexpected failure):

```powershell
$ErrorActionPreference = 'Stop'
$labRoot = 'reference-run-01'
foreach ($step in @('init', 'plan', 'approve', 'apply', 'verify')) {
    & python .\lab.py $step --root $labRoot
    if ($LASTEXITCODE -ne 0) { throw "Lab step failed: $step" }
}
& python .\lab.py health
if ($LASTEXITCODE -ne 0) { throw 'Health fixture failed' }
```

**Expected:** initialization creates synthetic state; plan changes `settings`; local approval binds a digest; apply commits sequence 1; verification reports `matches_desired: true`, two historical snapshots, and `endpoint_outcome: unknown`. Health shows 8/8 reporting successful but only 8/100 targeted successful. Repeated apply returns `already_committed` without another history entry.

The JSON `plan.json` is **not** an OpenTofu saved plan. The SQLite transaction is **not** a Graph transaction. The `approve` command grants **no** real authority. There is no HTTP server, secret handling, full UI, per-field accounting engine, or provider integration in this reference.

## 5. Synthetic estate and independent oracles

Expand the existing fixture generator, not just Appendix A, with:

- Multiple policies sharing setting definitions; duplicate names with different IDs.
- Nested typed values, arrays, explicit null versus absent fields, and unknown properties.
- Includes, exclusions, filters, device/user groups, unresolved membership.
- Complete, partial, denied, missing-page, and stale collections.
- Externally owned and unmanaged policies.
- Historical snapshots with rename-only, targeting, setting-value, and setting-move changes.
- Fresh success, fresh failure, pending, stale, and unknown deployment observations.
- Correlated incidents that deliberately do **not** establish causation.

Synthetic tenant/object IDs must be clearly separated from upstream OIB identifiers. Give seeds, generation parameters, source hashes, and scenario names to every fixture. Do not label generated device observations as captured telemetry.

Use independent expected data to check preservation. Comparing generator output to output generated by the same defective function is insufficient. Deliberately mutate exclusions, filter modes, setting types, IDs, and lineage and verify detection. Account for every raw field as desired, relationship, service-owned, separately managed, sensitive-local-only, unsupported, or unknown.

### 5.1 Required fault matrix

| ID | Fault | Oracle |
|---|---|---|
| F01 | Wrong tenant/stack/component/backend | No consequential dispatch |
| F02 | Changed revision/input/provider lock after approval | Approval invalidated |
| F03 | Plan byte change or substitution | Digest/provenance rejection |
| F04 | Backend state advances | No silent replan-and-apply |
| F05 | Two writers contend | Backend lock/CAS prevents conflicting completion |
| F06 | Assignment read denied | Unknown preserved, not empty desired collection |
| F07 | Pagination changes tenant/path/collection | Reject before request to unrelated destination |
| F08 | 429/transient read failure | Bounded retry; known retry delay displayed |
| F09 | Timeout after possible mutation | Read/reconcile before retry decision |
| F10 | Policy write succeeds, assignment fails | Known ID retained, partial outcome journaled |
| F11 | Cancel/kill during write | Recovery exposes durable state and uncertainty |
| F12 | 8 fresh reports out of 100 targeted | Both denominators displayed |
| F13 | Restore old configuration | New reviewed change, not universal rollback |
| F14 | Untrusted PR or injected workflow input | No privileged credential route |
| F15 | Terminal escape sequences in names/logs | Display sanitized without changing source data |
| F16 | Two sources use same display name | IDs remain distinct |
| F17 | OIB update conflicts with company exception | Review proposal, no automatic overwrite |
| F18 | Graph acceptance with no device evidence | Service accepted; endpoint outcome unknown |

Appendix A covers only its enumerated subset. Implement remaining cases against the actual workbench and mark them pending until executed.

## 6. OpenIntuneBaseline source acquisition and adaptation

Source: https://github.com/SkipToTheEndpoint/OpenIntuneBaseline [S5]. Use a small supported Windows policy subset first. Its baseline is community guidance requiring environment-specific review, not an organizational policy authority.

The changelog documents `OIBID:<UUID>` identifiers and `WINDOWS/PolicyManifest.json` [S6]. Treat OIB identity as upstream lineage, tenant+object ID as service identity, and resource address as IaC identity. Do not assume a description marker is unique or truthful in a tenant.

### Runbook R03 — pin a source without deploying it

**Prerequisites:** Git; network access approved for public source acquisition. **Effects:** local checkout only. **Does not run:** upstream scripts or import tools.

Bash:

```bash
# Set to a reviewed full 40-character commit, never a branch or invented hash.
OIB_COMMIT='REPLACE_WITH_REVIEWED_FULL_COMMIT'
[[ "$OIB_COMMIT" =~ ^[0-9a-f]{40}$ ]] || exit 2
git clone --no-checkout https://github.com/SkipToTheEndpoint/OpenIntuneBaseline.git oib-source
git -C oib-source checkout --detach "$OIB_COMMIT"
git -C oib-source rev-parse HEAD
rg --files oib-source/WINDOWS
```

PowerShell:

```powershell
$oibCommit = 'REPLACE_WITH_REVIEWED_FULL_COMMIT'
if ($oibCommit -cnotmatch '^[0-9a-f]{40}$') { throw 'A reviewed full commit is required' }
git clone --no-checkout https://github.com/SkipToTheEndpoint/OpenIntuneBaseline.git oib-source
if ($LASTEXITCODE -ne 0) { throw 'Clone failed' }
git -C oib-source checkout --detach $oibCommit
if ($LASTEXITCODE -ne 0) { throw 'Checkout failed' }
git -C oib-source rev-parse HEAD
```

These placeholders intentionally stop execution. Determine the commit from actual repository evidence. Record file hashes, acquisition time, license, chosen paths, and source format. Pin wiki content separately where used. Branch links in this document are discovery links, not immutable source locks.

The repository carries GPL-3.0 [S7]. Record intended copying/adaptation/distribution and applicable notices before bundling upstream files. This handoff embeds no OIB policy exports or source code.

### 6.1 Three-way comparison

Keep three independently versioned objects:

1. Upstream recommendation at an immutable revision.
2. Company-approved desired configuration, including exceptions.
3. Observed tenant configuration at a timestamp and known coverage.

Differences mean different things. Upstream-vs-company is a recommendation/exception comparison; company-vs-observed may indicate drift; observed-vs-upstream alone cannot diagnose drift. Upstream deletion is not permission to delete a company policy.

Use actual revision pairs to test rename-only changes, moved settings, and changed values. Never infer semantic identity solely from a name or matching OIB token. Record ambiguous candidates for review.

**Output:** source lock, explicit input adapter, field-accounting report, preservation tests, and synthetic estate enriched with attributed explanations.

## 7. GitHub Actions: executable local checks and external control design

### 7.1 Offline CI workflow template

Save the extracted `lab.py` as `lab/reference_lab.py` in an authorized disposable repository. The following job runs only the self-contained synthetic checks. It has no Azure or Graph credentials and performs no deployment.

The checkout commit below is an illustrative historical pin, not a claim of current organizational approval. Verify it and replace it with an approved immutable commit before enabling. The receiving agent must qualify runner/runtime requirements and action dependencies. This YAML was authored here; it was not run on GitHub.

```yaml
name: synthetic-reference-lab
on:
  pull_request:
  workflow_dispatch:
permissions:
  contents: read
jobs:
  offline:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - name: Check out source without persisting credentials
        uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683
        with:
          persist-credentials: false
      - name: Run synthetic checks
        shell: bash
        run: |
          set -euo pipefail
          python3 --version
          python3 lab/reference_lab.py selftest
```

Do not use `pull_request_target` to run untrusted PR code with privileged credentials. CI runners processing untrusted code must not share sensitive caches, workspaces, or identities with deployment runners. Static checks should flag mutable action/image references and unsafe interpolation.

### Runbook R04 — local workflow runner

**Prerequisites:** separately approved installed `act` version and container runtime; reviewed runner image with digest. **Effects:** local container execution, possible image download. **Credentials:** none.

```bash
act --version
act -l -W .github/workflows/synthetic-reference-lab.yml
# Substitute an actually reviewed image digest before execution.
act workflow_dispatch -j offline \
  -W .github/workflows/synthetic-reference-lab.yml \
  -P 'ubuntu-latest=REVIEWED_IMAGE@sha256:REPLACE_WITH_DIGEST'
```

The image placeholder is not a working image reference. Pin it in the compatibility manifest. If containers are unavailable, run `python3 lab/reference_lab.py selftest` directly and report local-script evidence only. Do not mount a credentialed host home or production state into this lab.

### 7.2 Production workflow integration contract

Implement/reuse these operations; names below are interfaces, not preexisting command names:

| Operation | Inputs | Required outputs |
|---|---|---|
| `validate_change` | Trusted base, candidate config, source coverage | Static/preservation/ownership report |
| `resolve_target` | Approved repository config | Effective Atmos target, engine/provider/backend and identity evidence |
| `create_plan` | Exact revision + inputs + target | Saved binary plan, value-free summary, provenance digest |
| `review_plan` | Plan summary + artifact binding | Review decision bound to exact operation |
| `execute_plan` | Trusted approval + exact artifact | Execution receipt and partial/complete result |
| `verify_change` | Expected object/assignment invariants | Readback, convergence, endpoint evidence depth |
| `collect_observations` | Approved reader identity and collection scope | Versioned snapshots, coverage, timestamps |

A deployment workflow must bind repository ID, exact commit, workflow identity/revision, run ID and attempt, environment, tenant/cloud, component/stack, backend, input digests, toolchain/provider locks, plan bytes, expiry, and intended operation. The digest covers exact plan bytes; do not hash a normalized reserialization of a binary plan.

Environment approval alone is not sufficient if the reviewed content is ambiguous. Present artifact identity before approval and revalidate it afterward. If merge or inputs change, generate a new reviewable plan. Never regenerate a fresh plan inside an approved apply job and automatically execute it.

Keep privileged orchestration/verifiers in a protected trust domain. A PR must not replace its own approval verifier or trusted workflow and receive production credentials. Checksums detect changes; they do not establish who authorized those changes.

Set job permissions minimally. Give OIDC request permission only where needed. Separate plan/read identity from write identity where the actual provider and backend allow it. A provider-backed plan may load executable provider code; it is not equivalent to pure parsing.

Use a concurrency key based on the actual tenant/component/state boundary, and backend locking as the independent control. Avoid cancel-in-progress for mutation jobs unless cancellation/reconciliation behavior is qualified. GitHub concurrency is not a substitute for backend locking.

### Runbook R05 — native GitHub qualification

**Prerequisites:** explicit authorization for a disposable repository, appropriate GitHub access, approved Actions policy and runner, reviewed workflow revision. No tenant permissions are required for an offline synthetic workflow.

Bash or PowerShell (replace values before use):

```bash
gh workflow list --repo OWNER/REPOSITORY
gh run list --repo OWNER/REPOSITORY --limit 10
# Mutating control-plane action: run only in the authorized disposable repository.
gh workflow run synthetic-reference-lab.yml --repo OWNER/REPOSITORY --ref REVIEWED_BRANCH
gh run view RUN_ID --repo OWNER/REPOSITORY
```

Record actual repository, run URL, resolved commit, job permissions, runner, log digests, and outcomes. Separately exercise environment approval, rejected approval, fork PR, artifact substitution, rerun, concurrency, and cancellation. Do not infer those controls from the offline workflow above, which does not implement them.

## 8. Azure, Entra, Graph, and provider qualification

GitHub documents Azure federation using OIDC [S2]. Federation avoids a long-lived CI secret where supported, but token issuance is distinct from Graph application permissions, Azure RBAC, and company approval. Validate the actual repository's OIDC claims; do not assume a remembered subject format. `azure/login` success does not prove the chosen provider obtains the required Graph token or that the backend uses the intended identity.

Company-managed keys remain supported only through an approved injection boundary. Never put them in CLI arguments, session JSON, database rows, prompts, diagnostic bundles, or generated HCL. Redaction is not permission to collect a secret unnecessarily. Test lifecycle expiry, revocation, rotation, and log exposure with non-secret canaries.

### Runbook R06 — qualify Atmos and exact-plan routing

**Prerequisites:** pinned installed Atmos/OpenTofu, repository instructions, reviewed hooks/custom commands, known credentials if provider access is intended. Describe/list may evaluate configuration with side effects or authentication; inspect before running.

```bash
atmos version
tofu version
atmos describe component --help
atmos terraform plan --help
atmos terraform apply --help
# Only after inspecting repository behavior:
atmos describe component intune-configuration -s example-dev
```

Determine exact saved-plan arguments from the installed version and repository contract. Do not guess wrapper flags, silently bypass Atmos, or replace OpenTofu with Terraform. The native raw-engine sequence below is only for an explicitly approved disposable non-Atmos fixture:

```bash
# Requires an approved fixture, qualified provider and backend; may contact services.
tofu init -lockfile=readonly
tofu plan -out=reviewed.tfplan
tofu show -json reviewed.tfplan > reviewed.plan.json
# Execute only after exact-plan approval in the authorized fixture.
tofu apply reviewed.tfplan
# Capture exit code: 0=no difference, 2=difference, 1=error for detailed-exitcode.
tofu plan -detailed-exitcode
```

Saved plan and JSON may contain secrets. Store them in restricted temporary/artifact paths; do not upload raw plans as public PR attachments. Do not call a no-change plan an endpoint-health test.

### Runbook R07 — backend emulator and real Azure

Reuse the existing pinned Azurite harness if present. Inspect its image/package digest, supported API/version behavior, host/port binding, disposable paths, synthetic credentials, cleanup, and network restrictions. Do not install a second unpinned emulator merely to match a remembered command.

Required emulator cases: lease contention, interrupted client, restart with persisted data, stale saved plan, expired/released lease behavior supported by that emulator, state read/write, and convergence. Preserve failed attempts and harness corrections.

Real Azure adds: tenant/subscription verification, workload identity federation, data-plane state access, forbidden access negative tests, network/DNS, encryption/access settings, backup/restore, and effective permission evidence. Keep Graph and storage identities separate in the evidence even if the organization permits the same principal.

### Runbook R08 — Graph/provider contract

Use a resource-family registry with provider source/version, API/version, create/read/update/import/assign/delete support, permissions, eventual consistency, field normalization, external deletion, drift, and recovery behavior.

A synthetic HTTP service should return actual fixture-shaped JSON over a local allowlisted endpoint and support deterministic response sequences. Validate nextLink scheme/host/path/tenant/collection before following it; do not blindly concatenate or follow arbitrary URLs. Retry bounded reads using qualified service guidance; reconcile ambiguous writes rather than retrying blindly.

Do not redirect a real provider to an emulator unless it explicitly supports a test endpoint or a reviewed harness implements that path. Do not disable TLS verification to manufacture compatibility. An in-process provider test is a separate evidence class from native plugin RPC.

External qualification sequence: read selected lab objects → negative authorization tests → create a disposable object where authorized → readback → qualified import/adoption → no-change plan → one intended update → assignment readback → convergence → cleanup with retained receipts. Actual endpoint receipt/execution/effective-state evidence requires approved test devices and workload-specific observations.

## 9. Persistent project memory and historical queries

Persist tenant-scoped stable identities and versioned observations. Use captured snapshots plus typed edges. Never store tokens or hidden credential caches in the project database.

Suggested minimal SQL contract (adapt to the existing database and migration framework):

```sql
CREATE TABLE observations (
  observation_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  object_id TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  changed_at TEXT,
  evidence_class TEXT NOT NULL,
  coverage_json TEXT NOT NULL,
  artifact_digest TEXT NOT NULL,
  source_revision TEXT
);
CREATE TABLE relationships (
  observation_id TEXT NOT NULL REFERENCES observations(observation_id),
  source_id TEXT NOT NULL,
  relation TEXT NOT NULL,
  target_id TEXT NOT NULL,
  assertion_class TEXT NOT NULL,
  provenance_json TEXT NOT NULL,
  PRIMARY KEY(observation_id, source_id, relation, target_id)
);
CREATE INDEX observations_by_object_time
  ON observations(tenant_id, object_id, observed_at);
```

This is a schema example, not the full production schema. Enable/verify foreign keys where required; define migrations, backups, access boundaries, encryption strategy, retention, deletion, export, and restore tests. Do not run DDL against an existing production DB without migration review.

Historical questions: what was observed at time T; what desired config was reviewed; when the change actually occurred if known; who changed it or attribution unknown; which PR/run/plan relates to it; what later evidence exists. Do not fabricate precollection history. Keep Git edits, service changes, and observation timestamps distinct.

A snapshot's immutability requires protected artifact storage and trusted receipt handling; a writable local database is not tamper-proof merely because it stores hashes.

## 10. Dictionary, relationships, and visual terminal requirements

Dictionary entries need identifier, name/aliases, type, meaning, applicability, documentation/source date, confidence/assertion class, actual uses, values, overrides, ownership, related workflow, and history. Classify vendor facts, observed facts, attributed community guidance, organization annotations, AI interpretations, and proposals separately.

Navigation acceptance:

1. Search a setting or policy.
2. Select it and highlight upstream/downstream relationships.
3. Inspect exact values and provenance in aligned text.
4. Expand assignments/exclusions/filters and unknown membership.
5. Follow a source into Atmos inheritance and repository location.
6. Open the delivery workflow and its latest relevant evidence.
7. Compare two historical observations.
8. Prepare a controlled maintenance proposal.

Views: estate table, definition inspector, targeting graph, inheritance graph, workflow execution graph, historical comparison, health overview, maintenance queue. Each edge has a type such as `inherits_from`, `assigns_to`, `excludes`, `managed_by`, `deployed_through`, or `observed_after`. A suspected interaction is not a proven dependency. Estate graphs may contain cycles; execution dependencies can use a DAG where appropriate.

Visual direction: fine outlines, restrained color, focused selected-object highlighting, purposeful dot animations, optional isometric figures. Ratatui is a candidate, not a required rewrite. Validate exact dependencies/licenses before reuse [S8]. Ordinary terminal functionality must not depend on image protocols. Exact values and actions remain available through standard text widgets and linear output.

Accessibility and terminal qualification: keyboard focus order, discoverable shortcuts, no color-only meaning, contrast, reduced motion, narrow layouts, resize, Unicode width, escape/control sanitization, stdout/stderr separation, cancellation, terminal restoration after failure, remote/multiplexer compatibility. Never render untrusted control sequences directly. Preserve raw evidence separately from sanitized display values.

### Runbook R09 — PTY and native-terminal acceptance

Use the current PTY harness if present. Declare terminal sizes, encoding, TERM/capabilities, OS, shell, and tool versions. Script actual key sequences for back/edit/cancel/search/history. Test no-TTY output separately. Save deterministic events and permitted screen captures; do not rely only on screenshots to prove action correctness.

Test Windows PowerShell/PowerShell on Windows separately from Linux PowerShell. Use argv execution internally; avoid `eval` and `Invoke-Expression`. Audit literal `--%`, straight/smart quotes, backticks, dollars, newlines, Unicode controls, paths with spaces, and leading hyphens. Prefer direct subprocess argument vectors over shell rendering. Run harmless roundtrips in an isolated lab, preserving original values in machine-readable assertions.

## 11. Monitoring and sustainability

Monitoring must work for supported unmanaged policies as well as IaC-managed ones. Never require adoption before inspection.

Run collection independently of the TUI through an approved scheduler, such as a qualified GitHub workflow or Azure execution service. Record collection start/end, last successful observation, freshness, denied/missing pages, and failure reason. A schedule is a request to run, not a guarantee of timely execution; show actual last-run evidence.

Separate configuration parity, service acceptance, fresh device reporting, processing outcome, effective endpoint state, and user/device outcome. Never use a denominator that hides unreported devices.

Define cohorts and statuses with explicit set membership: eligible, targeted, in-current-cohort, excluded, fresh success, fresh failure, pending, unknown/stale. Document whether statuses overlap; use disjoint partitions for totals. Example fixture: 100 targeted; 8 fresh successful; 92 unknown/stale. Show 100% of reporting and 8% of targeted; do not advance rollout on that evidence.

Maintenance queue fields: tenant/object ID, owner/team, finding, evidence and freshness, priority rationale, due/review date, related proposed change, exception expiry, provider/API compatibility, action state. Upstream OIB differences become proposals or documented exceptions, not automatic remediation.

### Runbook R10 — scheduled observation and stale data

1. Scheduler obtains approved reader identity for a declared tenant and collection set.
2. Collector writes staged captures and coverage, then atomically publishes an observation batch.
3. Independent checks reject mixed-tenant data, page gaps disguised as complete, and inconsistent counts.
4. Update history/health using observation IDs; preserve last-good data with an explicit stale marker on failure.
5. TUI displays last attempted collection, last successful collection, missing scope, and next permitted action.
6. Repeated failures create a maintenance finding. Never erase last-good observations or convert denied reads to empty policies.

Test collection while TUI is closed, repeated identical snapshots, delayed snapshots, out-of-order arrivals, pagination changes during capture, and partial batch failure. Define snapshot consistency limits honestly.

## 12. Recovery runbooks

### R11 — interruption before commit (reference lab)

```bash
python3 lab.py init --root interrupted-before
python3 lab.py plan --root interrupted-before
python3 lab.py approve --root interrupted-before
python3 lab.py apply --root interrupted-before --fault before-commit
# Expected exit 2. Inspect before deciding what to do next.
python3 lab.py verify --root interrupted-before
python3 lab.py apply --root interrupted-before
```

Expected first verification: sequence 0, desired not yet matched. Later apply commits once. This injects an exception, not SIGKILL, power loss, OS crash, or actual Graph failure. Test those separately against the real engine/journal on disposable hosts.

### R12 — response lost after commit (reference lab)

```bash
python3 lab.py init --root interrupted-after
python3 lab.py plan --root interrupted-after
python3 lab.py approve --root interrupted-after
python3 lab.py apply --root interrupted-after --fault after-commit
# Expected exit 2: the client did not receive success, but state was committed.
python3 lab.py verify --root interrupted-after
python3 lab.py apply --root interrupted-after
```

Expected verification: sequence 1 and desired matched; repeated application reports `already_committed`. Do not generalize local idempotency to Graph operations without a qualified operation-specific mechanism.

### R13 — real partial policy/assignment mutation

Stop further mutation. Retain known object ID, successful request evidence, failure response, target, plan, and run identity. Read policy and assignments independently with the approved reader. Mark each stage proven, unknown, or failed. Never delete partial state or recreate the policy solely because the overall run failed. Generate a bounded recovery proposal; changes beyond the approved operation require applicable review. Show unresolved endpoint state.

### R14 — stale approval, drift, or restoration request

Re-read target and current state. Compare artifact identity, source inventory, repository, locks, inputs, assignment cohort, expiry, and approval binding. Invalidate affected approvals and create a fresh reviewable plan. Do not reuse an old approval for a new plan. Restoring historical desired configuration is a new change; provider rollback and endpoint undo are not guaranteed.

### R15 — failed package or release gate

Preserve failed outputs, tool exit codes, source/build digests, and findings. Fix the cause without deleting contrary evidence. Rerun only checks affected by the change plus required gates. Rebuild the release from the tested source. Verify extraction safety, hashes, relative references, and tests against the actual extracted package. A skipped mandatory prerequisite remains blocked. A ZIP checkpoint may deliberately omit large artifacts; it must not be represented as a complete runtime distribution.

## 13. Wally: development performance and robustness

Wally reviews implementation and measurements to help ChatGPT improve the wizard. It is optional to end users and separate from the agent making changes.

Workloads: cold/warm startup, inventory normalization, 1/8/many-policy selection, search, graph expansion, history comparison, rendering during collection, cancellation latency, interrupted resume, process cleanup, and scheduled collection. Declare realistic bounded sizes including policy counts, nested settings, assignments, observations, and edges. Scaling synthetic device counts is not a live-tenant throughput benchmark.

Measure wall time, input-to-feedback latency, memory with explicitly stated sampling, process-tree lifetime, bytes/requests, redraw/idle CPU, and cancellation outcome. Do not claim P99 from a small sample or use repeated runs of the same cached process as cold-start evidence.

### 13.1 Minimal measurement script

This script measures fresh Python processes running the **reference self-test**, not the whole wizard. Save as `measure_reference.py` beside `lab.py`.

```python
import json
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path

script = Path(__file__).with_name("lab.py")
rows = []
for sample in range(7):
    start = time.perf_counter()
    result = subprocess.run([sys.executable, str(script), "selftest"],
                            capture_output=True, text=True, timeout=30)
    elapsed = time.perf_counter() - start
    rows.append({"sample": sample, "seconds": elapsed,
                 "exit_code": result.returncode})
    if result.returncode != 0:
        raise SystemExit("Reference check failed; do not report speed improvement")
print(json.dumps({"workload": "reference-selftest-fresh-process",
                  "platform": platform.platform(),
                  "python": sys.version,
                  "samples": rows,
                  "median_seconds": statistics.median(r["seconds"] for r in rows)}, indent=2))
```

Run:

```bash
python3 measure_reference.py > reference-measurement.json
```

### 13.2 Contribution evaluation

Compare at least matched no-Wally and Wally-assisted arms from the same revision using the same model, effort, tools, budget, task, and separately controlled implementation agent. Review advice must not modify code itself. Record discarded suggestions, timeouts, failed repairs, added cost, regressions, and retained improvements.

Where resources permit, include the strongest existing review composition and a Wally-plus-deterministic-profiler arm. Keep tuning cases separate from protected held-out tasks. Prevent access to hidden answers and grader modification. A model-generated persuasive review is not evidence of performance improvement.

Promote an implementation change only after correctness/security/recovery gates and repeatable improvement evidence. Promote Wally only after comparative evidence establishes useful incremental contribution. “No demonstrated advantage” is a valid result.

## 14. Security verification and external qualification checklist

- Trusted inputs and verifiers cannot be replaced by untrusted PR content.
- No credentials in process arguments, AI context, UI events, logs, sessions, artifacts, or test outputs.
- State and plan artifacts have appropriate access and retention; no claim that a sensitive flag encrypts them.
- Reader/writer/backend authorities and target identities are independently checked.
- Negative authorization tests use an approved lab and expected denied operations; denial is evidence, not an invitation to bypass controls.
- Artifact digest verification is coupled to trusted provenance and approval, not merely self-supplied checksums.
- Symlink/hardlink/path traversal and interrupted-write behavior are tested in disposable paths.
- Child processes, inherited environment, egress, timeouts, and cancellation are constrained.
- DB/artifact restoration and migrations preserve identity, history, access controls, and evidence links.
- No autonomous device actions, tool installations, tracing, or privilege escalation during diagnosis.

Actual GitHub, Azure, Intune, Windows, and endpoint-device evidence remains required for the declared supported routes. Appendix A is intentionally not a hardened execution service.

## 15. Acceptance and work sequence

| Milestone | Required demonstration |
|---|---|
| M1 Current candidate closure | Substantially reported complete locally: verify exact final delivery, supplements, and evidence links; preserve unresolved gates |
| M2 Connected lab | Supported policy journey through actual workbench scripts, synthetic service, and explicit evidence |
| M3 CI integration | Native GitHub controls qualified where authorized; local simulations labeled otherwise |
| M4 Persistent inspection | Dictionary, relationships, history, effective-value lineage work from the terminal |
| M5 Sustained operations | Closed-TUI collection, health/freshness, drift, maintenance queue, recovery |
| M6 Platform and production | Applicable native-host, AppSec, tenant/device pilot, and organizational acceptance |

**Execution priority after the latest transcript:** finish delivery confirmation; freeze the verified candidate; implement M2/M4/M5 using the existing engine and labs; advance M3 and M6 when their respective external prerequisites are available. No positive Wally result is a prerequisite for these milestones.

First complete product demonstration: discover an existing policy with a health concern, understand it, inspect relationships/history, propose a change, review its CI plan, execute under applicable authority, and inspect exactly what the evidence proves afterward.

Do not stop after a polished graph or passing unit suite. Demonstrate no-IaC onboarding, existing-repository integration, unmanaged-policy inspection, faithful adoption, subsequent change, and recovery. Keep a precisely declared policy profile while qualifying additional families individually.

## 16. Deliverables expected from the receiving agent

1. Updated source and discoverable terminal entrypoints.
2. Workflow templates converted into reviewed runnable integrations where prerequisites permit.
3. Source locks and approved dependency/compatibility matrix.
4. OIB adapter and explicit mapping coverage, not universal-export claims.
5. Synthetic estate, historical data, failure scenarios, independent expected outputs.
6. Persistent database migrations and operational runbooks.
7. Requirement-to-evidence ledger and exact artifact receipts.
8. Performance baselines, retained improvements, and Wally contribution results.
9. Packaged runtime separated from development corpus and hidden evaluation answers.
10. Clean-extraction verification and a short final report of actual user capabilities and unresolved gates.

Use checkpoints for long work. Do not re-request authorization for already authorized local work. Do not treat a missing external prerequisite as permission to simulate it silently and call it passed.

## 17. Sources and freshness

These are reference links inspected during the originating conversation, with S1/S2 rechecked on 2026-10-04. Revalidate behavior against exact installed versions and acquire immutable revisions for reuse. The report's architecture, runbooks, and examples are original proposed implementation material.

- **S1:** act compatibility limits — https://nektosact.com/not_supported.html
- **S2:** GitHub OIDC with Azure — https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-azure
- **S3:** Microsoft Learn FAQ, sandbox availability — https://learn.microsoft.com/en-us/training/support/faq
- **S4:** Intune trial setup — https://learn.microsoft.com/en-us/intune/fundamentals/free-trial-sign-up
- **S5:** OpenIntuneBaseline — https://github.com/SkipToTheEndpoint/OpenIntuneBaseline
- **S6:** OIB Windows changelog — https://github.com/SkipToTheEndpoint/OpenIntuneBaseline/blob/main/WINDOWS/CHANGELOG.md
- **S7:** OIB license — https://github.com/SkipToTheEndpoint/OpenIntuneBaseline/blob/main/LICENSE
- **S8:** Terminal visual references — https://grixate.github.io/dot-loaders/ ; https://github.com/ratatui/ratatui/tree/main/examples ; https://github.com/ratatui/ratatui/tree/main/ratatui-widgets/examples ; https://github.com/ratatui/ratatui-spinner ; https://github.com/sorinirimies/tui-spinner
- **S9:** LabEx exercise inspiration, not an inspected reusable implementation — https://labex.io/labs/github-actions-basic-build-and-test-633886
- **S10:** Checkout action documentation — https://github.com/actions/checkout

S8 links specify visual intent, not approved dependencies. Some linked repositories/pages were not retrievable in the original inspection. Do not claim their code or licenses were audited.

## Appendix A. Executable offline reference: `lab.py`

Copy this entire block into `lab.py`. No third-party packages are required. Only run it in a disposable local directory. It uses a fixed synthetic target and local SQLite state. Local files and database are not a security boundary against a malicious same-user process. File creation is not hardened against path attacks; initialization is not crash-atomic. Do not reuse it as production persistence or authorization code.

<!-- BEGIN_EXECUTABLE_LAB -->
```python
"""Offline reference only: no Graph, provider, credentials, or real approvals."""
import argparse
import copy
import hashlib
import json
import sqlite3
import tempfile
from pathlib import Path


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def context():
    return {"tenant": "synthetic-tenant", "stack": "lab", "component": "intune",
            "backend": "local-sqlite-model", "revision": "synthetic-revision-1",
            "toolchain": "reference-lab-v1"}


def policy():
    return {"tenant": "synthetic-tenant", "id": "synthetic-policy-1",
            "name": "Example policy", "writer": "lab",
            "coverage": {"settings": "complete", "assignments": "complete"},
            "settings": {"example.enabled": True, "example.timeout": 15},
            "assignments": [
                {"kind": "include", "group": "synthetic-pilot", "filter": None},
                {"kind": "exclude", "group": "synthetic-exception", "filter": None}]}


def validate(p, c):
    require(c == context(), "context differs from fixed offline lab target")
    require(p["tenant"] == c["tenant"], "wrong tenant")
    require(p["writer"] == "lab", "writer conflict")
    require(p["coverage"] == {"settings": "complete", "assignments": "complete"},
            "incomplete collection")
    require(isinstance(p["settings"], dict), "settings must be an object")
    require(isinstance(p["assignments"], list), "assignments must be known")
    canonical(p)  # Reject non-JSON values and NaN; booleans remain distinct from numbers.


def write_new(path, value):
    # Lab artifacts use exclusive creation; this is not a hardened production writer.
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, indent=2, ensure_ascii=True) + "\n")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def connect(root):
    require((root / "state.db").is_file(), "run init first")
    con = sqlite3.connect(root / "state.db", timeout=2, isolation_level=None)
    con.execute("PRAGMA synchronous=FULL")
    return con


def snapshot(con):
    seq, body = con.execute("SELECT seq, body FROM current_state WHERE id=1").fetchone()
    return seq, json.loads(body)


def initialize(root):
    root.mkdir(parents=True, exist_ok=False)
    con = sqlite3.connect(root / "state.db")
    try:
        con.executescript('''
        CREATE TABLE current_state(id INTEGER PRIMARY KEY CHECK(id=1), seq INTEGER, body TEXT);
        CREATE TABLE history(seq INTEGER PRIMARY KEY, operation TEXT UNIQUE, body TEXT);
        CREATE TABLE operations(digest TEXT PRIMARY KEY, seq INTEGER);
        ''')
        con.execute("INSERT INTO current_state VALUES(1,0,?)", (canonical(policy()),))
        con.execute("INSERT INTO history VALUES(0,'seed',?)", (canonical(policy()),))
        con.commit()
    finally:
        con.close()
    write_new(root / "context.json", context())
    desired = policy()
    desired["settings"]["example.timeout"] = 20
    write_new(root / "desired.json", desired)
    return {"status": "initialized", "evidence_class": "synthetic"}


def plan(root):
    c, desired = read(root / "context.json"), read(root / "desired.json")
    validate(desired, c)
    con = connect(root)
    try:
        seq, observed = snapshot(con)
    finally:
        con.close()
    validate(observed, c)
    require(desired["id"] == observed["id"], "object identity changed")
    changed = [key for key in sorted(set(observed) | set(desired))
               if canonical(observed.get(key)) != canonical(desired.get(key))]
    p = {"schema": "synthetic-plan/1", "evidence_class": "synthetic",
         "context": c, "base_seq": seq, "before_digest": digest(observed),
         "desired": desired, "changed_fields": changed}
    write_new(root / "plan.json", p)
    return {"plan_digest": digest(p), "changed_fields": changed}


def approve(root):
    p = read(root / "plan.json")
    require(p["context"] == read(root / "context.json"), "stale context")
    write_new(root / "approval.json", {"schema": "lab-approval/1",
              "synthetic": True, "plan_digest": digest(p)})
    return {"status": "lab_approval_recorded", "real_authorization": False}


def apply(root, fault="none"):
    p, a = read(root / "plan.json"), read(root / "approval.json")
    c, desired = read(root / "context.json"), read(root / "desired.json")
    require(a.get("synthetic") is True, "not a lab approval")
    require(a["plan_digest"] == digest(p), "plan digest mismatch")
    require(p["context"] == c, "stale context")
    require(canonical(p["desired"]) == canonical(desired), "desired input changed")
    validate(desired, c)
    operation = digest(p)
    con = connect(root)
    try:
        con.execute("BEGIN IMMEDIATE")
        seq, observed = snapshot(con)
        prior = con.execute("SELECT seq FROM operations WHERE digest=?", (operation,)).fetchone()
        if prior:
            require(canonical(observed) == canonical(desired), "later drift requires investigation")
            con.rollback()
            return {"status": "already_committed", "seq": prior[0]}
        require(seq == p["base_seq"] and digest(observed) == p["before_digest"], "stale state")
        require(observed["id"] == desired["id"], "object identity changed")
        require(fault != "before-commit", "injected interruption before commit")
        next_seq = seq + 1
        body = canonical(desired)
        con.execute("UPDATE current_state SET seq=?,body=? WHERE id=1", (next_seq, body))
        con.execute("INSERT INTO history VALUES(?,?,?)", (next_seq, operation, body))
        con.execute("INSERT INTO operations VALUES(?,?)", (operation, next_seq))
        con.commit()
    except BaseException:
        if con.in_transaction:
            con.rollback()
        raise
    finally:
        con.close()
    if fault == "after-commit":
        raise TimeoutError("injected lost response; read state before deciding to retry")
    return {"status": "committed", "seq": next_seq, "endpoint_outcome": "unknown"}


def verify(root):
    con = connect(root)
    try:
        seq, observed = snapshot(con)
        rows = con.execute("SELECT seq,operation,body FROM history ORDER BY seq").fetchall()
    finally:
        con.close()
    return {"evidence_class": "synthetic", "seq": seq,
            "matches_desired": canonical(observed) == canonical(read(root / "desired.json")),
            "endpoint_outcome": "unknown",
            "history": [{"seq": r[0], "operation": r[1], "policy": json.loads(r[2])} for r in rows]}


def health():
    # These are explicitly modeled counts for one snapshot, not Graph reports.
    targeted, reporting, successful = 100, 8, 8
    return {"evidence_class": "synthetic", "targeted": targeted,
            "fresh_reporting": reporting, "successful": successful,
            "unknown_or_stale": targeted-reporting,
            "success_of_reporting_pct": 100 * successful/reporting,
            "success_of_targeted_pct": 100 * successful/targeted,
            "rollout_ready": False}


def selftest():
    results = []
    def case(name, fn):
        with tempfile.TemporaryDirectory() as temporary:
            r = Path(temporary) / "lab"
            initialize(r)
            fn(r)
        results.append({"case": name, "status": "PASS"})
    def rejected(fn):
        try:
            fn()
        except (ValueError, TimeoutError):
            return
        raise AssertionError("expected rejection")
    def alter(r, filename, fn):
        obj = read(r / filename)
        fn(obj)
        (r / filename).write_text(json.dumps(obj), encoding="utf-8")
    def happy(r):
        plan(r); approve(r); apply(r)
        require(verify(r)["matches_desired"], "readback mismatch")
        require(apply(r)["status"] == "already_committed", "not idempotent")
        require(len(verify(r)["history"]) == 2, "duplicate history")
    case("happy_readback_history_idempotence", happy)
    def tamper(r):
        plan(r); approve(r)
        alter(r, "plan.json", lambda p: p.update(base_seq=999))
        rejected(lambda: apply(r))
        require(verify(r)["seq"] == 0, "tamper mutated state")
    case("tampered_plan_rejected", tamper)
    def stale(r):
        plan(r); approve(r)
        alter(r, "context.json", lambda c: c.update(revision="changed"))
        rejected(lambda: apply(r))
    case("changed_revision_rejected", stale)
    def denied(r):
        alter(r, "desired.json", lambda p: p["coverage"].update(assignments="denied"))
        rejected(lambda: plan(r))
    case("denied_assignments_rejected", denied)
    def writer(r):
        alter(r, "desired.json", lambda p: p.update(writer="external"))
        rejected(lambda: plan(r))
    case("external_writer_rejected", writer)
    def identity(r):
        alter(r, "desired.json", lambda p: p.update(id="other"))
        rejected(lambda: plan(r))
    case("changed_identity_rejected", identity)
    def before(r):
        plan(r); approve(r); rejected(lambda: apply(r, "before-commit"))
        require(verify(r)["seq"] == 0, "rollback failed")
        apply(r)
    case("before_commit_recovery", before)
    def after(r):
        plan(r); approve(r); rejected(lambda: apply(r, "after-commit"))
        require(verify(r)["matches_desired"], "lost committed outcome")
        require(apply(r)["status"] == "already_committed", "repeated mutation")
    case("lost_response_reconciliation", after)
    def concurrent(r):
        plan(r); approve(r)
        con = connect(r)
        try:
            con.execute("UPDATE current_state SET seq=seq+1")
        finally:
            con.close()
        rejected(lambda: apply(r))
    case("stale_state_rejected", concurrent)
    require(canonical(True) != canonical(1), "bool/integer confusion")
    results.append({"case": "typed_json_equality", "status": "PASS"})
    require(health()["success_of_targeted_pct"] == 8 and not health()["rollout_ready"],
            "denominator error")
    results.append({"case": "reporting_denominator", "status": "PASS"})
    return {"evidence_class": "synthetic", "cases": results, "passed": len(results)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["init", "plan", "approve", "apply", "verify", "health", "selftest"])
    parser.add_argument("--root", type=Path, default=Path("reference-lab-output"))
    parser.add_argument("--fault", choices=["none", "before-commit", "after-commit"], default="none")
    args = parser.parse_args()
    try:
        if args.command == "selftest":
            result = selftest()
        elif args.command == "health":
            result = health()
        elif args.command == "apply":
            result = apply(args.root, args.fault)
        else:
            result = {"init": initialize, "plan": plan, "approve": approve, "verify": verify}[args.command](args.root)
        print(json.dumps(result, indent=2, ensure_ascii=True))
        return 0
    except (ValueError, TimeoutError, OSError, sqlite3.Error, KeyError) as exc:
        print(json.dumps({"status": "error", "kind": type(exc).__name__, "message": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
```
<!-- END_EXECUTABLE_LAB -->

## Appendix B. State-based grading and the proposed external lab tools

### B.1 Correct interpretation of the additional research

Adopt observable-state grading throughout the laboratory. Keep synthetic tests for controlled failures, then add independent observations of the actual implementation and actual external services where authorized. A persisted simulator database is real filesystem state but its policy contents remain a model of Intune. Changing the grader does not change that boundary.

| Proposed claim | Correct implementation requirement |
|---|---|
| State-based grading eliminates shared wrong assumptions | It reduces reliance on command success. Graders can still encode incorrect expectations; review their specification, provenance, and negative controls independently. |
| Linux capstone completion proves enterprise readiness | It proves the exercised Linux tasks. Intune policy, GitHub protection, Azure identity, and company acceptance each require their own evidence. |
| Azurite simulates Entra authentication and authorization | It emulates supported storage behavior. Its basic OAuth mode does not validate token signatures or permissions; retain native identity and authorization tests [S13]. |
| OpenAPI-generated mocks simulate all Graph endpoints | Schemas help generate structural fixtures. Implement and qualify a bounded endpoint subset, state transitions, pagination, partial failures, and reporting delays. |
| `act` is the official offline GitHub runner | It is a separate local workflow implementation with documented gaps [S1]. An official self-hosted runner is connected to GitHub's control plane. |
| Terratest supplies Azure and Graph mock providers | Terratest is a Go infrastructure testing library. Mock providers or an actual provider test endpoint are separate components [S16]. |
| AI is the acceptance oracle | AI proposes cases and reviews differences. Deterministic, independently reviewed assertions decide preservation and release acceptance. |
| Mock audit logs establish compliance | Logs support investigation. Identity, integrity, retention, coverage, and organizational controls must still be qualified. |
| Synthetic device records are enrolled endpoints | They exercise reporting UI and aggregation only. Enrollment, processing, and effective endpoint state require actual devices. |

Do not replace working lab components solely to adopt another framework. Evaluate the smallest addition that closes a named evidence gap. Do not add LangChain or an autonomous model runtime as a prerequisite for deterministic qualification. Wally remains an optional development reviewer.

### B.2 dsoxlab evaluation contract and runbook R16

The upstream dsoxlab project describes declarative lab execution and checking [S11]. Evaluate a pinned framework and catalog before integrating either. Its Linux catalog documents a distinction between learner checks and instructor reference-solution replay [S12]. Inspect the pinned catalog's fixtures to prevent a grader from repairing the subject before checking it.

The following is a **command template**, not an executed installation. Use an isolated disposable environment. Establish an approved framework wheel and dependency lock first; catalog setup scripts may modify the host or provision infrastructure.

```bash
# Set these to independently reviewed values; there is deliberately no floating default.
: "${DSOXLAB_CATALOG_COMMIT:?Set a reviewed full catalog commit}"
: "${DSOXLAB_REQUIREMENTS_LOCK:?Set the reviewed hashed requirements file}"
python3 -m venv .venv-dsoxlab
.venv-dsoxlab/bin/python -m pip install --require-hashes -r "$DSOXLAB_REQUIREMENTS_LOCK"
git clone https://github.com/stephrobert/linux-dsoxlab-training.git dsoxlab-catalog
git -C dsoxlab-catalog checkout --detach "$DSOXLAB_CATALOG_COMMIT"
git -C dsoxlab-catalog rev-parse HEAD
.venv-dsoxlab/bin/dsoxlab --help
.venv-dsoxlab/bin/dsoxlab run --help
.venv-dsoxlab/bin/dsoxlab check --help
```

After inspecting the catalog setup, teardown, fixture hooks, license, and runtime requirements, use its documented catalog registration/selection route for the installed version. Run `dsoxlab doctor`, then the reviewed `run` and `check` commands for an actual listed lab ID. Capture exit codes and evidence. Do not invent a `graph-api-qualification` catalog entry or use an unverified Terraform module source. A `start` command, where supported, may also provision resources; inspect its help before use.

**Integration acceptance:** create an Intune-specific catalog only if the framework improves repeatable setup, grading, or reporting. It must preserve these modes:

- Learner/system-under-test grading: observes the result without replaying a solution or repairing state.
- Reference exercise: deliberately establishes a known correct result and tests the grader; labeled separately.
- Negative controls: deliberately wrong state must fail the grader.
- Recovery exercise: destroys/restarts only the declared disposable process or environment and checks persistence afterward.

Do not equate process restart with machine reboot or power-loss durability. Record exactly which interruption was performed. Linux filesystem or SELinux exercises can teach the method but cannot substitute for Intune semantic preservation tests.

### B.3 Independent persisted-state checker and runbook R17

Save this as `lab/grade_persisted_state.py`. It reads the reference database in a separate process, imports no application functions, and compares against an explicit expected fixture. Run it only after the reference lab's successful change, including the lost-response recovery exercise. This checks SQLite persistence and the reference policy contract; it does not establish Graph correctness or a security boundary.

```python
import json
import sqlite3
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve(strict=True)
db = (root / "state.db").resolve(strict=True)
expected = {
    "tenant": "synthetic-tenant", "id": "synthetic-policy-1",
    "name": "Example policy", "writer": "lab",
    "coverage": {"settings": "complete", "assignments": "complete"},
    "settings": {"example.enabled": True, "example.timeout": 20},
    "assignments": [
        {"kind": "include", "group": "synthetic-pilot", "filter": None},
        {"kind": "exclude", "group": "synthetic-exception", "filter": None}
    ]
}

def check(condition, message):
    if not condition:
        raise SystemExit("FAIL: " + message)

con = sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)
try:
    check(con.execute("PRAGMA integrity_check").fetchone() == ("ok",), "database integrity")
    rows = con.execute("SELECT seq, body FROM current_state").fetchall()
    check(len(rows) == 1 and rows[0][0] == 1, "one committed change")
    observed = json.loads(rows[0][1])
    # Serialized JSON distinguishes true from 1; do not use Python dict equality alone.
    check(json.dumps(observed, sort_keys=True) == json.dumps(expected, sort_keys=True),
          "complete expected policy, settings and targeting")
    history = con.execute("SELECT seq, operation, body FROM history ORDER BY seq").fetchall()
    check([r[0] for r in history] == [0, 1], "no duplicated or missing history")
    check(json.loads(history[0][2])["settings"]["example.timeout"] == 15, "original value retained")
    check(history[1][2] == rows[0][1], "history agrees with committed state")
    operations = con.execute("SELECT digest, seq FROM operations").fetchall()
    check(operations == [(history[1][1], 1)], "operation identity and sequence")
finally:
    con.close()
print(json.dumps({"status": "PASS", "evidence_class": "synthetic",
                  "observation": "persisted SQLite state from separate process"}))
```

```bash
python3 lab/grade_persisted_state.py reference-lab-output
```

Negative control: on a separate disposable copy, change the stored timeout or remove the exclusion and verify that this checker fails. Do not mutate the retained passing evidence. The receiving agent should extend independently reviewed state assertions to artifact digests, backend leases, actual provider readback, native GitHub approval enforcement, and eventually endpoint observations.

### B.4 Tool selection and network layout

The following earlier candidates remain optional. Appendix C contains the updated decisions; none is a mandatory new dependency.

| Candidate | Evaluate for | Must not claim |
|---|---|---|
| Existing stateful Graph lab | Preserve prior scenarios and add independent state inspection | Universal Graph parity |
| MockLoop [S14] | Generating bounded API fixtures and managing scenarios after code/license/security review | Verified support for every Graph endpoint, an assumed MCP tool count, or automatic compliance |
| WireMock [S15] | HTTP request matching, scripted faults, and scenario transitions | Automatic Intune business semantics or actual tenant authorization |
| Azurite [S13] | Supported blob operations, leases, and backend recovery | Entra permission enforcement or full Azure parity |
| Testcontainers | Disposable dependency lifecycle, if compatible with the existing language/runtime | More faithful service behavior merely from containerization |
| Terratest [S16] | Reusable Go helpers where actual infrastructure tests need them | An included Intune mock provider |
| dsoxlab [S11–S12] | Declarative setup and observable-state grading | Organizational production acceptance |

For a Compose implementation, retain established service names and ports where possible. Example addresses are `graph-lab:8081`, `github-lab:8082`, and `azurite:10000`; these do not require creating a GitHub emulator. Put the actual test driver on the internal network or publish deliberate loopback endpoints for a host driver. Keep the oracle/control interface inaccessible to the product. Inside containers, `localhost` means that container. Use immutable reviewed image digests, isolated volumes, synthetic identities, and explicit endpoint configuration. Do not route production tokens to lab endpoints. Network isolation is an enforced runner/container property, not a comment or environment variable.

The Graph SDK/provider must explicitly support the chosen test endpoint and credential adapter. If it does not, keep an in-process transport harness separate from the actual OpenTofu/provider RPC test. Do not disable certificate verification to make the route work. A provider mock cannot qualify the real provider's resource lifecycle.

### B.5 Additional primary sources

- **S11:** [dsoxlab upstream framework](https://github.com/stephrobert/dsoxlab). Verify the pinned CLI and catalog schema before adoption.
- **S12:** [Linux training catalog](https://github.com/stephrobert/linux-dsoxlab-training/blob/main/README.md). Inspect learner/reference replay behavior at the acquired revision.
- **S13:** [Microsoft: install and run Azurite](https://learn.microsoft.com/en-us/azure/storage/common/storage-install-azurite), including basic OAuth limitations.
- **S14:** [MockLoop basic usage](https://docs.mockloop.com/guides/basic-usage/). Candidate documentation, not independently qualified integration.
- **S15:** [WireMock stateful behavior](https://wiremock.org/docs/stateful-behaviour/).
- **S16:** [Terratest project documentation](https://terratest.gruntwork.io/).

These sources inform tool evaluation. No external framework, mock server, cloud resource, or catalog was installed or provisioned while preparing this handoff.

## Appendix C. Consolidated research decisions and execution corrections

This appendix incorporates the supplied open-source qualification dossier as research input. Its repository inspections, versions, action pins and commands have not been independently requalified during this document update. Verify exact revisions, licenses, CLI syntax and compatibility before integration. Research citations from another conversation are not local execution receipts.

### C.1 Smallest useful stack

The supplied research did not locate an adequate maintained open-source emulator implementing the required writable Intune lifecycle. This is a scoped negative search result, not proof that none exists. Inspect the existing semantic model and synthetic service before building anything new.

| Component | Updated decision | Evidence boundary |
|---|---|---|
| Existing Intune semantic model/service | Inspect and extend first | Preserve valid existing scenarios and receipts |
| Narrow `intune-lab` HTTP adapter | Add only missing routes, persistence and deterministic failpoints | Bounded service model, not general Graph parity |
| Azurite | Retain existing backend tests | Native Azure identity and authorization remain external |
| Microsoft Dev Proxy | Evaluate for HTTP/Graph faults absent from the existing lab | Does not supply a stateful Intune lifecycle |
| Toxiproxy | Use selectively for transport faults | Service-aware commit/lost-response failpoints remain necessary |
| actionlint | Add static workflow validation where missing | Native controls require native GitHub tests |
| act | Optional unprivileged smoke tests | No approval, federation or control-plane qualification |
| Native GitHub Actions | Qualify approval, permissions, artifacts, concurrency and federation | Requires authorized repository and declared controls |
| Microsoft tui-test | Prototype against actual TUI; verify version, license and commands | Retain the existing PTY harness until compatibility is established |
| Schemathesis/property tests | Supplement explicit semantic assertions | Schema checks are not an Intune oracle |
| Dex | Add only for identity-protocol behavior implemented by our own code | Cannot qualify GitHub-to-Entra exchange |
| hyperfine | Supplement specific process-level measurements | Version-command timing is not workbench startup or interaction latency |
| Intune Preflight | Inspect collection, retry and completeness patterns | Do not use as the acceptance oracle |
| OpenIntuneBaseline | Pin reference material and record provenance/distribution obligations | Community recommendations require company review |
| Floci and MiniStack | No direct dependency for current Azure/Intune path; borrow isolation/state-inspection patterns | Supplied research identifies AWS emulators, not the missing Intune backend |
| Floci AZ | Defer unless a demonstrated Azure gap remains beyond Azurite | Directory Graph and AzureRM coverage do not establish Intune/Microsoft365-provider compatibility |
| dsoxlab | Borrow grading patterns; adopt only for a concrete improvement | Optional framework, not a release requirement |
| WireMock / MockServer / MockLoop | Optional scripted-fixture fallback after exact capability review | Do not add multiple overlapping mock frameworks |
| Compose / Testcontainers / Terratest | Prefer existing orchestration and language; add only for a named need | Orchestration does not improve service fidelity by itself |

This supersedes the earlier recommendation to make a Floci AZ compatibility exercise the immediate next task. The next useful result is a connected maintenance journey and a precise remaining-blocker ledger.

### C.2 Corrections required before executing dossier examples

The dossier's larger Compose and deployment workflow examples remain design inputs. They are not drop-in runnable integrations. Apply these requirements to their actual repository equivalents; the self-contained reference code in Appendix A remains unchanged.

| Defect | Required correction and acceptance observation |
|---|---|
| Plan-only journey | Include review, explicitly synthetic lab approval, execution of exact approved plan bytes, independent readback and no-change second plan. If provider execution is unavailable, mark that stage BLOCKED rather than silently substituting a simulator. |
| Workflow-wide cancellation | Separate validation and deployment workflows or demonstrate equivalent isolation. A job-level setting alone does not resolve a cancellation policy on the enclosing workflow. Test cancellation and recovery at both scopes. |
| Event filter mistaken for trust | Enforce permitted deployment refs, protected environment restrictions and trusted workflow/verifier revisions. Merely excluding pull requests is insufficient. |
| Grader runs after teardown | Grade and export oracle state, journal and sanitized logs before removing containers/volumes. Retain failure evidence. A post-teardown grader may consume an exported snapshot only when that mode is explicitly implemented. |
| Host driver cannot reach internal network | Run the driver on the internal network or publish selected loopback endpoints. Verify the product cannot access private control/oracle operations. |
| PowerShell native failures ignored | Use a tested native-command wrapper checking exit codes, including pipeline behavior. Preserve the primary failure if cleanup fails. `$ErrorActionPreference` alone is not the native exit-code contract. |
| Partial placeholder detection | Before startup, reject every required unresolved placeholder and missing configuration file, including source/image/action pins and actual-script mappings. Do not limit checks to two placeholder prefixes. |
| Invented interfaces | Publish a proposed-operation-to-real-entrypoint map. Implement missing interfaces before describing their commands as runnable. |
| Identity roles conflated | Record Graph permissions, backend access and GitHub authority independently. Planning may require backend lease operations while still denying Intune configuration writes. |
| Failure evidence lost | Export sanitized readback and execution evidence on unsuccessful/interrupted runs; constrain access and retention for plans, state and captures. |

For security negative controls, use inert markers and non-secret canaries rather than printing real credentials. A trusted verifier must compare manifest fields against independently trusted target policy, not merely validate a manifest's self-supplied hash.

### C.3 Stateful adapter and independent grading contract

Derive routes from the exact patched provider and collector request paths. The supplied research highlights Settings Catalog policy CRUD, settings pagination, assignment reads and the separate assignment mutation. Confirm those paths in this candidate before implementing or changing them. Add reports, filters and group routes only when the actual journey exercises them.

Keep **committed service state**, **publicly visible service state**, and **client-observed state** distinct. A journal records whether mutation committed separately from whether a success response was delivered. A delayed-visibility scenario must serve the intended older observation, not merely delay a response while exposing new state everywhere.

Provide deterministic cases for denied/incomplete collection, cross-collection pagination, 429/retry exhaustion, policy success followed by assignment failure, commit followed by disconnect, stale plans, substitution, contention, and interrupted collection/execution/evidence recording. Record seed, rule ID and request counter. A snapshot-based lab pagination model is a reproducibility choice, not a claim about Microsoft Graph's consistency guarantees.

A private oracle URL alone does not establish independence. Enforce access isolation, use separately reviewed expected fixtures, avoid the product normalizer in the grader, and prove that wrong IDs, exclusions, filters, typed settings and missing objects fail. Compare desired configuration, engine state, service/oracle state and independently collected observations, with completeness/freshness assessed separately. No absence is actionable until the relevant collection is complete.

Persist collection runs, observations, typed relationships, deployment observations, operation identity and evidence links in the existing product store. Preserve last-good observations with explicit stale/partial status. Test graceful restart and abrupt termination separately; neither alone proves host power-loss durability. A hash chain also needs a trusted retained anchor if it is meant to detect wholesale history replacement.

### C.4 Exact provider execution boundary

First qualify launch of the unchanged candidate through actual OpenTofu RPC on an authorized socket-capable host. Verify its artifact digest and supported installation route, then perform the authorized native lifecycle with independent Graph readback. A development override or local mirror selects a binary; it does not solve a host socket prohibition or create an arbitrary Graph endpoint capability.

Inspect the candidate's cloud/client construction and every custom request helper before assuming endpoint injection. If a lab endpoint seam materially improves local fault tests, keep it in a separate lab build with separate version, package and evidence. Constrain its targets, keep test authentication out of the production artifact, and preserve normal TLS verification. Use a provider-compatible executable installation name even when the package/version clearly identifies the lab variant. Lab-build results cannot qualify the unchanged candidate's Entra authentication or native Intune behavior.

Do not block useful offline product work while the external host or tenant is unavailable. Record the narrower scope of each local journey and the exact missing provider stage.

### C.5 Implementation order and completion evidence

1. Confirm final tested delivery, supplement hashes and evidence links; preserve the candidate.
2. Map existing engine, service, collector, TUI, scripts, store and grading capabilities to requirements.
3. Add completeness-aware independent grading and negative controls; extend only missing adapter behavior.
4. Connect persistent inspection/history and closed-TUI collection to the actual application.
5. Drive actual scripts through reviewed exact-plan execution, readback, convergence and uncertain-outcome recovery in the declared lab profile.
6. Automate terminal interaction and record semantic state assertions alongside screen evidence.
7. Qualify unchanged provider RPC, native GitHub/Azure/Entra and authorized Intune/device paths as their prerequisites become available.

For every introduced tool, record the missing capability it closes, exact version/revision/digest, license, real invocation, qualification result and residual limits. New broad research is unnecessary. Open a narrow research question only when repository inspection, official documentation and a focused experiment leave a concrete unresolved decision.

## 18. Verification receipt for this document

Original preparation receipt, retained as historical evidence: executed on Linux with Python 3.12.14, using code extracted from this Markdown. The consolidation does not constitute a rerun of these tests:

| Check | Result |
|---|---|
| Offline reference scenarios | 11 passed |
| Separate-process recovery after committed change loses its response | Passed; no repeated mutation |
| Independent persisted-state checker | Passed |
| Checker negative control: remove exclusion | Correctly rejected |
| Embedded Python syntax, Bash syntax, JSON examples, SQLite schema | Passed |
| Reference self-test timing | 7 fresh-process samples; median about 44 ms |

The timing measures only this small reference self-test, not wizard performance or cloud throughput. YAML, PowerShell, dsoxlab, and external integration examples remain unexecuted templates. The independent checker confirms the fixture contract; it is not an independent model of Intune.

Executed Appendix A Python SHA-256: `f353fe562123c29e3aee4cf787528275b90e9e96cfc4c71da163a236f27f5518`.


These checks qualify the embedded reference examples only. They do not rerun the reported project suites, including the latest 967-pass extracted-source result or establish completion of the existing workbench. No GitHub workflow, `act`, Azure request, Graph request, Intune deployment, native PowerShell run, or live provider operation was executed to produce this document.

## 19. Paste-ready continuation instruction for the existing Work session

Continue the Intune engineering workbench using the existing implementation, this technical handoff and the supplied open-source qualification dossier. The next objective is a complete, independently graded maintenance journey through the actual terminal application and workflow scripts. We have enough research to proceed; investigate focused implementation questions as they arise.

**Preserve and reconcile the candidate.** The supplied transcript reports a successful final provider build from unchanged source, 55 named resource-method checks across 12 lifecycle groups, assignment-transition failing-before/passing-after evidence, 967 extracted-source passes with zero failures/errors and one required host skip, clean-extraction checks and byte-for-byte archive reconstruction. Verify the exact receipts and preserve valid evidence. Describe this as a built, integrity-verified candidate with resource-method evidence, not a production-qualified provider. Keep the strict release gate unsuccessful while a mandatory prerequisite remains unmet.

First finish the interrupted delivery: identify exact tested archives and digests, manifests, final evidence index and evaluator reconstruction supplement. The UI interruption alone does not prove artifact loss. Do not rebuild or rerun completed qualification without a relevant change or unresolved discrepancy. Preserve the previous host's Unix-socket EPERM failure, native Windows gap, durability findings, security-analysis limitations and tenant/device requirements.

**Apply the research selectively.** Inspect and extend the existing semantic model/service first. Add a narrow HTTP adapter only for missing routes, state and deterministic failures. Retain Azurite. Apply Appendix C's tool decisions: Floci/MiniStack supply no direct dependency for this path; defer Floci AZ without a demonstrated Azure gap. Prototype additional tools only against specific missing capabilities. Treat supplied versions, pins and commands as qualification inputs.

**Correct the integration examples before execution.** Resolve all ten Appendix C.2 defects: missing apply; cancellation scope; trusted deployment refs; grading before teardown; driver network access; native PowerShell exit handling; complete placeholder/file validation; real command mapping; separate Graph/backend/GitHub identities; and retained failure evidence. Keep privileged verifiers in a protected trust domain.

**Strengthen independent evidence.** Isolate the control/oracle interface, review expected fixtures separately, avoid sharing the product normalizer with the grader, and demonstrate known-bad rejection. Keep committed, visible and observed service state distinct. Test denied/incomplete reads, pagination escape, throttling, partial assignment mutation, lost responses, stale plans, substitution, contention and interruption. Preserve uncertainty until independent readback resolves it.

**Keep provider qualification explicit.** Launch the unchanged candidate with actual OpenTofu RPC on an authorized compatible host. Do not assume arbitrary Graph endpoint support. Inspect client construction and custom request helpers. Any justified lab-only endpoint build needs separate identity, packaging and evidence and cannot qualify production authentication or native Intune semantics. Continue useful offline work while external gates are blocked.

**Deliver the connected maintenance journey.** An engineer must be able to:

1. Open the terminal and inspect existing policies, including unmanaged policies.
2. Find a policy requiring investigation.
3. Understand its settings, targeting, ownership and incomplete evidence.
4. Trace repository definitions, inheritance and typed relationships.
5. Compare historical observations.
6. Prepare an intentional correction without unrelated changes.
7. Review and execute the exact operation through the appropriate workflow.
8. Inspect independent readback and a no-change second plan.
9. Recover from an interrupted or uncertain outcome.
10. Close the terminal, run scheduled collection and reopen updated health, history and maintenance views.

Keep service acceptance, reporting coverage, endpoint application and endpoint health separately represented. Report three distinct outcomes: laboratory journey with identified emulated dependencies; platform qualification with actual host/GitHub/Azure/Entra/provider/Intune evidence; and organization-specific production approval.

Wally remains optional. Preserve its reported 87 completed reviews, nine timeouts and lack of demonstrated benefit. Do not delay delivery to obtain a positive result.

Deliver updated source, reproducible real commands, connected-journey evidence, a requirement-to-evidence ledger and precise remaining blockers. Request further research only for a specific unresolved question. Do not weaken gates or restart completed work merely to align with older instructions.

This consolidation preserves all original executable reference blocks and 17 runbooks. Section 18's original receipt applies only to those reference examples; it does not validate the new integration requirements or the other Work session's artifacts.
