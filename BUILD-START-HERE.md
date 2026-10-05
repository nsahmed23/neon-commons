# Appendix B — integrated offline repair

This package repairs the original synthetic Intune Settings Catalog reference pipeline. It includes the correction contracts, independent preservation checks, local receipt/resume tools, regression tests, and fresh verification receipts. It remains an offline implementation reference; provider/tenant and native-host qualification are separate.

## Run

Use Python 3.12 with the exact packages in `requirements-validation.txt`. In your chosen environment, install those dependencies once:

```bash
python -m pip install -r requirements-validation.txt
python tools/runtime-check.py
python tools/verify-materials.py
```

Verification does not install dependencies, authenticate, run a provider, import state or execute generated commands. To keep an extracted archive unchanged, place receipts elsewhere:

```bash
python tools/verify-materials.py --output ../verification-results
```

Generate the supported local example:

```bash
python tools/build-reference.py --input examples/supported/input/export.json --context examples/context.json --output ./reference-output
```

The CLI validates the source, normalizes the supported subset, independently checks preservation and generated HCL/import structures, and then writes a new local project. A raw-byte/source-digest receipt travels with the output. Rerunning identical inputs verifies owned files; changed or malformed ownership manifests produce a conflict instead of overwriting files.

Exit codes: 0 complete offline mapping, 2 blocked review output, 3 invalid input or failed independent check, 4 output conflict, 5 incomplete validation environment, 130 interruption. A mapping result does not authorize cloud execution.

The three blocked examples remain runnable with the same CLI by selecting `partial`, `missing-page` or `access-denied` in the input path. Their outputs contain review artifacts and no active IaC/import command cards. Unknown raw fields remain only in the source input; emitted artifacts use opaque findings where necessary.

## Local workflow and evidence

See `examples/workflow-demo/README.md`, `workflowdocs/LOCAL-WORKFLOW.md` and the `tools/session-reference.py --help` commands for the integrated local receipt/decision store. Resume checks actual artifact bytes and dependencies before deriving completion; it does not trust a saved completion list or reuse authorization. The full interactive terminal interface is still a separate host implementation.

## Evidence and status

- `verification/result-summary.json` and `verification/final-test-log.txt`: current integrated verification.
- `verification/runtime-receipt.json`: actual dependency/runtime checks.
- `verification/historical/`: preserved original results and newly reproduced baseline counterexamples.
- `CHANGELOG-REPAIR.md`: code changes, versioned regression decisions and boundaries.
- `gap-register.json`: current gap status; G01 is closed only for dossier structure, G02–G12 remain partial pending their remaining integration/qualification scope.
- `corrections/`: supplied correction dossier, with repaired schemas/models and source-ledger corrections used by this implementation. Receipts inside its `evidence/` directory remain historical model results.

The included HCL is parsed and independently inspected locally. Actual provider validation, serialization/state roundtrips, OpenTofu/Atmos execution, native Windows/PowerShell, host installation, paid behavioral benchmarks and live Azure/Intune operations are not established by these tests.
