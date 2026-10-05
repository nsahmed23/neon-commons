# Enterprise Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Advance the actual plugin toward every enterprise gate in `docs/ENTERPRISE-GOAL.md`, with implemented capabilities and independently checked evidence.

**Architecture:** Separate authenticated observations, target consistency, execution authorization, irreversible operation outcomes and workflow progress. Offline contracts cannot grant external execution. Fixed adapters and independent readback connect these layers; the optional judge stays advisory.

**Tech Stack:** Python 3.12, existing pinned dependencies, Atmos 1.199.0, OpenTofu 1.10.0 and Deployment Theory microsoft365 1.0.0 for the existing qualification baseline.

**Spec:** `docs/ENTERPRISE-GOAL.md`, `docs/PRODUCT-STATUS.md`, and the original correction contracts.

## Global Constraints

- Preserve immutable identity, policy values, all direct targeting tuples and field accounting. Do not renumber settings or broaden a provider support claim without evidence.
- Unsupported, missing, denied, stale or unauthenticated evidence blocks the dependent action. Local JSON claims are consistency evidence, never authenticated approval.
- No arbitrary shell or user-supplied executable arguments. No force, skipped-plan, disabled-lock or target substitution escape hatches.
- Credentials and raw unsupported source values must not enter model-visible output or ordinary receipts. Bound filesystem and transport inputs.
- All external actions remain unqualified until concrete approved execution evidence exists. Never infer atomic policy/assignment or multi-state operations.
- Work in disjoint owned paths; agents do not commit or spawn other agents. Root integrates, commits, and assigns independent review. Parallel work is explicitly requested by the user.

## Review Focus

- A saved success or changed artifact must not be accepted as fresh execution authority.
- Duplicate identities, partial observations and stale readbacks must retain unknown outcomes.
- Unknown future plan formats or changes must fail closed rather than disappear from effects.
- A changed cohort, stack or backend must invalidate dependent milestones without advancing the saved frontier.
- An action may have succeeded remotely despite a failed response or failed receipt write; retries require reconciliation.

### Task 1: Selected provider source and request/state harness

**Files:** create `research/provider-qualification/`, `labs/provider-contract/`, `scripts/qualify-provider-contract.py`, and `plugin_tests/test_provider_contract_lab.py`; no production mapper edits without root coordination.

**Interfaces:** a standalone qualification entrypoint returns machine-readable observed checks, exact source identities, failures and remaining service/native boundaries. Exercise real upstream code when feasible; otherwise label reimplementations as models.

- [x] Trace pinned validator, SDK setting/Entity serializer, JSON normalization, state mapping, pagination and assignment construction to raw source and hashes.
- [x] Write counterexamples for wrapper/id/null/order/default and partial-request outcomes before treating the path as qualified.
- [x] Implement a source-level or transport harness that runs actual selected code without a cloud call where possible; record exact failure if unavailable.
- [x] Run scoped tests; report provider configuration/state differences and the smallest safe mapper correction if justified.

### Task 2: Effective target evidence

**Files:** create `intune_iac/target.py`, `plugin_tests/test_target.py`, `docs/TARGET.md`, `research/enterprise-target/`; root owns CLI wiring.

**Interfaces:** `inspect_target(document: dict) -> dict` and `compare_targets(expected: dict, observed: dict) -> dict`, with explicit assurance and blockers. Input is a strict versioned evidence document; no input claim alone may authenticate itself.

- [x] Research upstream Atmos/Azure backend/authenticated identity patterns from pinned primary code/docs.
- [x] Test complete structured binding: cloud/endpoints, tenant/principal/client/federation, logical stack/component/revision, backend storage identity/endpoint/container/key/workspace/resolved blob, state lineage/serial and writer ownership.
- [x] Implement bounded strict inspection/comparison with path-level mismatch reasons and safe outputs. Native observation or authenticated collection may be added only with separately identified authority and tests.
- [x] Test omission, unknown fields, nulls, wrong origin, malformed IDs, all field mutations and spoofed assurance; report actual authenticated boundary.

