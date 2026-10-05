# Genuine offline validation runtime

Observed on 2026-09-30 using Python 3.12.14. Validation dependencies were installed by ordinary pip through the configured network proxy into a separate target directory. No validation shim, approval escalation, proxy override, cloud/provider process, or paid model call was used. The earlier dependency lookup failure did not recur when the normal pip request was retried; the genuine jsonschema distribution and its dependencies downloaded and imported successfully.

Run the integrated work with:

```bash
export PYTHONPATH=/workspace/scratch/26b6d364cfda/correction-validation-deps
/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python tools/runtime-check.py
```

`requirements-validation.txt` pins the full observed validation dependency closure. `tools/runtime-check.py` makes no network request and reports distribution versions, resolved module paths, and schema/YAML/HCL smoke checks. Missing or mismatched dependencies report `blocked` and exit 2; semantic smoke failures exit 1. `verification/runtime-receipt.json` records a successful dependency-complete check. The primary runtime without the target directory lacks jsonschema/HCL dependencies; callers must supply the target path or install the requirements into their own isolated environment.

A separate scratch wheelhouse contains all ten dependency distributions. Installation into a second fresh target using `pip install --no-index --find-links ... -r requirements-validation.txt` succeeded without network access; `verification/runtime-offline-reinstall.json` records its successful runtime check. `verification/runtime-wheel-receipt.json` lists wheel filenames, sizes and SHA-256 hashes. These environment-specific wheels stay outside the portable source archive. `verification/runtime-blocked-default.txt` records the primary interpreter's honest blocked result when the dependency target is omitted.

The HCL parser is genuine `python-hcl2==8.1.4`. For independently inspected dictionary structures use `SerializationOptions(strip_string_quotes=True, explicit_blocks=False, with_comments=False)`: v8 defaults retain surrounding quotes. The smoke check parses an import target and GUID, and confirms malformed HCL fails. HCL syntax parsing does not qualify the pinned provider schema or service behavior.

Fresh baseline evidence has prefix `verification/historical/runtime-20260930T163025Z`. The original pack was copied before running its verifier because that verifier writes receipt files inside its root. Immutable original and correction roots were hashed before and after and remained unchanged; hashes and exact commands are in the provenance JSON.

| Scope | Fresh result |
| --- | --- |
| Original official verifier | 74 passed, 0 failures/errors; static verification passed |
| Desired-behavior assertions against original | 33 run, 5 passed, 28 failed, 0 harness errors |
| Original correction model specifications | 22 passed; 2,184 nonadvancement model cases passed |

The 28 original regression failures are genuine reproduced defects, not dependency/import failures. The baseline and correction results do not establish integrated repairs. Tests used only synthetic local material; no tenant authentication, provider execution, deployment, live collection, native host qualification, or model benchmark was performed. The portable source deliverable need not contain interpreter-specific binary dependencies; reproduce the environment using the pinned requirements and require the runtime check before substantive verification.
