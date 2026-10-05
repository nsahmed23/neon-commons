# Historical Appendix B integration and qualification plan

This records the repair-phase plan before the runnable plugin and repository-aware release were built. Its next-task statements are historical; do not repeat them as the current backlog. Use [product status](docs/PRODUCT-STATUS.md), [release evidence](RELEASE-VERIFICATION.md), and the dated implementation plans for current behavior and remaining gates. Historical G01–G12 status is retained without claiming production closure.

The offline repair is implemented. See CHANGELOG-REPAIR.md and repair-traceability.csv for completed work; the following tasks concern the broader plugin. G01 alone remains closed for dossier structure; G02–G12 remain partial.

Build the interactive product; do not repeat the landscape report. Use the already runnable synthetic reference and independent tests as a starting point, not a production-ready importer. Start with B03/B04/B05/B06/B07 for the local journey; close the exact B02/B08/B09/B10 gates before host/provider claims. B11 and B12 remain staged obligations. Keep helper functions independently testable and data-only commands separate from execution.

### B01 — Dossier/traceability (G01)
Input/source: original-contract. Read requirements-traceability.csv; BUILD-PLAN.md.
Target/interface: preserve the named schema/artifact contract; extend runtime only through that interface.
Current evidence: All12 gaps have populated material and next-task records.
Next bounded task: Consume the supplied contract; preserve its regression tests when implementing the product.
Tests: `tools/verify-materials.py`; expected artifacts are the paths above, not an invented score.
Dependencies: source/target context before generation; G02 before provider-backed acceptance; G06/G07 before host interaction; G09/G10 before distributing real plugins.
Organization parameters: approved provider/pins, target and owner where relevant. Qualification boundary: offline tests first; no live action unless separately authorized.

### B02 — Provider/assignment feasibility (G02)
Input/source: typed-intune;msgraph. Read provider-api-coverage.csv; recipes/settings-catalog-adoption.md; recipes/assignment-preservation.md.
Target/interface: preserve the named schema/artifact contract; extend runtime only through that interface.
Current evidence: Typed candidate source/import/assignment path and full reference files provided.
Next bounded task: Assign replacement/merge semantics, common serializer and pagination, provider execution remain unqualified.
Tests: `evaluations/test_reference.py`; expected artifacts are the paths above, not an invented score.
Dependencies: source/target context before generation; G02 before provider-backed acceptance; G06/G07 before host interaction; G09/G10 before distributing real plugins.
Organization parameters: approved provider/pins, target and owner where relevant. Qualification boundary: offline tests first; no live action unless separately authorized.

### B03 — Offline export contract (G03)
Input/source: original-contract. Read contracts/export-intake.schema.json; contracts/NORMALIZATION.md; examples/missing-page/input/export.json; examples/access-denied/input/export.json.
Target/interface: preserve the named schema/artifact contract; extend runtime only through that interface.
Current evidence: Versioned synthetic capture adapter and per-collection coverage implemented/tested.
Next bounded task: Consume the supplied contract; preserve its regression tests when implementing the product.
Tests: `evaluations/test_intake_edges.py`; expected artifacts are the paths above, not an invented score.
Dependencies: source/target context before generation; G02 before provider-backed acceptance; G06/G07 before host interaction; G09/G10 before distributing real plugins.
Organization parameters: approved provider/pins, target and owner where relevant. Qualification boundary: offline tests first; no live action unless separately authorized.

### B04 — Normalization contracts (G04)
Input/source: original-contract. Read contracts/observed-inventory.schema.json; reference/core.py; evaluations/test_invariants.py.
Target/interface: preserve the named schema/artifact contract; extend runtime only through that interface.
Current evidence: Real schemas, pointers/dispositions, partial blocking and independent mutation checks.
Next bounded task: Consume the supplied contract; preserve its regression tests when implementing the product.
Tests: `evaluations/test_invariants.py`; expected artifacts are the paths above, not an invented score.
Dependencies: source/target context before generation; G02 before provider-backed acceptance; G06/G07 before host interaction; G09/G10 before distributing real plugins.
Organization parameters: approved provider/pins, target and owner where relevant. Qualification boundary: offline tests first; no live action unless separately authorized.

