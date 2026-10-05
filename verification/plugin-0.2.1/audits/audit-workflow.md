# Intune IaC v0.2.0 workflow audit and repairs

Audit scope: `intune_iac/wizard.py`, `runner.py`, `io.py`, and the relevant CLI dispatch/exit behavior. The audit reviewed executable code and wrote counterexamples before repair. This review is limited to the local workflow; it does not establish provider, tenant, host or PowerShell correctness.

## Reproduced defects

| ID | Severity | v0.2.0 behavior | Repair and evidence |
| --- | --- | --- | --- |
| WF01 | Medium | A saved session with `step: review`, `generated: null`, and empty fingerprints was accepted. With valid source/context and an absent output directory, `finish` returned `status: complete`, `generated: false` and printed `Local generated proposal verified`. The saved step was sufficient to claim generated-handoff completion. | Review checkpoints now require source fingerprints, all source/target paths and generated-file evidence. Completion also checks these prerequisites before the existing source-derived `engine.verify_project` validation. The invalid session is rejected without changing its bytes or creating output. |
| WF02 | Medium | A saved session with `step: conflict` and `conflict_reason: null` was accepted. Choosing `review` raised an uncaught `TypeError` while concatenating the null reason. | Conflicts require a valid, non-null reason at session validation. Invalid state returns a bounded `invalid_wizard_session` error, without traceback. |
| WF03 | Medium | Two invocations using the same session could both run and save. A deterministic nested invocation saved another output path, then the outer wizard silently overwrote its progress. Target locks do not protect session state. | A canonical-session-path `O_EXCL` lifecycle lock rejects a second wizard before it changes session progress. Normal save, cancel, EOF and handled Ctrl-C release it. An abrupt process termination may retain it; explicit recovery is documented, with no time-based lock stealing. Path aliases share the same lock. |
| WF04 | Medium | Placing the session inside its own output directory was accepted. Saving created an unowned output directory which the generator then could not safely adopt. Editing output to contain an existing session likewise persisted a self-conflicting state. | Scope validation runs before initial persistence, on resumed state and before each save. Output may not contain source/context, session or attempt paths. A rejected edit preserves previous session bytes, and an initially invalid scope does not create the output. Existing source/session alias rejection is now explicit rather than incidentally depending on JSON schema incompatibility. |

These findings do not demonstrate cloud execution, execution-approval bypass or arbitrary source-file overwrite. WF01 is a false local completion claim; `execution_authorized` remained false.

## Validation

- Original isolated repro: `workflow-audit-repro.py` reproduced false completion with no output and the conflict runtime exception.
- Before repair, nine regression tests produced **7 assertion failures, 1 application runtime error, and 1 control pass**. The runtime error was the reproduced WF02 application defect, not an absent fixture or test harness failure. Transcript: `workflow-audit-red.txt`.
- After repair and integration of the explicit assignment-source fixture, **53 tests passed**: ten audit regressions (including canonical path alias locking), the existing prepared-context and repository wizard suites, and the runner suite. Transcript: `workflow-audit-green.txt`.
- An intermediate repository-wizard run had **13 of 14 passes** while the production audit added a required explicit assignment source. The production agent repaired the old API-shaped fixture to provide observed `source: direct`; all 14 cases passed in the final 53-test run. The intermediate transcript is retained as `workflow-audit-repository.txt`.
- Final full-suite and clean-release testing belong to the parent integration step.

The changes are in `intune_iac/wizard.py`, `plugin_tests/test_workflow_audit.py`, and `docs/WIZARD.md`. Runner and I/O algorithms were inspected but did not need modification for these findings.

## Remaining product work

The current wizard implements a bounded, single-policy local authoring workflow. It does not implement the original full 32-state adoption wizard, cohort/partial-generation orchestration, an authenticated receipt/approval store, effective cloud/backend inspection, provider execution, live adoption verification or a privileged execution adapter. Those are unfinished product capabilities, not defects made complete by these regressions.

The runner's six fixed local actions, byte evidence rechecks, target locks and unknown-outcome retention are appropriate local controls. It deliberately provides no arbitrary shell dispatch, cloud adapter, cross-host lock or automatic reconciliation. Its documentation explicitly excludes power-loss durability and adversarial filesystem writers. `write_json` uses atomic replacement and file fsync, but lacks parent-directory fsync; no power-loss guarantee should be added without implementing and qualifying it. No undocumented durability claim is made here.

Native Windows and host behavior remain unqualified. The repaired lock uses portable Python file creation semantics, but these tests ran on Linux; that fact must not be converted into a Windows qualification claim. A production workflow should include user-facing outcome reconciliation and native-host/terminal interruption tests alongside the broader adoption milestones.
