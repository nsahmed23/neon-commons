# Correction-pack provenance and contracts

This subtree preserves and extends the supplied correction materials inside the integrated repair. Original test receipts below are historical. Use `../BUILD-START-HERE.md` and `../verification/result-summary.json` for the executable repaired distribution.

# Appendix B corrections — start here

**This is a correction specification, adversarial regression pack and small executable contract models. It is not a repaired replacement for `build-materials-gap-closure.zip` and not a plugin.** The original archive is unchanged. Its supported golden should not be treated as provider-valid.

Read `CORRECTION-SPEC.md`, `defect-to-correction.csv`, `sources/provider-dependency-map.json`, and `qualification/PROVIDER-SERVICE.md`. Use `revised-gaps.json`: G01 closed for dossier structure only; G02–G12 partial, including reopened G03/G04/G06.

## What actually ran

The original full verifier was rerun in a baseline copy with its existing dependencies: 74/74 pass. A separate desired-behavior regression suite against an unchanged extraction ran33 tests: 5 controls passed, 28 assertions failed, no harness errors. Those failures reproduce defects, not completed repairs. `evidence/` retains the receipts and logs.

The new schemas and pure contract models have their own tests and receipt. Their passing results demonstrate those model assertions only. They do not close missing original-generator wiring, independent full-oracle implementation, session receipt persistence, provider semantics, native host execution or live qualification.

## Use the materials

From an already approved Python environment with the versions listed in `evidence/input-and-environment.json`:

```bash
python verify-corrections.py
```

This checks local schema/example/model/material consistency and runs only the new isolated contract tests. It does not run old desired-behavior regressions automatically or invoke cloud tools.

To reproduce counterexamples against an extracted ORIGINAL pack, supply its project root:

```bash
python regressions/run_original.py --pack /path/to/build-materials-gap-closure --output ./local-regression-results
```

The original currently returns exit1 because desired-behavior assertions fail. This run uses synthetic tempfile data and a harmless local Bash/CLI probe; inspect the test files first. It does not run provider commands. The original full verifier is separate; never replace failure with success because a golden reproduced.

## Required implementation order

1. Integrate F01/F02/F03/F04 gates into the original intake/normalization/generation path; keep old failing fixtures as regressions. Preserve unknown raw values only in restricted inputs (F06).
2. Implement the independently derived F05 oracle and compare actual generated import/HCL structures. Do not simply update goldens to whatever the generator now emits.
3. Integrate prerequisite-aware F07 dispatch plus the documented real decision/receipt store. Test early and partial resume, missing files, corrupted state, cancellation and concurrent writers.
4. Bind explicit F08 context through a trusted inspector and protected approval channel. Fix both F09 local recovery paths and native tests.
5. Run the actual pinned provider offline validation/serialization suite under a separately approved environment; then native host tests; then authorized tenant and behavioral qualification. Keep all stages separately labeled.

No automatic upgrade of OpenTofu1.10.0, Atmos1.199.0 or the selected provider1.0.0 is proposed. No source, tenant or target credentials are needed for the correction-spec tests.

## Key files

- `CORRECTION-SPEC.md`: exact correction rules and original path targets.
- `contracts/`: eight validating schemas, field rules, fingerprint origins, resume frontier and integration obligations.
- `models/contract_model.py`: pure decision/projection models; not integrated repair code.
- `fixtures/`: synthetic source, corrected provider config and inactive `.tf.txt` example; no authentic approval/live data.
- `regressions/`: original-pack counterexamples and new-contract tests.
- `qualification/`: separate provider/service/native/behavioral gates, none executed here.
- `sources/`: exact reviewed source identities/ranges and unresolved dependencies. No fictitious raw acquisition hashes.

The source export and context are synthetic copies from the original pack. Do not replace them with production exports in an unapproved model environment. Do not apply the inactive HCL example or emitted commands as part of this handoff.
