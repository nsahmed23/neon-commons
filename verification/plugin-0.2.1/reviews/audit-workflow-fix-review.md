# Independent review of workflow fixes

Reviewer: Atmos/graph audit agent, reviewing another agent's wizard changes. No workflow implementation or workflow test file was edited by this reviewer.

Reviewed: current diff for `intune_iac/wizard.py`, `docs/WIZARD.md`, and `plugin_tests/test_workflow_audit.py`, with surrounding wizard and runner code. Scope is local saved-state invalidation, path overlap, cooperative session locking and recovery.

## Verdict

**Pass for the bounded local contract; no new blocking defect reproduced.** This does not qualify Windows filesystem behavior, adversarial shared-filesystem protection or a production cloud workflow.

- A saved `review` checkpoint now requires source/context fingerprints, all three paths and generated output evidence. Existing independent project verification remains required on resume and before completion; saved hashes alone are not trusted.
- Missing conflict reasons fail as an invalid session. Normal source/context or repository evidence changes still invalidate inspection/output progress.
- Scope validation runs before session lock/attempt creation, before writes and before revalidation. Output directories containing the session, attempts, source or context are rejected without overwriting the saved state. Canonical lexical aliases map to the same session lock; symlinked path components are rejected.
- The lock is acquired exclusively, is held for the interactive lifecycle and is released only by a caller that acquired it. A rejected concurrent invocation cannot remove the first caller's lock.
- Normal suspension and handled interruption release the session lock. Abrupt termination preserves it. No TTL/PID heuristic silently converts an unknown outcome into permission to retry. Documentation distinguishes session lock recovery from runner target-outcome reconciliation.

## Executed evidence

1. Ran the new workflow audit tests plus existing wizard and repository wizard suites: **41 tests passed**, zero failures, errors or skips. Receipt: `/workspace/scratch/26b6d364cfda/audit-workflow-fix-review-tests.txt`.
2. Independently exercised actual separate Python processes, not only the same-process nested unit test. Process A reached a locked prompt; process B was blocked. After terminating A and waiting for exit, its lock remained and a third invocation was blocked. The reviewer removed only that temporary test lock after confirming process exit, resumed successfully and confirmed normal suspension removed the new lock. No cloud operation occurred. Receipt: `/workspace/scratch/26b6d364cfda/audit-workflow-process-lock.json`; reproducer: `/workspace/scratch/26b6d364cfda/review-wizard-process-lock.py`.

## Residual boundaries

The mechanism is cooperative local exclusion. It does not claim an authenticated lock owner, distributed lock, filesystem-attack resistance, automatic reconciliation, Windows/native host qualification or authorization for external execution. These remain explicit product/qualification work, not reasons to reject the fixes reviewed here.
