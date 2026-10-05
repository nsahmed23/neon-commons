# Appendix B Offline Repair Implementation Plan

> For agentic workers: use superpowers:subagent-driven-development. Work in this isolated copy; the source archives remain unchanged.

Goal: ship the integrated, tested offline repair of Appendix B with independent preservation checks and usable local receipt/resume tools.

Architecture: retain the existing source-to-normalized-to-project interfaces. Integrate versioned correction schemas through a small validation boundary; derive preservation expectations independently. Workflow persistence validates actual local artifacts before calling the resume decision model.

Tech stack: Python 3.12, genuine jsonschema/PyYAML/HCL parser dependencies, unittest, Bash; no cloud/provider execution.

Spec: corrections/CORRECTION-SPEC.md and corrections/contracts/ORACLE-IMPLEMENTATION.md; the supplied independent correction-pack review adds GUID length, comparator shape, command registration and version-aware regression fixes.

Global constraints: synthetic source only; deploymenttheory/microsoft365 1.0.0; OpenTofu 1.10.0; Atmos 1.199.0; preserve identities/targeting and restricted originals; partial input has no active IaC/command cards; execution_authorized remains false; offline tests do not imply provider/tenant qualification.

Review focus: malformed but wrapper-valid settings, missing first relationship page, sensitive unknown keys/values in output, changed/missing receipt dependencies, valid authentication branch changes.

## Tasks and ownership

1. Runtime and baseline: acquire genuine validation dependencies in an isolated environment, record exact versions, run original 74 and 33 regression suite plus correction 22. Preserve failure causes. No validation shim.
2. Contracts: corrections schemas/models and reference/validation.py. Add failing length/branch/token cases, repair them, expose schema_errors/provider_settings/capture_errors/reference_errors. Populate capability map and field rule omissions.
3. Pipeline: reference/core.py and focused tests. Wire validation, strict root/chain checks, typed/qualified mapping, duplicate/reference checks, redacted unknown output, schema validation, registered command renderer, OutputConflict handling. Keep normalize(bundle,policy_id,expected_tenant) and generate_files(normalized,context).
4. Oracle: reference/invariants.py and mutation tests. compare(source,normalized,files=None,context=None) returns safe error codes, independently deriving identity/digests/mapped values/field dispositions and parsing actual generated imports/config. Never import generator/normalizer.
5. Workflow: reference/workflow.py, reference/approval.py, tools/session-reference.py and tests. Persist safe decisions/receipts, reread safe local artifacts and dependency hashes, reconstruct fingerprints, detect missing/edited/corrupt evidence, route early/partial/cancelled sessions with no authorization replay. Integrate structured approval comparison with controlled rejection.
6. Root integration: tools/build-reference.py and verify-materials.py; version-aware regressions; regenerate golden files only after oracle passes; updated docs/receipts/gap status; source comparison and clean extraction tests; ZIP saved as deliverable.

Each code task: add or reuse a concrete failing behavior test; observe the expected failure; implement; run its focused tests; report changed files and verification; receive independent review. Root performs full integrated verification and handles incompatibilities rather than weakening requirements.

## Interface rulings

- Tasks 2/3 share only validation API: task 2 owns reference/validation.py; task 3 consumes its four named functions. Task 2 does not edit core.py.
- Tasks 3/4 communicate normalized field/accounting decisions; task 4 derives expectations separately, does not call task 3 helpers. Only task 3 edits core.py.
- Tasks 2/5 share correction models: task 2 owns models; task 5 consumes them and owns workflow/approval persistence files.
- Task 6 owns verifier/CLI and original test updates; workers add separate test modules, do not edit old tests/goldens.
- Ruling: parallel implementation on disjoint owned files is appropriate for this local isolated copy; root integrates and reviews shared interfaces.
- Ruling: user explicitly directed execution; plan approval is already supplied. No further plan handoff is needed.

## Progress

- [x] Isolated copy and baseline git snapshot created.
- [x] Genuine runtime and red receipts (original74pass; original33adversarial 5pass/28fail; originalmodels22pass).
- [x] Contracts repaired.
- [x] Pipeline repaired.
- [x] Oracle implemented.
- [x] Workflow integrated.
- [x] Full verification, review, regeneration and packaging.

Final review is adversarial: imported provider alias/lifecycle/command/Atmos mutations, unmanifested component files, duplicate receipt kinds, malformed lockfiles and concurrent store creation are added as regression cases before delivery. All reproduced findings were resolved and independently rechecked. The integrated suite passed 207/207 with zero failures/errors/skips. Packaging uses the deterministic source-archive tool and a separate clean-extraction verification pass.