### Task 3: Plan review and protected execution protocol

**Files:** create `intune_iac/execution.py`, `intune_iac/reconciliation.py`, `plugin_tests/test_execution.py`, `plugin_tests/test_reconciliation.py`, `docs/EXECUTION.md`, `research/enterprise-execution/`; root owns CLI/runner integration.

**Interfaces:** `review_plan(document: dict) -> dict`; a fixed typed orchestration API with injected qualified adapters (not arbitrary command strings); durable operation receipt and independent readback reconciliation. Document exact additional signatures before integration.

- [x] Research actual upstream saved-plan, approval, lock and failure-recovery designs; pin reused facts.
- [x] Test destructive/replacement/unknown/sensitive/deferred effects, import identity, drift and no-change, version parsing, missing fields and changed plan/config/tool/target fingerprints.
- [x] Implement conservative plan review and durable operation/reconciliation APIs, fail-closed authorization, separate policy/assignment outcomes and interrupted-state classification. If a safe native adapter is feasible, implement and qualify a bounded local one without promoting it to cloud authority.
- [x] Fault-inject fail-before, fail-after, lost response, readback mismatch, receipt failure and concurrent attempts; no automatic replay of uncertain actions.

### Task 4: Receipt-backed guided progress

**Files:** own `intune_iac/wizard.py`, new `intune_iac/workflow.py`, `plugin_tests/test_workflow.py`, `docs/WORKFLOW.md`; coordinate CLI changes with root.

**Interfaces:** versioned progress and receipt reconstruction consumed by the existing wizard; saved session fields remain hints, never approvals. Actual files and dependency digests must be reread before completion is supplied to the resume algorithm.

- [x] Read correction resume/oracle contracts and existing wizard; reproduce missing receipt/frontier/invalidation cases.
- [x] Implement receipt store and milestone reconstruction, frontier intersection, dependency invalidation, cohort and partial-generation routing. Integrate reachable safe user flows into existing wizard rather than supplying only another isolated model.
- [x] Test object_selection plus changed cohort stays there; partial_generate plus changed stack stays on partial path; missing/tampered/synthetic receipts cannot advance; old sessions safely migrate or reject explicitly.
- [x] Run real CLI or PTY journey plus scoped tests; document remaining live stages without fabricated completion.

### Task 5: Independent security and package audit

**Files:** report outside runtime; root adds selected report to source evidence after inspection. No simultaneous production edits by auditor.

- [x] Run Codex Security Standard preflight and audit workflow or report exact blocker and use a clearly labeled independent source audit.
- [x] Audit baseline evidence, paths, hostile captures, transport, session/runner trust and new execution trust boundaries when ready.
- [x] Validate exploitability with bounded local reproductions. Feed findings to owners, then independently review fixes.
- [x] Run Plugin Eval structural analysis; do not invent publisher policy URLs to improve score or invoke paid benchmarks implicitly.

### Task 6: Integration, adversarial review and release evidence

**Files:** root owns `intune_iac/cli.py`, release inventories/version/docs and release qualification artifacts.

- [x] Expose completed safe capabilities through CLI, preserve old behavior and state exact boundaries in doctor/status.
- [x] Delegate independent task and whole-change review; repair material findings with covering tests.
- [x] Run full verifier and relevant native/CLI/PTY qualification once changes stabilize; preserve failed receipts.
- [ ] Build deterministic runtime/source archives, test clean extraction, verify hashes, save code/reports and keep all unpassed enterprise gates open.
- [x] Execute further independent engineering revealed by reviews; isolate exact environment/organization dependencies for the remaining pilot and acceptance.

## Source-freeze status

Tasks 1–5 and local integration are implemented and reviewed within the documented scopes. The final archive/extraction/persistence step is recorded in the separately delivered 0.3.0 archive receipt after this source snapshot is built, avoiding self-referential archive hashes. Enterprise gates remain open; see `docs/ENTERPRISE-EXECUTION-LEDGER.md`.
