# R3 execution sequence — final03

Resume **0.8.0**, `289ee9477372825aad848f4482cf681c2ff43b02`. Preserve the
1,141-test R2 result and both failed-candidate ledgers with all scoped passes and
negatives. Do not repeat completed repairs or start another research cycle.

1. **Close the new exact-source gate.** Read actual final03 strict,
   connected-source, reproducibility and `QUALIFICATION.json` receipts under
   `milestone-0.8.0-final03/`. The fresh 64-check/34-command/10-PTY source journey
   passes; strict and final before/after closure remain pending. Do not infer
   them from focused tests or reused runtime evidence.
2. **Reconcile current results with explicit evidence reuse.**
   `REUSED-QUALIFICATION-EVIDENCE.json` proves the new runtime ZIP is exactly
   `cce47f620f5e1e7d3dbdab1e030624fae3991cbf88376737a4eda07e6c703515` and all product,
   graders, fixtures and native harness bytes are unchanged from c122e38. Only
   the reviewed native-observation test and generated source manifest changed.
   Keep original final02 runtime/native/capacity/capture/maintenance observations
   under their original commit and hashes; do not rerun or relabel them. Embed
   the complete failed-final02 ledger, which retains failed-final01 and R2.
   Preserve both strict failures, intermediate signal-repair negatives and
   open provenance gaps; add actual final03 strict and 40-file security review.
3. **Publish layered recovery after qualification.** Keep the full immutable R2
   snapshot; add the exact final03 source/runtime ZIPs and the entire R3 epoch
   as a typed/hash-bound supplement. Index all layers at
   `intune-r3-handoff-20261007`; verify public size/hash/reconstruction. This is
   not a replacement complete R3 ZIP. Keep unrelated Neon Commons untouched.
4. **Continue independent authorized external work.** Use the acceptance gate
   matrix and `docs/EXTERNAL-QUALIFICATION-R3.md`. A missing host or identity
   does not block unrelated work. Live worker and integrated Azure backend
   require implementation after reviewed execution/host/secret/state/lease
   boundaries; authentic platform qualification follows. No production change,
   credential provisioning, privilege expansion or deployment is authorized.

| Actual entrypoint | Implemented behavior | Evidence still required beyond local qualification |
|---|---|---|
| `capture`; `workbench import-capture`, `collection-history`, `collection` | Bounded GET retries, safe progress, cancellation, raw attempts and durable honest partial/denied history | Approved authentic Graph identity/tenant/object scope and service behavior |
| `wizard --journey`; `workbench adopt`, `inspect`, `history`, `propose`, `review`, `execute`, `reconcile` | Connected adoption, preserved lineage, exact-plan maintenance, independent readback, convergence and interruption recovery | Live worker implementation; native Intune import/refresh/change/readback/convergence under approved disposable scope |
| `workbench schedule-create`, `schedule-run`, `schedule-status` | Finite closed-terminal modeled observation and durable history/reopen | Installed/authenticated Graph fleet scheduling remains unsupported |
| `overview`, `search`, `dictionary`, `health`, `queue`, `terminal` | Scoped reads, explicit pages and truthful retained unpaged resource bound | Actual other hosts and representative production-scale evidence; no fleet SLA claim |
| `reference-import`, `reference-compare`, `lineage` | Pinned narrow Microsoft reference facts and historical Atmos lineage | Broad vendor mappings, native OIB and dynamic Atmos remain unsupported |
| Native `provider` and backend controls | Pinned schema/validation and existing separate local/lease controls | Integrated Azure backend implementation, reviewed authority boundary and separately authorized live state/lease/lifecycle proof |
| Native Codex `plugin` commands | Linux local registration/discovery/install/list/uninstall | Actual skill/model activation and other host profiles |

For a changed candidate or required final gate, replay from an exact source
extraction into **new** output directories using the retained runtime:

```bash
export PYTHONDONTWRITEBYTECODE=1
export INTUNE_TEST_VALIDATOR_LIBRARY=/workspace/intune-continuation/work/evidence/epoch-20261005/approval-prerequisite/libsodium.so.23.3.0
export INTUNE_TEST_TOFU_EXECUTABLE=/workspace/intune-recovery/native-reprobe/tools/tofu
/workspace/intune-runtime/bin/python -B scripts/verify-plugin.py --include-core --output /absolute/NEW/strict
/workspace/intune-runtime/bin/python -B scripts/qualify-workbench-connected.py --plugin /absolute/EXACT_PRODUCT_ROOT --python /workspace/intune-runtime/bin/python --output /absolute/NEW/connected
/workspace/intune-runtime/bin/python -B /absolute/capture-retry/qualify_capture_retry.py --project /absolute/EXACT_PRODUCT_ROOT --output /absolute/NEW/capture
/workspace/intune-runtime/bin/python -B scripts/qualify-workbench-capacity.py --prepare --project /absolute/EXACT_PRODUCT_ROOT --store /absolute/PRESERVED_1000_IMPORT_STORE --output /absolute/NEW/capacity
/workspace/intune-runtime/bin/python -B scripts/qualify-workbench-capacity.py --run --project /absolute/EXACT_PRODUCT_ROOT --python /workspace/intune-runtime/bin/python --output /absolute/NEW/capacity --quiet-window 'Coordinator confirms no competing heavy jobs; background activity remains observable'
```

Use the exact source checker for runtime-only qualification. Do not substitute
`--oracle-self-test` for the connected journey. Capacity reuses the preserved
1,000-import store; the original ingestion/performance receipt stays tied to
`9191d38` and need not be repeated.

The strict suite retains legacy `/tmp/intune-native-completion/tofu` 1.10.0.
Verify an existing destination or restore only regular member `tofu` to a new
private directory from retained
`evidence/epoch-20261005/native-legacy-prerequisite/tofu_1.10.0_linux_amd64.zip`.
Do not overwrite a destination, install system-wide or substitute current ToFu.
`legacy-tool-recovery.json` records CRC checks and restoration. Archive SHA-256
is `ff8aebfd069f15f3f9ba7814444c8cae05428314c2ded0faedb9d040f6936cdb`;
binary size is 88,379,576 and SHA-256
`0a9eda0f0898896969492504a6ce778f310675e8a1eb960434c26806cd252627`.
Current ToFu remains pinned to
`a325c8c2f6834575e440b03c2ba67f94256072754ac7787fea718be6f01fef6a`;
libsodium to `fe00408090ea084504d7cb0130af56a22554fe299034b864551b65a64ca8a7b5`.
Final03 `prerequisites.json` records all pins, including the native provider.

Native schema replay is `labs/production-lifecycle/native_smoke.py --tofu
PINNED_TOFU --provider PINNED_PROVIDER --work NEW_WORK --receipt NEW_RECEIPT
--provider-trace`; use the preserved final02 `native.command.json` for exact argv.
Native Codex uses the retained digest-pinned, network-disabled image and
`native-codex-container/RESULT.md` procedures: `qualify-native.py --plugin
EXACT_RUNTIME_ROOT --output NEW_OUTPUT`, then `grade-native.py --case NEW_OUTPUT
--runtime-zip EXACT_RUNTIME_ZIP --commit c122e38e33641336bc5af47b9dbf06eb0e58bc32`.
The preserved native case is `native-codex-container/final-runtime-02`; successful
installation alone does not prove a skill/model invocation.

Keep external gates separate: approved authentic reader credentials and scope;
reviewed live worker/backend implementation; disposable native service
lifecycle objects; actual protected GitHub/Azure trust controls; enrolled
representative devices; Windows/Git Bash/PowerShell/macOS hosts; controlled
host-failure environment; and accountable AppSec/risk/pilot approval. Each gate
needs its real procedure and independent evidence. Synthetic captures and
hash-consistent fixtures cannot replace it. Historical unexplained temporary
files/reappearance/stale locks remain open despite attributed working caches.
The separate `commit-transition-provenance/RECEIPT.json` retains an unattributed
commit-command actor with verified commit/parent/content/package linkage. Retain
execution-system command audit if available; do not invent a cause, rewrite the
commit, conflate it with the original three files or claim full provenance
closure.
