# Independent contracts task review

Reviewed 30 September 2026 against `corrections/CORRECTION-SPEC.md` and the correction-pack implementation brief. Scope: correction schemas, capability map, field rules, `contract_model.py`, `reference/validation.py`, and their targeted tests. Read-only review except this report; concurrent workers' unrelated files were not changed.

**Final spec compliance: pass for this bounded task scope. Final code quality: pass for this bounded task scope.** C01–C03 are implemented correctly within the preview/offline scope. Both material findings below were repaired and independently rechecked; no open material finding remains in this review scope.

## Original material findings — both resolved

1. **Missing policy template evidence permits active generation.** `corrections/contracts/observed-policy.schema.json` does not require `templateReference`. Removing that property from the selected policy in `examples/supported/input/export.json` returns no observed-policy schema errors, no normalization blockers, and `offline_mapping_complete: true`; generation emits `main.tf` and `imports.tf`. The policy field rule qualifies only the exact bounded none-template shape. Absence does not establish that shape. Require affirmative none-template evidence for the active slice, or block active generation when it is absent; preserve absence in field accounting without inventing a source record.

2. **An error-bearing page can be declared complete.** `contract_model.py::capture_errors` checks HTTP status and a `value` array but does not reject `body.error`. Adding `error: {}` to the assignments page of the supported bundle gives `capture_errors == []` and normalization blockers `[]`. A nonempty error is incidentally blocked by unsupported child retention in the current producer, while the shared capture validator still accepts it. The specification requires error pages to invalidate completeness. Reject any explicit error envelope, including malformed/empty envelopes, in the capture gate and keep the integrated gate aligned.

Reproduce both with the genuine runtime:

```bash
PYTHONPATH=/workspace/scratch/26b6d364cfda/correction-validation-deps PYTHONDONTWRITEBYTECODE=1 python - <<'PY'
import copy, json
from pathlib import Path
from reference.core import normalize, generate_files
from reference.validation import schema_errors, capture_errors
b = json.loads(Path('examples/supported/input/export.json').read_text())
c = json.loads(Path('examples/context.json').read_text())
missing = copy.deepcopy(b)
policy = missing['collections'][0]['pages'][0]['body']['value'][0]
policy.pop('templateReference')
n = normalize(missing, c['selected_policy_id'], c['tenant_id'])
files = generate_files(n, c)
print('missing-template', schema_errors('observed-policy', policy), n['blockers'],
      [p for p in files if p.endswith(('.tf', '.tf.json'))])
error = copy.deepcopy(b)
cap = error['collections'][2]
cap['pages'][0]['body']['error'] = {}
n = normalize(error, c['selected_policy_id'], c['tenant_id'])
print('error-page', capture_errors(cap, cap['pages'][0]['request_url']), n['blockers'])
PY
```

Independent post-repair rerun of the original probes returned:

| Case | Contract diagnostic | Normalization result | Active files / command cards |
| --- | --- | --- | --- |
| Missing policy template | `schema::required` | `invalid_observed_policy`; mapping incomplete | Empty / empty |
| Empty error envelope | `error_page` | Capture violation; assignments incomplete; mapping incomplete | Empty / empty |

The observed-policy schema now requires the exact existing none-template object. `capture_errors` now rejects error-member presence regardless of truthiness. New tests cover missing/null/incomplete/non-none policy templates, empty/malformed/nonempty error envelopes at HTTP 200, and both integrated normalize/generate paths. The original failure evidence is retained in `verification/policy-template-before-repair.txt` and `verification/capture-error-before-repair.txt`; the implementation worker's fresh suite receipt is `verification/contracts-combined-after-repair.txt`.

## Verification and positive findings

The reviewer independently reran the genuine `jsonschema` runtime with `PYTHONPATH=/workspace/scratch/26b6d364cfda/correction-validation-deps PYTHONDONTWRITEBYTECODE=1 python -m unittest evaluations.test_repaired_contracts corrections.regressions.test_contract_models -v`: **42 tests passed** in 1.519 seconds, zero failures/errors. The earlier 38-test run passed before the two missing cases were added. The reviewer also reran both original probes independently as shown above.

- Exact GUID lengths reject trailing newline/whitespace; applicable policy/group/filter zero-ID constraints remain enforced.
- Valid federation object/null authentication transitions return controlled mismatches in both directions.
- The executable registry rejects builtins, keywords, assignments, leading dashes and unknown tools. Registered `python`/`sys.executable` identifiers are expressly offline argv-test previews; they do not prove binary trust or confer execution authority.
- The worked capability map gates definition, permitted value, instance/value type, platform, technology and empty children; unmapped shape-valid records remain review-only.
- Explicit field rules now cover metadata, null/absent setting template references, policy template leaves, and container/leaf accounting.
- Both schema diagnostic helpers return codes and sanitized paths rather than validator messages or rejected raw values. The canary diagnostic test passes.

Provider serialization/refresh, service behavior, native hosts, PowerShell and approval authenticity were not tested or qualified by this review.
