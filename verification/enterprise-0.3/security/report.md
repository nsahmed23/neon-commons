# Security Review: intune-iac-plugin

## Scope

Partial critical-runtime source audit with bounded synthetic reproductions and independent review of all four repairs.

- Scan mode: repository
- Target kind: git_worktree
- Target ID: target_sha256_824526ce876babeff230cd23cea344b27067ac1396ccea2c3d87348f2cae47b5
- Revision: 3fbfae8f986feda036c6fdb14257be6ad1c5b826
- Snapshot digest: codex-security-snapshot/v1:sha256:6b9fd43bda790f85ffe744f244d7dfc53f59dbdb48757af913260173749a0dea
- Inventory strategy: repository
- Included paths: .
- Excluded paths: none
- Artifacts reviewed: intune_iac/__init__.py, intune_iac/io.py, intune_iac/capture.py, intune_iac/mcp.py, intune_iac/cli.py, intune_iac/engine.py, intune_iac/runner.py, intune_iac/judge.py, intune_iac/repository.py, intune_iac/production.py, intune_iac/production_oracle.py, intune_iac/atmos.py, intune_iac/graph.py, intune_iac/wizard.py, intune_iac/target.py, intune_iac/workflow.py, intune_iac/execution.py, intune_iac/reconciliation.py, scripts/verify-dependencies.py
- Scan context: Can you create a goal for yourself to not stop working until it’s acceptable for production use in an enterprise environment? Use whatever plugins or skills you have access to to critically plan it and then fan out subagents to execute a plan of action to finish this “goal”. Comb through as many repos and do as much as deep research as needed. Delegated security scope: critical audit all execution/identity/preservation/host boundaries; no cloud operations. Source audit offline.

Limitations and exclusions:
- Whole-repository coverage partial; historical and fixture corpus not exhaustively reviewed.
- Concurrent working-tree implementation; baseline findings and repair snapshots distinguished in artifacts/fix-review.md.
- No nested independent baseline worker available; degraded-worker preflight path used.
- This source audit does not establish enterprise production readiness or organizational approval.

### Scan Summary

| Field | Value |
| --- | --- |
| Scan outcome | completed |
| Reportable findings | 4 |
| Severity mix | low: 4 |
| Confidence mix | high: 4 |
| Coverage | partial |
| Validation mode | Source-backed bounded reproductions plus independent source review of owner repairs. |

Canonical artifacts: `scan-manifest.json`, `findings.json`, and `coverage.json`. This report is a deterministic projection of those files.

## Threat Model

Local Python CLI/MCP plugin consumes caller-selected Intune captures and Atmos repositories, preserves bounded observations, emits inactive production candidates, and records local attempts. New guided receipt reconstruction, strict target consistency checks, fixed authenticated GET observations, conservative plan review and local fixture simulation were reviewed. No production cloud mutation adapter is enabled.

### Assets

- Captured tenant/policy identities, accepted settings and targeting tuples; generated project confidentiality and integrity.
- Source provenance, output ownership, wizard progression and operation receipt integrity.
- Explicit Graph bearer token and optional CLM credential; raw input confidentiality.

### Trust Boundaries

- Untrusted local JSON -\> parse_json regular-file/size/duplicate-key/depth checks (intune_iac/io.py:29-73); CLI/MCP only fixed routes (intune_iac/mcp.py:21-57).
- Untrusted repository -\> inert YAML AST and bounded literal merge; raw effective values stay internal and public projection omits them (intune_iac/repository.py:116-263,431-565).
- Capture -\> GET-only Graph allowlisted origin/path with no redirects and restricted dirfd persistence (intune_iac/capture.py:41-99,128-252).
- CLM claim/evidence -\> explicit configured endpoint, no redirects/proxy inheritance, advisory result cannot authorize execution (intune_iac/judge.py:110-136,251-282,315-384).
- Projection -\> owned local output transaction; new generated POSIX directories are now 0700 and files 0600. Existing output is preserved rather than chmodded (reference/core.py).
- Local action proposals -\> fixed registry dispatch, evidence reread and exclusive cooperative target locks; unknown writes retain locks (intune_iac/runner.py:17-29,174-211,300-378).
- Guided session -\> canonical input/output scopes and cooperative lock -\> reread session and artifacts -\> verified local milestones. Completion never grants external execution authority (intune_iac/workflow.py).
- Caller-supplied target claims -\> strict snapshot/schema/endpoint comparison; optional collector only fixed Graph and Azure management GETs. Neither self-reported fields nor collected subset authenticate principal, federation, state ownership or approver (intune_iac/target.py).
- Plan JSON -\> conservative typed effect review with denominator and known-value consistency; provenance remains caller-supplied and result cannot authorize execution (intune_iac/execution.py).
- Local fixture operation -\> exact concrete adapter, fixed facet files, durable strict event-prefix receipt chain and retained lock on unknown outcome; reconciliation reads independent local state and cannot unlock/retry automatically (intune_iac/execution.py, reconciliation.py).
- Vendored wheelhouse -\> exact lock, bounded ZIP metadata/name/version/hash inspection; no extraction/install/execute and no publisher authentication or vulnerability assessment (scripts/verify-dependencies.py).