### B05 — Golden projects and assertions (G05)
Input/source: original-contract. Read examples/supported/expected/project; examples/partial/expected/project; evaluations/plans; reference/invariants.py.
Target/interface: preserve the named schema/artifact contract; extend runtime only through that interface.
Current evidence: Actual projects, request shapes, plans, assertions and CLI tests present.
Next bounded task: Generated HCL has been parsed and independently compared; actual provider-schema validation and wire serialization/no-change adoption remain unobserved.
Tests: `evaluations/test_cli.py`; expected artifacts are the paths above, not an invented score.
Dependencies: source/target context before generation; G02 before provider-backed acceptance; G06/G07 before host interaction; G09/G10 before distributing real plugins.
Organization parameters: approved provider/pins, target and owner where relevant. Qualification boundary: offline tests first; no live action unless separately authorized.

### B06 — Wizard specification (G06)
Input/source: original-contract. Read wizard/wizard-state-machine.yaml; wizard/wizard-questions.yaml; wizard/FILES-AND-RESUME.md; wizard/transcripts.
Target/interface: preserve the named schema/artifact contract; extend runtime only through that interface.
Current evidence: Closed states/questions, seven missing branches, selective resume and file conflict contracts supplied.
Next bounded task: Consume the supplied contract; preserve its regression tests when implementing the product.
Tests: `evaluations/test_wizard.py`; expected artifacts are the paths above, not an invented score.
Dependencies: source/target context before generation; G02 before provider-backed acceptance; G06/G07 before host interaction; G09/G10 before distributing real plugins.
Organization parameters: approved provider/pins, target and owner where relevant. Qualification boundary: offline tests first; no live action unless separately authorized.

### B07 — Runtime/shell interaction (G07)
Input/source: original-contract. Read wizard/PLATFORM-AND-COMMANDS.md; wizard/argv-vectors.json; tools/build-reference.py; evaluations/test_cli.py.
Target/interface: preserve the named schema/artifact contract; extend runtime only through that interface.
Current evidence: Runtime selected; noninteractive CLI and Bash roundtrip tested; PowerShell renderer authored.
Next bounded task: Native Windows/PowerShell and actual interactive/PTY implementation/validation still needed.
Tests: `evaluations/test_cli.py`; expected artifacts are the paths above, not an invented score.
Dependencies: source/target context before generation; G02 before provider-backed acceptance; G06/G07 before host interaction; G09/G10 before distributing real plugins.
Organization parameters: approved provider/pins, target and owner where relevant. Qualification boundary: offline tests first; no live action unless separately authorized.

### B08 — Atmos/Azure/CI (G08)
Input/source: atmos. Read examples/azure-integration/expected/project; recipes/atmos-integration.md; permission-matrix.csv; reference/approval.py.
Target/interface: preserve the named schema/artifact contract; extend runtime only through that interface.
Current evidence: Complete synthetic existing-backend/handoff fixture and binding comparison provided.
Next bounded task: Effective Atmos inspector and real protected plan/import/change adapter, auth/network qualification remain.
Tests: `evaluations/test_approval.py`; expected artifacts are the paths above, not an invented score.
Dependencies: source/target context before generation; G02 before provider-backed acceptance; G06/G07 before host interaction; G09/G10 before distributing real plugins.
Organization parameters: approved provider/pins, target and owner where relevant. Qualification boundary: offline tests first; no live action unless separately authorized.

