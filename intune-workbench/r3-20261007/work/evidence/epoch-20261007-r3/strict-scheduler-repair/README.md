# SIGINT during process acquisition: reproduced and repaired

The exact final01 strict candidate remains preserved. Its `../milestone-0.8.0-final01/strict-suite/test-log.txt` reports 1,236 tests, one failure and one unrelated test error; it is not a passing qualification. The scheduler failure was the unchanged `test_real_sigint_cleans_child_and_preserves_interrupted_run` immediate process-state assertion: an observed collector was still `R` after its parent returned. This finding does not erase the earlier R2 descendant-cleanup repair or its evidence.

## Root cause and repair

Both local supervisors initialized `process = None`, then assigned the return value of `subprocess.Popen`. A real SIGINT could raise `KeyboardInterrupt` after fork but before that assignment. Their existing finally cleanup then had no process reference, so the already-created collector escaped cleanup. The existing R2 process-group census/kill/reap logic was not reached; that logic is unchanged by this repair.

The initial mask-only repair passed the narrow single-thread tests but was independently shown insufficient when another unblocked Python thread receives the process signal: Python can still execute its main-thread handler during Popen. `mask-only-source/` preserves that intermediate implementation. Its 29-test and 12-repetition results below do not qualify the final repair or close the background-thread finding.

The final `protected._defer_spawn_interrupt` temporarily defers the Python SIGINT callback as well as masking SIGINT while the caller constructs and assigns its child process. It requires invocation on Python's main thread and rejects other callers before spawning; benign background transport threads remain supported. The parent restores its exact original handler and mask only after assignment, then dispatches any deferred original callback so cleanup has an owned reference. The child restores the exact original caller handler and mask before applying its existing execution guard. Both protected and provider supervisors use this narrow context. Existing guards, process-group identity checks, bounded cleanup, inherited scheduler overlap lock, and original scheduler assertion remain unchanged. This temporary process-global handler change is a new explicitly tested R3 behavior and is not an inherited R2 assurance claim. Ignored and custom handlers, preblocked masks, and restoration on failed spawn have explicit tests.

This repair delays parent SIGINT during Popen construction. It does not add a timeout to preexec startup, handle parent SIGKILL, or establish hostile-host or escaped-process-group containment. Existing Linux local execution qualification and storage/startup assumptions still apply.

## Evidence

- `before-source.json` and `before-source/` preserve affected original source/test bytes.
- `before-original.json` and per-attempt logs preserve four passes followed by an independently reproduced original scheduler failure on attempt five. The assertion was not weakened or delayed.
- `before-deterministic.json/.stderr` preserve deterministic real-SIGINT failure in both protected and provider profiles. The interception sends SIGINT after the real Popen constructor returns but before the supervisor receives its return value. Independent immediate procfs task-state checks observe `R` for both actual child processes; evaluator cleanup follows the assertion so no test survivor is left running.
- `after-focused.json/.stderr` record **29 passing tests in 10.319 seconds**, all process-cleanup and scheduler tests, including three new regression methods covering the real signal acquisition gap, exact parent/child mask inheritance, and failed-spawn mask/handler preservation. Before/after source maps match.
- `after-original.json` and per-attempt logs preserve **12 consecutive passes of the unchanged original scheduler test**, with stable affected source hashes. These repeated cases overlap the 29-test suite and are not additional unique tests.
- `mask-only-background.json/.stderr` preserve an initial background-thread test pass whose injection window was too short to establish closure. `mask-only-background-02.json/.stderr` preserve both profiles failing after extending only the bounded pre-return signal injection phase; immediate post-return state assertions remain unchanged. This finding agrees with the independent background-thread repro.
- `after-focused-02.json/.stderr` record **32 passing tests in 10.449 seconds** against the final handler-plus-mask repair, with identical source hashes before/after. The new background-thread signal, custom/ignored handler, and fail-before-spawn nonmain-thread cases supplement the prior focused coverage. The original scheduler assertion still passes unchanged. Do not add 29 and 32 as disjoint test totals.
- The separate evaluator owns `../strict-scheduler-independent-review/`. `before-01/receipt.json` independently records four original failures; `background-after-01/receipt.json` records the mask-only background-thread blocker. Final `after-handler-single-01/receipt.json` and `after-handler-background-01/receipt.json` each record four passes, covering both real supervisor guards at actual constructor and pre-assignment signal injection points with immediate original-identity task-state assertions. Both final source maps remain stable. Those independent results must be read separately.

The focused replay from the source directory is:

```text
/workspace/intune-runtime/bin/python -B -m unittest plugin_tests.test_process_cleanup plugin_tests.test_workbench_scheduler
```

The deterministic failing-before method is `plugin_tests.test_process_cleanup.ProcessCleanupTests.test_real_sigint_before_spawn_returns_cannot_lose_owned_child`; replay it against the preserved original supervisor modules to demonstrate the acquisition defect. The original timing-dependent regression is `plugin_tests.test_workbench_scheduler.WorkbenchSchedulerTests.test_real_sigint_cleans_child_and_preserves_interrupted_run`.

Final exact packages and the strict-suite gate must bind the repaired source. Neither this focused result nor prior completed R2 evidence relabels the failed final01 candidate as passed.
