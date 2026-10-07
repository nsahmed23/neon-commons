# R2 execution sequence

**Completed and preserved:** frozen 0.7.0 commit `74130d0db99febf2f41cf4f4ebe2920a5d4dffb7` passes 1141/1141 strict tests, exact-source connected 26-check CLI/PTY qualification, native schema validation and exact runtime scheduling smoke. Both archives reproduce exactly; source bytes are unchanged. Do not repeat those checks without a source change or concrete new concern.

| Connected entrypoint | Current implementation and qualified scope | Remaining behavior |
| --- | --- | --- |
| `scripts/intune-iac.py workbench import-capture`, `migrate`, `collection-history`, `collection`, `inspect`, `history` | `capture_adapter.py` / `workbench_store.py`: bounded offline receipts/raw-page validation, backed-up migration, policy-scoped persistence and denied/partial coverage | Existing GET capture transport needs bounded retries/backoff; authentic fleet collection needs approved identity/scope |
| `reference-import`, `reference-compare`, `dictionary` | `workbench_provenance.py`: immutable community/local provenance, typed comparisons and candidate rename history; nine actual pinned OIB interpretation checks | Authoritative vendor breadth and supported native OIB adoption remain absent |
| `device-evidence-import`, `workflow-import`, `health`, `workflows` | `workbench_health.py`: distinct policy/device stages and denominator accounting; local assertions remain explicit | Real endpoint/workflow authenticity and effectiveness need approved external evidence |
| `schedule-create`, `schedule-run`, `schedule-status` | `workbench_scheduler.py`: finite explicit ModeledService window, pinned identity, persistent run history, overlap prevention and observed SIGINT/SIGKILL recovery | No daemon, cron/systemd installation or real Graph fleet scheduler; broader host durability remains open |
| `propose`, `review`, `execute`, `reconcile`, terminal navigation | Existing maintenance engine and protected execution, bounded process cleanup and repaired PTY checker | Add dedicated comprehensive terminal oracles for every new route and enterprise-scale/performance qualification |

Proceed next with a bounded retry contract in the existing GET-only capture transport: explicit per-attempt/deadline budget, capped Retry-After/backoff, cancellation, unchanged scope/origin admission, and denied/partial final coverage. Add focused transport fixtures and one connected capture/import/reopen qualification, preserving prior no-retry evidence. Then broaden terminal traversal/oracles and vendor/reference support. Do not start another general research or recovery cycle.

For the next changed candidate, use the retained runtime and exact test prerequisites:

```bash
export PYTHONDONTWRITEBYTECODE=1
export INTUNE_TEST_VALIDATOR_LIBRARY=/workspace/intune-continuation/work/evidence/epoch-20261005/approval-prerequisite/libsodium.so.23.3.0
export INTUNE_TEST_TOFU_EXECUTABLE=/workspace/intune-recovery/native-reprobe/tools/tofu
/workspace/intune-runtime/bin/python -B scripts/build-release.py --output-dir /absolute/new/build
/workspace/intune-runtime/bin/python -B scripts/verify-release-artifact.py --archive NEW_SOURCE_ZIP --sha256 REVIEWED_NEW_SHA256 --extract /absolute/new/extraction
# From the exact new extracted intune-iac-source directory:
/workspace/intune-runtime/bin/python -B scripts/verify-plugin.py --include-core --output /absolute/new/strict
/workspace/intune-runtime/bin/python -B scripts/qualify-workbench.py --output /absolute/new/journey --python /workspace/intune-runtime/bin/python
```

Do not add `--oracle-self-test` for the complete journey: that flag runs only two checker controls. Retain pinned legacy `/tmp/intune-native-completion/tofu` alongside current ToFu. Validator SHA `fe00408090ea084504d7cb0130af56a22554fe299034b864551b65a64ca8a7b5`; current ToFu `a325c8c2f6834575e440b03c2ba67f94256072754ac7787fea718be6f01fef6a`; legacy ToFu `0a9eda0f0898896969492504a6ce778f310675e8a1eb960434c26806cd252627`. No repinning or system installation is needed.

Actual approved Graph readers/tenant/object scope, separately authorized native provider lifecycle objects/backend, GitHub/Azure trust controls, representative Intune devices, native Windows/GitBash/PowerShell/macOS, hostile-host/power-loss evidence and organization AppSec/production approval remain separate prerequisites. No tenant mutation, deployment, paid service, credential provisioning or privilege expansion is authorized.