### Attacker Capabilities

- Can supply a malicious capture, graph, or repository for operator review; cannot assume control of process code, host credentials or trusted operator configuration.
- Separate unprivileged local user may traverse a shared output parent; cannot initially read restricted capture files.
- Remote judge service can return malformed/delayed responses after operator explicitly selects that endpoint.

### Security Objectives

- Unsupported/missing/denied data must not silently become empty desired state or execution authority.
- Prevent source-derived code execution and out-of-scope filesystem overwrite.
- Preserve accepted sensitive observations in owner-restricted generated files.
- Local digests and receipts establish consistency, never authentication or organizational approval.

### Assumptions

- No cloud call or actual credentials used in audit; bounded synthetic local reproduction explicitly authorized by parent.
- Parent assigned all concurrency slots elsewhere and prohibited nested workers; sequential baseline and architecture review are not independent.
- Cooperative local filesystem for ordinary runtime; no adversarial writable-ancestor race isolation guarantee.
- Whole repository requested; this audit fully read 19 critical runtime/auditor source files and selected supporting code/tests, but historical research, all fixtures and the full repository were not exhaustively audited. Changes were reviewed incrementally while implementation owners worked.

## Findings

| Finding | Severity | Confidence | Detailed write-up |
| --- | --- | --- | --- |
| [Parent-directory aliases let guided checkpoints overwrite protected capture inputs](#finding-1) | low | high | inline below |
| [Generated projects publish accepted capture values with world-readable defaults](#finding-2) | low | high | inline below |
| [Public per-field digests disclose low-entropy restricted values by enumeration](#finding-3) | low | high | inline below |
| [Small imported captures trigger repeated whole-bundle graph work](#finding-4) | low | high | inline below |

### Confidence Scale

| Label | Meaning |
| --- | --- |
| high | Direct evidence supports the finding with no material unresolved blocker. |
| medium | Evidence supports a plausible issue, but material runtime or reachability proof remains. |
| low | Evidence is incomplete and the item is retained only for explicit follow-up. |

<a id="finding-1"></a>

### [1] Parent-directory aliases let guided checkpoints overwrite protected capture inputs

| Field | Value |
| --- | --- |
| Severity | low |
| Confidence | high |
| Confidence rationale | Direct source trace; implementation owner reproduced raw capture overwrite in regression before fix and independently reviewed canonicalization after fix. |
| Category | path-traversal |
| CWE | CWE-23, CWE-180 |
| Affected lines | intune_iac/workflow.py:28-32, intune_iac/workflow.py:88-101 |

#### Summary

Initial workflow._safe returned absolute but noncanonical paths. A source inside the receipt store spelled through x/.. evaded lexical _scopes checks, and an ordinary checkpoint overwrote the source capture as inventory.json. The working-tree fix canonicalizes paths after rejecting symlinks. Fixed during this audit; the code evidence records the vulnerable version observed before repair.

#### Root Cause

Path normalization occurred after neither path selection nor lexical persistence/input overlap comparisons.

#### Validation

Owner test_parent_alias_cannot_hide_source_inside_evidence returned suspended instead of blocked and overwrote capture before fix. Example /base/x/../session.json.evidence/inventory.json aliases source under /base/session.json.evidence; x is existing directory. Fix source independently inspected.

#### Dataflow

Supplied source path with x/.. -\> absolute-only _safe -\> lexical _scopes misses overlap -\> _checkpoint writes evidence/inventory.json over source.

#### Reachability

Caller can supply initial guided input locator or resume state. Input must be valid capture and alias actual evidence filename; normal local checkpoint is sufficient.

#### Severity

**Low** — Local source-integrity loss requires a crafted path/session selected by the operator; no arbitrary remote execution or privileged filesystem write established.

Additional runtime or deployment evidence could raise or lower this severity.

#### Remediation

Canonicalize filesystem locators after rejecting symlink components and before comparing scopes; preserve source bytes and reject overlapping receipt/output paths before writes.

Tests:
- Capture supplied through parent alias into evidence is rejected with unchanged original bytes.
- Saved state reread after acquiring wizard lock avoids stale cancelled intent.

<a id="finding-2"></a>

### [2] Generated projects publish accepted capture values with world-readable defaults

| Field | Value |
| --- | --- |
| Severity | low |
| Confidence | high |
| Confidence rationale | Direct source trace and bounded synthetic reproduction observed exact file/directory modes. |
| Category | insecure-file-permissions |
| CWE | CWE-732, CWE-276 |
| Affected lines | reference/core.py:518-524, intune_iac/engine.py:128-145 |

#### Summary

On POSIX with umask 0022 and a searchable shared output parent, write_project publishes generated directories as 0755 and files as 0644. A separate local UID can read accepted capture values and identifiers that were restricted in the original capture. Fixed during this audit; the code evidence records the vulnerable version observed before repair.

#### Root Cause

Private staging parent protects construction, but the inner project is created with permissive defaults and then relocated outside that private parent.

#### Validation

Synthetic probe artifacts/permissions_probe.py executed with umask0022: generated and generated/review0755, normalized.json and generated-files.json0644. No real capture or tenant used.

#### Dataflow

Operator-selected capture -\> engine._expected_files review content -\> write_project -\> mode0644 files in0755 generated project.

#### Reachability

Requires destination ancestors searchable by another local UID. Private home/workspace ancestors mitigate; file modes permit disclosure once shared parent is chosen.

#### Severity

**Low** — Local confidentiality exposure requires another host user plus a searchable shared parent. No write escalation, remote exposure, or cloud mutation is established.

Additional runtime or deployment evidence could raise or lower this severity.

#### Remediation

Create new generated project directories explicitly0700 and files0600, including ownership manifest. Preserve existing user-owned output and surface overly permissive existing output for review instead of silently modifying it.

Tests:
- With umask0000 and0022, newly generated production/synthetic output directories0700 and files0600.
- Existing output remains unchanged on conflict and is not silently chmodded.

<a id="finding-3"></a>

### [3] Public per-field digests disclose low-entropy restricted values by enumeration

| Field | Value |
| --- | --- |
| Severity | low |
| Confidence | high |
| Confidence rationale | Counterexample unsupported private_pin0042 remained absent in plaintext, passed independent preservation oracle, and was recovered from normalized hashes in0.057seconds. |
| Category | sensitive-data-exposure |
| CWE | CWE-200 |
| Affected lines | intune_iac/production.py:209-213, intune_iac/production_oracle.py:412-416 |

#### Summary

Production field accounting includes an unsalted digest of each unsupported/restricted source value. A review recipient can enumerate small value spaces without receiving the raw field, defeating restricted retention for low-entropy values. Fixed during this audit; the code evidence records the vulnerable version observed before repair.

#### Root Cause

Deterministic unkeyed hashes serve as equality oracles for low-entropy confidential values; labeling them restricted does not remove the leak.

#### Validation

restricted_digest_probe.py adds a synthetic unsupported private_pin0042. Mapping remains blocked, plaintext absent, independent oracle returns no errors. Enumerating0000–9999 against public restricted source hashes recovered0042.

#### Dataflow

Unsupported raw field -\> _accounting canonical SHA256(value) -\> normalized review/MCP inspect output -\> dictionary enumeration by review-only recipient.

#### Reachability

A recipient needs the ordinary normalized review but not original capture or host privileges. Low entropy is required. Public whole-source digests can also be equality oracles if all other source material is reconstructable.

#### Severity

**Low** — Requires a sensitive low-entropy value in an unsupported field and a recipient with access to the review output but not raw input; no credential reuse or deployment exposure demonstrated.

Additional runtime or deployment evidence could raise or lower this severity.

#### Remediation

Avoid public per-value/container digests for restricted and unselected source content; rederive preservation from restricted original bytes. If cryptographic confidentiality is required when all other input is known, keep keyed integrity evidence outside review; public salts are insufficient.

Tests:
- Unsupported low-entropy scalar and container digests are absent from public review.
- Independent preservation oracle continues detecting dropped/changed mapped fields.
- Version and document field-accounting contract change.

<a id="finding-4"></a>

### [4] Small imported captures trigger repeated whole-bundle graph work

| Field | Value |
| --- | --- |
| Severity | low |
| Confidence | high |
| Confidence rationale | Source loop and bounded measured20/40/80policy reproduction demonstrate superlinear amplification. |
| Category | resource-exhaustion |
| CWE | CWE-400 |
| Affected lines | intune_iac/graph.py:162-183, reference/core.py:138-141 |

#### Summary

build_graph invokes whole-capture normalization for every distinct policy without a total policy-by-source work budget. This amplifies a caller-supplied capture and blocks the sequential local MCP worker or CLI. Fixed during this audit; the code evidence records the vulnerable version observed before repair.

#### Root Cause

Per-file16MiB bound does not limit multiplicative whole-source normalization across policy count.

#### Validation

Bounded synthetic graph_budget_probe.py:20policies12,343bytes0.425seconds;40policies23,283bytes1.325seconds;80policies45,163bytes4.636seconds. All generated graphs completed; no load test or real tenant used.

#### Dataflow

Caller-supplied capture -\> build_graph candidates -\> full-source normalize/oracle per policy -\> repeated CPU/allocations.

#### Reachability

Local graph build is exposed through CLI and fixed MCP local action. MCP serves requests sequentially. A user must choose the input; no remote autonomous ingestion assumed.

#### Severity

**Low** — Requires operator import of attacker-controlled local capture; availability impact only and no demonstrated remote exposure.

Additional runtime or deployment evidence could raise or lower this severity.

#### Remediation

Enforce total parsed-node/candidate/work budgets before expensive projection, reject complete input with a safe reason rather than truncating it, and index shared source facts once. Bound query validation costs too.

Tests:
- Oversized policy-times-source input rejected before first normalization.
- Preserve all policy coverage denominator; no truncated success.
- Small supported fixtures still reproduce.

## Reviewed Surfaces

| Surface | Risk Area | Outcome | Notes |
| --- | --- | --- | --- |
| Fixed CLI/MCP and local runner | not recorded | No issue found | No arbitrary shell or cloud action entrypoint in baseline; inactive adapters explicit. Local receipts/digests not treated as authenticated approval. |
| Capture and judge transport | not recorded | No issue found | Graph route/origin and redirects checked; CLM advisory only. Slow-drip wall-clock bound remains an open robustness question. |
| Generated artifact confidentiality | not recorded | Reported | Validated local permission exposure; sent to root for repair. The repair was independently source-reviewed and is recorded as fixed in the working tree. |
| Literal Atmos parsing and projection | not recorded | No issue found | Safe YAML composition, import/path/value restrictions and known limits present; no native execution. |
| Imported graph resource budgets | not recorded | Reported | Bounded local benchmark validated amplification; sent to root. The repair was independently source-reviewed and is recorded as fixed in the working tree. |
| Restricted source value disclosure | not recorded | Reported | Synthetic dictionary recovery validated; sent to root. The repair was independently source-reviewed and is recorded as fixed in the working tree. |
| Guided persistence and input scope | not recorded | Reported | Parent alias overwrite found, reproduced by owner, canonicalization fix independently reviewed. The repair was independently source-reviewed and is recorded as fixed in the working tree. |
| Strict target evidence and optional fixed GET collection | not recorded | No issue found | Reviewed endpoint/token transport, snapshot and control-character fixes; explicit unqualified identity/backend boundaries retained. No network calls or credentials used by auditor. |
| Plan review, local fixture execution and reconciliation | not recorded | No issue found | Correctness defects in typed equality, event schema/sequence and output denominator were sent to owner; repairs independently reviewed. Only local concrete adapter exists, uncertain outcomes retain locks. |
| Vendored dependency read-only integrity verifier | not recorded | No issue found | Bounded exact lock/ZIP metadata verification reviewed. It does not assess publisher authenticity or known vulnerabilities. |
| CLI typed outcome exit status | not recorded | No issue found | Initially missing locked/reconciliation_required failure mapping was sent to root; final source returns exits 4 and 3 respectively, preventing false CLI success. |

## Open Questions And Follow Up

- Ordinary runtime uses cooperative filesystem checks; adversarial concurrent ancestor replacement is not isolated.
- Capture and optional judge slow-drip wall-clock behavior was not fully qualified. Target collector adds a post-connect absolute deadline but retains OS-resolver-bounded DNS.
- Whole-source hashes establish equality and can disclose guesses when all other source bytes are reconstructable; strong secret confidentiality requires a separately protected integrity mechanism.
- Requested whole-repository coverage remains partial: critical runtime and new trust boundaries reviewed, but historical research, every fixture and all repository source files not exhaustively audited.
  - Follow-up prompt: Review deferred unit deferred-c381a91755993bf6 and close its stated proof gap.
- No native host installation, Windows ACL/native PowerShell behavior, cloud provider execution, authenticated approval integration or live Azure/Intune acceptance was qualified by this source audit.
  - Follow-up prompt: Review deferred unit deferred-fe2cea6780b8fe87 and close its stated proof gap.
- No independent nested baseline/architecture worker was available because all team slots were allocated and parent prohibited nested delegation. Sequential review followed preflight's degraded-worker path.
  - Follow-up prompt: Review deferred unit deferred-64ff740319fc6d84 and close its stated proof gap.
- New execution, target and workflow modules still being authored; review after ready.
  - Follow-up prompt: Review deferred unit deferred-520a3eede1b3635c and close its stated proof gap.
- Full repository fixtures/research/historical documents not reviewed exhaustively; requested whole-repo coverage is partial.
  - Follow-up prompt: Review deferred unit deferred-431d0248af8384af and close its stated proof gap.
