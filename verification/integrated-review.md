# Independent integrated review — 30 September 2026

Verdict: **pass for the declared bounded offline repair**. No unresolved blocking defect was found in the reviewed source after the fixes below. This verdict does not establish provider/service behavior, native-host qualification, authenticated capture or approval, or permission to execute infrastructure commands.

## Scope and evidence

Reviewed the repair plan, correction specification, independent-oracle implementation contract, change map and material status; then inspected `reference/invariants.py`, `core.py`, `field_accounting.py`, `validation.py`, `workflow.py`, the CLI integration, applicable contracts and regression tests. Review changes were confined to this report. The original archives were not modified.

The final independent run of `tools/verify-materials.py` with genuine jsonschema 4.26.0, PyYAML 6.0.3 and python-hcl2 8.1.4 completed at 16:58:57 UTC: **207 tests passed; zero failures, errors, skips or static failures**. Its receipt was written to `/tmp/integrated-review-20260930-final-late`. This run includes the added full-path workflow positive and late invalidation controls. The authoritative packaged final count remains `verification/result-summary.json`, which may include subsequent additional regression tests.

## Concrete defects identified and rechecked

| Review finding | Required behavior now independently observed |
|---|---|
| Raw bytes plus generated files could pass without a raw-source receipt | Missing receipt rejects; correct raw/canonical receipt passes |
| Import provider override and lifecycle `ignore_changes` escaped parsed-HCL checks | Both mutations reject through exact import/lifecycle contracts |
| Command executable substitution and stack qualification guard mutation passed | Changed executable and false-to-true stack guard both reject |
| HCL was aggregated across unrelated directories | Moving the real component or import file to `review/` rejects |
| Additional automatic variable configuration escaped the active-HCL list | An extra `.auto.tfvars` file rejects |
| Existing output reruns ignored an unmanifested active file | Rerun raises an output conflict and preserves every existing byte |
| Tests lacked a successful late workflow path | A full byte-backed seed independently verifies all nine milestones and reaches `qualification_handoff`, with execution disabled |

The oracle worker also added parsed block/path, command-preview and configuration mutations. The owned-file symlink, duplicate receipt-kind and stale Git-binding defects found by scoped reviewers have integrated regression coverage. A temporary partial-command assertion mismatch was a test-envelope issue: the stricter implementation already rejected the malformed document; the test now exercises the intended schema-valid partial card case.

## Preservation and integration assessment

The oracle does not import the normalizer, generator, producer accounting or shared projection helper. It independently derives selected tenant/object identity, stable key, source digests, desired policy/settings/target values, external references, capture coverage and each field-accounting record. It compares actual parsed generated HCL and independently specified command/stack structures. The CLI gates writes on this comparison; the successful baseline and four complete/partial fixture paths prevent blanket rejection from counting as preservation.

The supported mapping is deliberately limited to the exact synthetic capability declaration. Unknown fields and unsupported known values are retained in the original input with opaque public findings; supported observations, desired values and accounting are independently compared. The canary checks are bounded evidence, consistent with the documented absence of a general secret-detection guarantee. Partial records remain inactive and do not obtain infrastructure command cards.

The resume layer rereads artifact bytes and dependencies instead of accepting a caller's claimed verification list. Its decision model intersects verified prerequisites with saved progress, invalidates dependents and selects the first missing prerequisite. Beyond the integrated suite, this reviewer independently exercised the full receipt-backed workflow and observed:

- All nine milestones verified; no inspection errors; unchanged resume reaches `qualification_handoff` without execution authority.
- Adding an unlisted active file under the generated component, outside the separately declared repository path, returns to `generate`.
- Editing actual generated HCL bytes returns to `generate`.
- Removing the validation receipt, while correctly updating the local index locator hash, returns to `local_validation`.

These positive and mutation controls demonstrate real late-stage progress and invalidation, rather than testing only graph reachability or a decision model supplied with trusted completion strings.

## Quality and remaining boundary

The separation between production mapping, independent comparison and persisted-evidence verification is appropriate for this reference. Errors exposed through the CLI remain safe codes/messages; provider pins and source hashes are not substituted for semantic validation. The implementation is intentionally strict about a small generated layout and supported capability, which should remain explicit when extending it.

The remaining gaps are honestly recorded: no actual provider schema/serializer/state-roundtrip qualification, provider-backed import/plan, service assignment semantics, native Windows/PowerShell qualification, cloud calls or protected execution adapter was performed. Those omissions do not invalidate this bounded offline repair and must not be relabeled as completed by the passing local suite.
