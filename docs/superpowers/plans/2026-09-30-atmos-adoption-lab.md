# Atmos Adoption Lab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Exercise native local state adoption through Atmos and use independently reviewed upstream labs to expose and repair workflow defects.

**Architecture:** Keep upstream acquisition and content audits separate from the original lab implementation. Run pinned Atmos and OpenTofu against a disposable local backend and built-in terraform_data resources, then compare native results with the plugin's repository analysis. Record command results and assertions; passing local simulations do not qualify Intune behavior.

**Tech Stack:** Python 3.12, unittest, Atmos 1.199.0, OpenTofu 1.10.0, local filesystem backend.

**Spec:** The user requests open-source lab research, critical audit, implemented fixes and robust executable workflow simulation. Acceptance requirements are recorded below.

## Global Constraints

- Never operate on the user's estate, existing state, credentials or repository through the lab runner.
- Use a fresh output directory, isolated environment and fixed commands; inspect source before executing it.
- Record all 88 catalog lab contracts, test sources and fixtures; encrypted solutions remain explicitly uninspected.
- Distinguish source inspection, upstream execution, native local execution and Intune qualification.
- Independently review changes; repair reproduced correctness failures before packaging.

## Review Focus

- Existing output and symlink paths must not allow overwritten data.
- Inherited process variables must not redirect state, backend, CLI configuration or credentials.
- A zero exit code must not substitute for checking plan actions and state identity.
- Stack selection and configuration precedence must match native behavior or remain blocked.
- Imported identity must not imply settings preservation or no-change adoption without observed plans.

### Task 1: Source acquisition and content audit

**Files:** `research/terraform-catalog/`, `research/atmos-resources/`.
**Interfaces:** Produces pinned source inventories, file hashes, licensing and selected lab-to-requirement mappings. Consumed by the lab guide and completion report.

- [x] Clone and pin Terraform catalog, Atmos and supporting test repositories.
- [x] Read plaintext lab contracts, tests and fixtures for every declared lab; mark encrypted content.
- [x] Categorize execution requirements and audit scoring limitations.
- [x] Select reusable state/import/drift/stack/workflow patterns and document decisions.

### Task 2: Executable native lab

**Files:** `labs/atmos-adoption/`, `scripts/qualify-adoption-lab.py`, `plugin_tests/test_adoption_lab.py`.
**Interfaces:** Script accepts explicit native executable paths and a fresh output directory; produces JSON assertion and command receipts. Existing `resolve_component` API supplies plugin-to-native comparison.

- [x] Write and observe failing tests for runner boundary and plan/state assertions.
- [x] Implement isolated fixed native commands with deadlines and bounded local artifacts.
- [x] Observe baseline creation, unchanged second plan, intact state adoption into Atmos, intentional change detection, stack isolation and stale-plan rejection.
- [x] Exercise import separately and report whether it restores attributes.
- [x] Run the real native workflow and retain receipts.

### Task 3: Independent workflow audit and repairs

**Files:** `plugin_tests/test_lab_audit_regressions.py`, affected runtime modules, `research/lab-workflow-audit.md`.
**Interfaces:** Reproduced native/static counterexamples become permanent regression assertions.

- [x] Audit repository interpretation and lab execution boundaries independently.
- [x] Reproduce each accepted finding before changing implementation.
- [x] Repair implementations and run scoped regressions.
- [x] Have a fresh reviewer inspect the lab, integration and changed runtime behavior.

### Task 4: Verification and delivery

**Files:** version and release documentation, `release-source-files.txt`, verification receipts, release archives.
**Interfaces:** Existing verifier and deterministic release builder produce clean-extraction evidence.

- [ ] Run complete tests, native lab, CLI/PTY/repository checks and static Plugin Eval.
- [ ] Update factual support matrix and lab execution guide.
- [ ] Explicitly inventory new reviewed files; build archives and verify hashes after extraction.
- [ ] Repeat native lab from the extracted source and save deliverables with remaining production gates.

## Execution ledger

- Baseline: 539f942, release 0.2.1, clean worktree.
- Ruling: Execute the plan without a confirmation pause because the user explicitly requested planning and execution. Local disposable state writes are authorized; cloud adoption is outside this lab's scope.
- Ruling: Use built-in terraform_data instead of running unreviewed upstream provider/cloud examples. The cost is that this lab cannot establish real service refresh or Intune provider behavior.
- Task 3: Reproduced two defects with four test methods (one control pass and six failing subcases). Repaired missing directory-presence binding and vanished malformed dependencies. Scoped regression run: 76 passed, zero failures/errors/skips.
- Ruling: Preserve the documented file-only source digest, and bind directory presence in selection and runner evidence instead. The graph independently reconstructs that selection binding. Existing stored graphs using the old selection formula must be rebuilt; no execution authority derives from either format.

- Task 4: Final integrated source verification passed 466 tests with no failures/errors/skips. Final-source native lab passed 18 assertions/25 commands and 113 artifact hashes. Archive/extracted-source closure is recorded in the separately delivered versioned archive receipt.
