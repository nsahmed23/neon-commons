# R4 continuation sequence

Start from the latest `integration/COMMIT-*.json` and this branch's
`CONTINUATION-R4-CHECKPOINT.md`, then reconcile `CONTINUATION-R4-LEDGER.json`.
The recovered 0.8.0 baseline is commit
`289ee9477372825aad848f4482cf681c2ff43b02`; newer valid work must be retained.
Checkpoint 8 is `b1ea9331de53228c0a0220928d8c0c38471b2a63`. Its detached
98-test changed scope and earlier 1,242/1,141-test historical scopes are separate.

| Order | Actual entrypoint and remaining behavior | Qualification and prerequisite |
| --- | --- | --- |
| 1 | `workbench views`, `workbench workspace` and the same text engine expose repository, observed, proposed and coverage evidence. Finish native Windows object-view readers without opening unsupported POSIX journals. | Retain actual Linux CLI/PTY evidence and recorded-Win32 controls. Real Windows/Git Bash/mintty remains a host-owner gate. |
| 2 | `service prepare`, `service review`, `service status`, `service attach`, `service cancel`, `service recover`; execution is `ServiceJob.run` in the trusted controller, not a terminal `service run` command. Implement the separate durable protected import/adoption route: native import currently has harness evidence, while `provider prepare` is the legacy network-denied route. | Separate import approval/state mutation/recovery from exact saved-plan apply. Exercise native import, first no-change plan, bounded change, readback, convergence and interruption. Existing signed apply and both committed-state recovery scopes remain valid at their exact bytes. |
| 3 | `workbench observer-create`, `observer-run`, `observer-status`, `observer-scheduler` connect the typed reader and durable store. Finish inactive native Windows scheduling and native target integration. | Preserve denied/partial/duplicate/out-of-order and atomic-publication evidence. Actual Linux cron attempts did not start observers; Windows tasks remain unregistered. Native host and existing authorized collector identity are required for closed-terminal platform qualification. |
| 4 | Complete the shared visual workspace, navigation context and native command coverage. Preserve the complete reference text interface. | Actual input/state assertions accompany captures. Unsupported journal or mutation routes must remain explicit; screenshots or recorded Win32 effects do not establish native host support. |
| 5 | Freeze the exact source and reviewed inventory; use `scripts/build-release.py`, `verify-release-artifact.py`, `verify-source-linkage.py` and `verify-plugin.py --include-core --output NEW_DIRECTORY`. | Follow `PACKAGE-QUALIFICATION-R4.md`: two byte-identical builds, safe extraction, exact Git-object linkage, required final gate and separate connected/native journeys. Never add overlapping counts. |
| 6 | Freeze and reconstruct all eight declared recovery layers, then read back the specifically reviewed public delivery. | Preserve all failures, literal negative-test links and provenance findings. Current capacity cannot hold a fresh simultaneous complete reconstruction; earlier exact-layer evidence remains separately reusable. Platform owners and AppSec/operations must supply their declared evidence and accountable approval. |

Parser help was inspected and retained in
`evidence/epoch-20261007-r4/integration/ENTRYPOINTS-09.json`. From the project
directory, these are safe discovery commands using the verified local runtime:

```sh
/workspace/intune-runtime/bin/python -B scripts/intune-iac.py workbench views --help
/workspace/intune-runtime/bin/python -B scripts/intune-iac.py service prepare --help
/workspace/intune-runtime/bin/python -B scripts/intune-iac.py workbench observer-create --help
/workspace/intune-runtime/bin/python -B scripts/intune-iac.py workbench workspace --help
```

`EXTERNAL-GATES-R4.md` identifies each required environment, owner, procedure,
expected evidence and release consequence. The malformed-provider-error repair
remains stopped following automatic review rejection; successful conformant
native runs do not close that finding. No production mutation, task activation,
credential provisioning or privilege expansion is authorized by this sequence.
