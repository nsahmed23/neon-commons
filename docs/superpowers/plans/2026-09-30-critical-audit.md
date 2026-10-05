# Critical audit remediation implementation plan

> **For agentic workers:** Use Superpowers audit, test-driven development, and verification-before-completion. Track each reproduced defect through a failing regression, fix, and independent review.

**Goal:** Repair reproducible defects in v0.2.0 and publish a truthful product completion assessment with a reproducible maintenance release.

**Architecture:** Keep the existing local-only runner, independent preservation checks, and inactive production candidates. Repair the evidence boundaries and interfaces without inferring provider or service correctness from local tests.

**Tech Stack:** Python 3.12, unittest, pinned runtime dependencies, Plugin Eval static analysis, local Git.

**Spec:** User request to critically audit and fix the plugin; current correction requirements in `corrections/CORRECTION-SPEC.md`, runtime contracts in `docs/`, and original brownfield Intune/Atmos product scope.

## Global constraints

- Never convert unavailable or partial collections into an empty desired collection.
- Do not emit executable production adoption output without provider and target qualification.
- Preserve unsupported raw content only in restricted original input; public review uses safe references.
- Saved session state and hashes establish consistency, not approval or artifact existence.
- Report incomplete features separately from reproducible defects and environment qualification.
- Keep historical evidence immutable in meaning; mark superseded claims explicitly.

## Review focus

- Contradictory counts, assignment indicators and duplicate identities must invalidate completeness.
- Saved review states without generated artifacts must not finish successfully.
- Unresolved Atmos dependencies must remain visible, and base paths must select the actual manifest.
- Invalid MCP initialization must produce a protocol error without terminating the process.
- Untracked captures, credentials and symlink targets must not enter release archives automatically.

## Tasks and evidence

### Task 1: Preservation and intake

Files: `reference/core.py`, `reference/invariants.py`, `intune_iac/production.py`, `intune_iac/production_oracle.py`, new preservation regression tests.

- [x] Reproduce count and isAssigned contradictions against the original implementation.
- [x] Independently reject contradictions in producer and oracle; examine missing assignment provenance and field destination lineage.
- [x] Run targeted regressions and preservation mutation checks; review the fix diff.

### Task 2: Atmos relationships

Files: `intune_iac/graph.py`, `intune_iac/atmos.py`, resolver if needed, new Atmos regression tests.

- [x] Reproduce wrong base_path import edge, dropped unresolved dependencies, and falsely resolved aggregate status.
- [x] Repair relationship target resolution and propagate unresolved/blocked states through queries.
- [x] Run targeted tests and review the graph semantics changes.

### Task 3: Wizard and persistence

Files: `intune_iac/wizard.py`, runner or persistence if needed, new workflow regression tests.

- [x] Reproduce fabricated handoff completion and null-conflict failure.
- [x] Require fresh output verification before finish, validate persistent state, and prevent path collisions or concurrent session overwrite.
- [x] Run resume, concurrency and file-preservation regressions; review failure recovery.

### Task 4: MCP and collector boundaries

Files: `intune_iac/mcp.py`, `intune_iac/capture.py`, protocol docs and regression tests.

- [x] Reproduce malformed initialize process termination and false collector completeness.
- [x] Validate protocol lifecycle and reconcile collection counts/identities conservatively.
- [x] Run subprocess protocol and injected-transport regression tests; review explicit limits.

### Task 5: Distribution and instructions

Files: `scripts/build-release.py`, `release-source-files.txt`, `intune_iac/cli.py`, release/CLI regression tests; skill, capture docs, historical status headers and `docs/PRODUCT-STATUS.md`.

- [x] Prove untracked sensitive-shaped files and symlink parents can enter the old source release.
- [x] Replace recursive source collection with an explicit reviewed file inventory; reject unsafe paths and output aliases within the checkout.
- [x] Make missing-dependency exit status match the documented contract.
- [x] Correct repository-first instructions, label historical evidence, and create a product requirement matrix.
- [x] Run targeted tests and review packaging/instructions.

### Task 6: Integrated verification and release

- [x] Run fresh full core/runtime suite and relevant CLI/PTY/repository workflows.
- [x] Conduct independent review of the combined fix diff; resolve findings.
- [ ] Build version 0.2.1, verify exact archive membership/hashes, extract cleanly, run source suite and runtime workflows from extraction.
- [x] Re-run Plugin Eval; retain genuine unresolved listing, complexity and behavioral qualification findings.
- [ ] Save runtime/source archives, audit and execution report, action plan and receipt.

## Execution decisions

The existing isolated feature worktree is retained. Independent reviewers own disjoint files while implementing confirmed findings, as authorized by the request to execute fixes; the root reviews integration and a fresh final reviewer checks the complete diff. No plan-approval pause is needed. Public listing URLs, native host/model evidence, provider roundtrips and tenant authorization cannot be fabricated to close findings.

## Progress

Baseline: 379/379 tests passed. Confirmed audit defects were reproduced and repaired; fresh final review found no unresolved findings in its scope. Final integrated suite: 435/435 passed; CLI 11 checks, repository 7 checks and Linux PTY passed. Plugin Eval remains failed at 26/F with real unresolved publishing/maintainability/behavioral gates. The final packaging and delivery steps are recorded in the separately delivered versioned archive receipt after this source snapshot. Completion checkboxes will be updated only after fresh evidence.
