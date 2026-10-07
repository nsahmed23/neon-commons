# Native observation assertion after the SIGINT ownership repair

The preserved final02 strict log reports 1,242 tests, one failure and no errors. Its sole failure is the old test requiring the Popen preexec callback to be identical to the original network guard. The SIGINT acquisition repair intentionally wraps that callback so it can restore the original child signal handler and mask before delegating. The identity assertion therefore no longer describes the required behavior.

Only `plugin_tests/test_native_smoke_observation_epoch.py` changes. The repaired assertion observes the actual forked child: it records the signal mask and original-handler identity before calling the original guard, invokes that real guard, and persists the evidence only after it returns. The parent independently checks the child PID is different, the exact original mask (including a blocked SIGUSR1) and handler were restored before the guard, and the parent's signal settings were restored after supervision. An outer finally also restores test signal state after a failing assertion, so a detected regression cannot contaminate following tests.

All prior trace/environment, Popen-control, output and private-evidence assertions remain. Additional checks cover exact argv, cwd, umask and stdin/stdout/stderr controls. The observation wrapper still adds only the fixed `TF_LOG_PROVIDER=TRACE` environment value; neither that wrapper nor any runtime source changes.

Evidence:

- `before-test.py`, `before-source.json`, `before.json` and `before.stderr` retain the original test and focused failure.
- `after.json/.stderr` retain the first six-test module pass before the independent review requested additional test-state cleanup.
- `after-02.json/.stderr` record the final **six tests passing in 0.067 seconds**, with identical source maps before/after. Compared with the pre-repair map, only the test file changed; all `intune_iac/*.py` modules and the native-smoke wrapper are unchanged.
- Final test SHA-256: `01fb4992680253a613bd81ee12e7ec355a9e19c2df4ab427305338ea49787cb5`.

Replay from the project source directory:

```text
/workspace/intune-runtime/bin/python -B -m unittest plugin_tests.test_native_smoke_observation_epoch
```

This test repair does not rerun or upgrade native-provider evidence and does not turn final02's strict failure into a pass. Final source qualification and the byte-identical runtime-package comparison belong to the release coordinator's next candidate receipts.