### B09 — Provenance/acquisition (G09)
Input/source: source-lock. Read source-lock.json; code-catalog.jsonl; reuse-ledger.csv; citation-repair-ledger.csv; sources/ACQUISITION.md.
Target/interface: preserve the named schema/artifact contract; extend runtime only through that interface.
Current evidence: Selected immutable code-unit records and pinned retrieval script; citation repair status explicit.
Next bounded task: Raw upstream bytes/dependency/license closure incomplete; some original citations unresolved.
Tests: `tools/verify-materials.py`; expected artifacts are the paths above, not an invented score.
Dependencies: source/target context before generation; G02 before provider-backed acceptance; G06/G07 before host interaction; G09/G10 before distributing real plugins.
Organization parameters: approved provider/pins, target and owner where relevant. Qualification boundary: offline tests first; no live action unless separately authorized.

### B10 — Host/evaluation (G10)
Input/source: plugin-eval. Read examples/host-package; evaluations/HOSTS-AND-HARNESSES.md; evaluations/plugin-eval.native-example.json; evaluations/cases.json.
Target/interface: preserve the named schema/artifact contract; extend runtime only through that interface.
Current evidence: Current-source contract differences, native examples,16case suite and four-arm plan supplied.
Next bounded task: Native parsers/install/runtime, protected effect recorder and paid behavioral tests not run.
Tests: `evaluations/test_additional_materials.py`; expected artifacts are the paths above, not an invented score.
Dependencies: source/target context before generation; G02 before provider-backed acceptance; G06/G07 before host interaction; G09/G10 before distributing real plugins.
Organization parameters: approved provider/pins, target and owner where relevant. Qualification boundary: offline tests first; no live action unless separately authorized.

### B11 — Diagnostics and broader families (G11)
Input/source: original-contract. Read examples/diagnostics; DIAGNOSTICS.md; INTUNE-ROLLOUT.md; family-coverage.csv.
Target/interface: preserve the named schema/artifact contract; extend runtime only through that interface.
Current evidence: Complete offline synthetic diagnostic/evidence case and app/script review contracts supplied.
Next bounded task: Collector source adaptation and additional family implementations still staged.
Tests: `evaluations/test_additional_materials.py`; expected artifacts are the paths above, not an invented score.
Dependencies: source/target context before generation; G02 before provider-backed acceptance; G06/G07 before host interaction; G09/G10 before distributing real plugins.
Organization parameters: approved provider/pins, target and owner where relevant. Qualification boundary: offline tests first; no live action unless separately authorized.

### B12 — Corpus audit (G12)
Input/source: terraform-corpus. Read catalog-manifest.json; tools/inventory-catalog.py; evaluations/CORPUS.md.
Target/interface: preserve the named schema/artifact contract; extend runtime only through that interface.
Current evidence: All88 actual meta.yml declarations recorded; Terraform replay source rechecked.
Next bounded task: Individual88lab files/grader/effect/attestation and matching runner audit not complete;0labs run.
Tests: `tools/verify-materials.py`; expected artifacts are the paths above, not an invented score.
Dependencies: source/target context before generation; G02 before provider-backed acceptance; G06/G07 before host interaction; G09/G10 before distributing real plugins.
Organization parameters: approved provider/pins, target and owner where relevant. Qualification boundary: offline tests first; no live action unless separately authorized.

## Delivery order

1. Verify this pack and run the synthetic CLI. Select and record real implementation language/runtime using the supplied Python reference unless a measurable requirement justifies change.
2. Implement the closed interactive graph in the chosen host/CLI, preserving partial blocking and selective resume. Keep the source project useful without the wizard.
3. Complete exact provider/import/assignment and Atmos context qualification. Do not remove acknowledgement or execution gates merely to make tests pass.
4. Integrate the organization's existing Azure identity/backend/CI and separately qualified protected runner.
5. Validate native host manifests/interaction, isolated graders/effect recorder, then perform authorized behavioral comparisons. Extend resource families only with source+fixture evidence.
6. Produce separate runtime/evaluation/provenance ZIPs; no golden answers/production data in runtime. Report observed checks and remaining limitations. This dossier ZIP is not those runtime ZIPs.
