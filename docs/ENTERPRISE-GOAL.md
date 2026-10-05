# Enterprise production goal

Status: **open — not production ready**. Baseline: release 0.2.2, commit `3fbfae8f986feda036c6fdb14257be6ad1c5b826`. Reference engineering checkpoint: 0.3.1. The intended product remains the Intune adoption plugin and wizard. See `ENTERPRISE-EXECUTION-LEDGER.md` for prior progress.

Deliver an interactive Intune-to-Atmos/OpenTofu adoption and operations plugin that an enterprise can approve for its declared support matrix. An operator must be able to preserve existing policy identity, settings, inclusions, exclusions and filters; resolve the actual stack, backend, credentials and writer; review the exact planned effects; execute through protected controls; and recover from partial or uncertain outcomes without blind replay.

This goal is not satisfied by a research pack, local model, high test count, static plugin score, or successful synthetic lab. Required evidence must be attributable to the actual shipped implementation and exact dependency versions. No closure is inferred from a specification. The goal remains open across engineering checkpoints; a checkpoint is not release acceptance.

## Acceptance gates

| ID | Required outcome | Acceptable evidence | Baseline |
|---|---|---|---|
| E01 | Declared estate and support denominator | Named families, setting forms, targeting, exporter/provider/engine/Atmos versions, cloud/backend, hosts/platforms, limits and unsupported counts | One setting candidate; enterprise denominator not established |
| E02 | Provider and service preservation | Actual selected-provider serialization/refresh tests, schema validation, import, ordinary and refresh-only no-change, complete pagination and assignment semantics | Source evidence and local init; startup and live gates open |
| E03 | Effective identity, target and ownership | Authenticated endpoint/tenant/principal plus repository/backend/blob/workspace/state lineage/serial and single writer; explicit unknowns block effects | Literal repository evidence only |
| E04 | Protected execution | Exact plan/config/tool/target binding, protected approval, last-moment comparison, native lock and operation lock, restricted credentials, durable receipts | Local actions only |
| E05 | Recovery | Fault-injected separate policy/assignment and state/history outcomes; independent readback; no blind replay after unknown outcome | Contracts and local unknown-outcome handling |
| E06 | Guided adoption | Receipt-backed milestones, cohorts, partial generation, prerequisites, edit/resume invalidation, conflicts and reconciliation | Single-policy local authoring wizard |
| E07 | Adversarial quality | Independent preservation tests, bounded inputs, invalid/denied/partial captures, concurrent/interrupted execution, independent code/security review | 466 local tests and bounded native labs |
| E08 | Host/platform/behavior acceptance | Native install/use/uninstall and agent-driven tasks on every supported host/platform; optional judge calibrated separately | CLI/MCP/Linux PTY only |
| E09 | Enterprise operations | Organization-approved CI identity/review/concurrency, incident recovery, support owner, vulnerability/update policy, reproducible release/dependency integrity | Offline examples and reproducible archives |
| E10 | Authorized pilot and release decision | Named nonproduction tenant and existing policy; observed preservation, recovery and ring promotion; accountable enterprise acceptance | Not run |

## Execution policy

Implement and verify all independent work available in the current environment. Acquire public source as needed, pin identities, distinguish code inspection from execution, and use independent reviewers. Keep failures and counterexamples. Never rewrite goldens to hide a failed preservation assertion.

External effects require concrete target scope and protected authorization. Missing tenant access, native hosts, authentic approvals or enterprise decisions remain visible dependencies; they do not stop independent engineering. No paid model inference, tenant mutation, external publication or production deployment is inferred from this goal.

The planned production boundary is a supported, declared slice that can expand with evidence. A narrow pilot does not complete the broader requested estate. Arbitrary repository code is executable input; an LLM judge is advisory and cannot supply missing authorization or override deterministic checks.

## Current work

See `superpowers/plans/2026-09-30-enterprise-execution.md` and `ENTERPRISE-EXECUTION-LEDGER.md`. Gates are reported as open, implemented-unqualified, qualified within stated scope, or accepted. Only observed acceptance evidence may advance a gate to accepted.


