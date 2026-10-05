# Legacy wizard complexity refactor

The original single-policy wizard now uses a private session controller with named state handlers. Its public API, saved-session schema, step names, prompts, error codes, locking, interruption behavior, evidence rechecks and guided delegation are preserved. No cloud, provider, host or paid model operation was added or executed.

Only `intune_iac/wizard.py` changed for this task. `workflow.py` was left untouched while its independent review proceeded. No additional runtime module or dependency is required.

## Actual Radon results

Measured with **Radon 6.0.1**, using:

```bash
/workspace/scratch/26b6d364cfda/enterprise-quality-venv/bin/radon cc -j intune_iac/wizard.py
```

| Callable | Before | After |
|---|---:|---:|
| `_run_wizard` | 127 | 9 |
| `_session` | 44 | 4 |
| `_selected_context` | 21 | 7 |
| Maximum function/method | 127 | 15 |

The remaining maximum of 15 belongs to the unchanged `_policy_ids` and `_validate_scopes` helpers. The highest new controller method is `revalidate`, at 14. These are measured Python cyclomatic complexities, not Plugin Eval's approximate whole-file decision count. Lower complexity does not independently establish correctness or enterprise readiness.

The source grew from 669 to 793 lines because state behavior now has named, separately inspectable handlers rather than one 400-line function. The controller holds the same in-memory state, inspection result, local attempt directory and callbacks previously captured by nested functions.

- The main loop prepares choices/review, obtains one answer and dispatches a fixed handler.
- Intake, path edits, selection, conflicts, generation and the two handoffs have separate handlers.
- Rendering is separate from state changes and execution checks.
- Saved-session validation has separate header, paths, fingerprints, generated-evidence, checkpoint and repository validators.
- Generation preview, execution-result acceptance and independent postconditions remain distinct checks.

## Verification observed

**54 tests passed**, zero failures/errors/skips, in 12.124 seconds:

```bash
/workspace/scratch/26b6d364cfda/plugin-clean-venv/bin/python -m unittest \
  plugin_tests.test_wizard plugin_tests.test_wizard_repository plugin_tests.test_workflow -q
```

This includes 17 legacy wizard tests, 14 repository wizard tests and 23 guided workflow tests. Coverage includes interrupt/save/resume, edit/back, denied/incomplete input, raw-value redaction, repository changes during prompts, forged session/manifest evidence, output conflicts, inactive production candidates and guided delegation.

The actual Linux PTY journey passed: generate was entered at the preview prompt, finish at review, process exit was 0 and independent CLI verification exited 0. The actual repository-first CLI/MCP qualification passed all seven checks: discover, resolve, wizard, verify, action preview, local action and stdio MCP.

```bash
python scripts/qualify-terminal.py --plugin /absolute/plugin --output /fresh/evidence
python scripts/qualify-repository.py --plugin /absolute/plugin --output /fresh/evidence
```

A separate differential harness loaded the exact pre-refactor implementation and compared **264 bounded saved-session perturbations** with the new implementation. Return values and exception type/code/message matched in every case. This included changed/missing top-level fields, every saved step, repository selector and fingerprint variations, path values and generated evidence values. It is an observed bounded comparison, not exhaustive equivalence proof.

The existing regression suite was sufficient for this behavior-preserving refactor; no implementation-mirroring tests were added to inflate its count. Final whole-project verification remains the root integration step after the parallel changes stabilize.

## Evidence and hashes

Workspace evidence:

- `/workspace/scratch/26b6d364cfda/wizard-pre-refactor.py`: exact before snapshot.
- `/workspace/scratch/26b6d364cfda/wizard-radon-before.json`: SHA-256 `6fc0e85709deb16cb2daf155b88f1423d9a1ca6480feda6a2e835c26fc107ecc`.
- `/workspace/scratch/26b6d364cfda/wizard-radon-after.json`: SHA-256 `5aebe3d0bd787edebe0b5249a25210c1b96bc02faaa2e133fb8982e14a85d5ac`.
- `/workspace/scratch/26b6d364cfda/wizard-refactor-tests.txt`: SHA-256 `42593a0c32af3f3db9084665a961dded8734fdbac87162e6823df3cb812bdbda`.
- `/workspace/scratch/26b6d364cfda/wizard-session-differential.py` and `.json`: 264-case harness and result; result SHA-256 `c94d1b78e2e2abea07ea2328e63ad4feda3d27b0b3b37f1d4c2997f3d479b88b`.
- `/workspace/scratch/26b6d364cfda/wizard-refactor-pty/`: native PTY transcript and `result.json`; result SHA-256 `70f860ad423859249b16467421997ff43b43ea4209844618ed9f6f10050ba2b6`.
- `/workspace/scratch/26b6d364cfda/wizard-refactor-repository/`: seven-check qualification evidence, generated inactive candidate and transcripts.

Final `intune_iac/wizard.py` SHA-256 at this task's handoff: `cae4017b32c4ea8883cd7d8ae00107aefb741844034031954838706e3c4b9450`.

`git diff --check` and Python compilation passed. No commits were made by this worker. This refactor changes maintainability, not the support matrix or production qualification status.
