# Independent SIGINT acquisition review

**PASS_SCOPED:** the final handler-plus-mask repair passes eight independent actual-signal cases: both protected and provider supervisors, inside-constructor and before-assignment signal timing, with and without a benign background Python thread. Exact source hashes, original PID/starttime, immediate per-task observations, parent handler/mask restoration, and raw product cleanup receipts are preserved in `after-handler-single-01/receipt.json` and `after-handler-background-01/receipt.json`.

The frozen e8 implementation failed all four initial cases (`before-01`). A mask-only attempted repair passed four single-thread cases (`after-01`) but failed two of four background-thread cases (`background-after-01`): both inside-constructor cases left the original child runnable and no cleanup evidence. All these failures and the pending review remain intact. An early chat reversed phase labels; the raw receipt was immediately read and the label corrected.

Root cause: SIGINT could arrive after fork before `Popen` returned its process object to the supervisor. The finally block had no reference and skipped cleanup. Thread-local masking alone was insufficient because another unblocked thread can receive SIGINT and Python dispatches its handler on main. The final repair defers that callback during main-thread child acquisition, restores exact child and parent state, and then uses the unchanged R2 group-cleanup algorithm. Unsupported off-main invocation is rejected before creation. Existing cleanup, resource-release and network-guard functions are byte-identical to the failed e8 candidate.

`plugin_tests/test_workbench_scheduler.py` is byte-identical to R2 commit74130d0; the immediate terminal-state assertion was not weakened. The independent oracle observes state immediately after cancellation before evaluator-owned cleanup, with no post-return sleep. This reviewer did not rerun the full suite or original scheduler repetitions; owner qualification records those separately.

Replay only after a relevant source change, using a fresh output directory:

```sh
/workspace/intune-runtime/bin/python -B acquisition_probe.py --project /absolute/exact/source --output /absolute/new/single
/workspace/intune-runtime/bin/python -B acquisition_probe.py --project /absolute/exact/source --output /absolute/new/background --background-thread
```

Scope is cooperative Linux main-thread Python SIGINT cancellation, including benign background threads. The temporary process-global handler is explicit. No new startup timeout, arbitrary signal/SIGKILL containment, escaped-group, hostile-host, power-loss, live-provider or production approval claim is made. Final exact-package qualification remains separate; the failed e8 strict result and original R2 1,141 result retain their scopes.
