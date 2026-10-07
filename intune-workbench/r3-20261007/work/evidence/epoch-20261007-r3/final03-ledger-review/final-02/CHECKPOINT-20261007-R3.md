# R3 checkpoint — final03 local scopes qualified

Continue from Intune **0.8.0**, branch `continuation/r3-20261007`, commit
`289ee9477372825aad848f4482cf681c2ff43b02`. Its exact-source strict gate passes
**1,242/1,242 tests, zero failures, errors or skips**. The fresh source connected
journey and final reproducibility gates pass. Prior successful runtime/application
evidence is reused only through explicit exact-byte equivalence. These are
recorded local/Linux scopes; platform and organizational production completion
remain open.

| Exact artifact under `releases/continuation-0.8.0-r3-final03/` | Bytes | SHA-256 |
|---|---:|---|
| `Intune_IaC_Plugin_0.8.0_Source.zip` | 16,627,882 | `4a0e56e4e01dd58e911a7fd0ad87c8f0be851630f3beb9c40d7ccc0b1b4c8590` |
| `Intune_IaC_Plugin_0.8.0.zip` | 513,895 | `cce47f620f5e1e7d3dbdab1e030624fae3991cbf88376737a4eda07e6c703515` |

All 3,087 declared source payloads match exact final03 Git; both extracted file
maps match their archives. `milestone-0.8.0-final03/REUSED-QUALIFICATION-EVIDENCE.json`
proves the runtime ZIP is byte-identical to final02 and source differs only in
`plugin_tests/test_native_smoke_observation_epoch.py` plus generated
`SHA256SUMS`. Product modules, graders, native harnesses and fixtures are
unchanged. Original `c122e38` connected-runtime, capture, capacity, native and
maintenance receipts retain their original commit/hash identities; they were
not rerun or renamed. Final03 source strict, fresh connected journey and rebuild
have separate completed receipts. Before/after source and runtime maps remain
unchanged and match the archives; both independently rebuilt ZIPs are
byte-identical. `milestone-0.8.0-final03/QUALIFICATION.json` records
`local_candidate_qualified: true`; it explicitly does not qualify production or
live service operation.

Final02's complete ledger is embedded unchanged and hash-bound by the new
acceptance ledger, including its failed strict gate, successful scoped gates,
failed final01 ledger and the complete preserved R2 ledger. Final02 ran
**1,241/1,242 passed, one failure, zero errors and zero skips**; its
reproducibility gate passed. That failed strict result is not reused as a pass.

The final01 `e8c581d` gate ran 1,236 tests: **1,234 passed, one failure, one error,
zero skips**. Its reproducibility gate passed. Its complete immutable ledger is
embedded and hash-linked by the new acceptance ledger. Its connected 64-check,
34-command, 10-PTY journey, capture 59-check/20-command run, capacity
48-command/10-check run and native provider/Codex results remain valid for their
original hashes; they are not relabeled as final02 observations.

Final02's sole failure was an obsolete identity assertion between the native
preexec wrapper and its original guard. The final03 test instead observes an
actual forked child, records restored signal handler/mask, calls the original
guard and writes evidence only after it returns. It checks a distinct child
PID, parent restoration and unchanged Popen controls, with outer-finally test
cleanup. **Six focused tests pass**, independently reviewed. All 41 runtime
Python modules and the native harness remain unchanged; no runtime repair or
native replay was needed. Evidence is in `strict-native-observation-repair/`
and `strict-native-observation-independent-review/`. Root's explicit final03
commit command is recorded in `final03-commit-command/RECEIPT.json`; that does
not resolve the older c122 actor-attribution gap.

The capture error was a stale test patching removed `capture.build_opener`.
The repaired test observes the real native HTTPS socket route under hostile
proxy/CA settings, with a proxy-sensitive urllib control. **43 focused tests**
and **six independent route assertions** pass. Product transport bytes did not
change; the observer blocks before DNS/TLS/send, so this does not qualify live
Graph TLS or identity. Receipts: `strict-capture-proxy-repair/` and
`strict-capture-independent-review/` in the R3 epoch.

The scheduler failure exposed a separate acquisition gap: SIGINT could raise
after fork but before assigning `Popen`, leaving no owned process for existing
cleanup. Both supervisors now defer the Python SIGINT callback and mask SIGINT
through assignment, then restore the exact original handler/mask and dispatch
the deferred callback. Child handler/mask inheritance is preserved. Nonmain
Python thread callers reject before spawning; benign background threads work.
**32 focused tests** and **eight independent actual-process cases** pass, with
unchanged original scheduler assertions and stable source. The initial mask-only
repair's 29-test/12-repetition passes and independent two-of-four background-thread
failure remain preserved; they are not final-repair passes. See
`strict-scheduler-repair/README.md` and `strict-scheduler-independent-review/`.
No preexec startup timeout, parent SIGKILL, escaped-group or hostile-host
containment claim is added.

The existing connected CLI now supports receipt-bound adoption, persistent
inspection/history, intentional change, exact-plan approval/execution,
independent service/SQLite readback, no-change convergence, lost-response and
delayed-visibility recovery without replay, finite closed-terminal observation
and reopen. Bounded GET retries retain attempts/raw responses and truthful
partial/denied/cancelled history. Explicit pages/scoped reads repair five
1,000-object navigation failures while retaining the 16 MiB unpaged bound.
A fresh final03 source run passes the **64-check, 34-command, 10-PTY** connected
journey with source unchanged. The identical runtime retains its original
final02 connected journey; source/runtime capture retain **59 checks and 20
commands each** through explicitly unchanged product/grader/fixture bytes.
Each final02 extraction also passed **48 capacity commands and 10 named checks** under its recorded
quiet-window thresholds, with source and databases unchanged. The existing
26-check/28-command maintenance grader and native provider schema/validation
also retain their final02 passes. These unchanged-byte scopes carry forward;
the new 1,242-test source gate is independently passed. Overlapping focused,
CLI, native and review assertion counts are not added to that total.

The byte-identical runtime retains **26 native Linux Codex assertions and 10 native
commands** (nine positive, one negative); all 130 installed files match its ZIP,
and the container was removed. The independent spotcheck supplies 24 grouped
cross-checks and 64 raw hash references, overlapping these observations rather
than adding to test totals. See `native-codex-container/RESULT-FINAL02.md`,
`EVIDENCE-HASHES-FINAL02.json` and `INDEPENDENT-SPOTCHECK-FINAL02.json`. Actual
model sessions and skill activation were not run. This supersedes older
native-unavailable prose only for the measured Linux plugin lifecycle.

The final changed-source security review accounts for **40 files and 11 bounded
AST candidates**. Eighteen accounting checks confirm the sole final03 test
change and unchanged runtime/harness bytes; they are not additional dynamic
tests. Seven other security boundary files and seven cleanup/filter bodies
remain unchanged. Findings and limits remain scoped and inconclusive for
organizational AppSec; no certification is inferred.

The original `9191d38` performance run remains **1,037 commands, 22 named checks,
1,000 actual imports**: complete 100-object overview passed; oversized unpaged
1,000-object overview truthfully rejected. Preserve that scope, the five later
route failures, and the development source-drift negative. Three short timing
samples do not establish a fleet SLA or percentile claim.

R2's **1,141/1,141**, zero-failure/error/skip result remains bound to 0.7.0 commit
`74130d0db99febf2f41cf4f4ebe2920a5d4dffb7` and its original Linux laboratory
scope. It was not rerun as a baseline. The earlier descendant cleanup repair
remains valid: signal acknowledgement was mistaken for terminal state and early
leader reap lost the group anchor. Retaining the leader with `waitid(WNOWAIT)`,
checking all tasks and two stable terminal censuses before reap repaired it.
Original results were 9/20 failures before and 20/20 passes after; independent
results were 15/44 failures before and 48/48 passes after. The new acquisition
gap bypassed that cleanup; it does not erase those receipts. Linkage is in
`reconciliation/cleanup-evidence-linkage.json`.

Keep laboratory completion, platform qualification and organizational production
approval separate. Native provider schema RPC and Linux Codex plugin lifecycle
are scoped observations; actual model/skill activation, live Graph/Intune
lifecycle, authentic Azure backend/GitHub workflow/device evidence, other native
hosts, controlled power-loss/hostile-host evidence and AppSec/pilot approval are
still open. A live execution worker and integrated Azure backend remain
**implementation/integration gates requiring reviewed execution and host/secret/
state/lease boundaries**, not merely credentials. Existing network denial must
not be removed to manufacture support. The scheduler is a finite local modeled
reader; broad vendor mappings, native OIB adoption and dynamic Atmos families
remain unsupported. The ledger lists environment, authorization, procedure,
expected evidence and release blocker for each external gate.

Preserve all six threads, inputs, raw negatives, skips and generated negative
symlinks. Three currently attributed Python caches are recorded in
`attributed-working-caches/RECEIPT.json`, including `py_compile` that writes even
with `-B`; those causes do not explain the original three unexpected archive-
absent temporary files, reappearance or stale locks. `SEC-GAP-WORKSPACE-RESTART`
remains unresolved. Wally stays optional/read-only; 87 completed reviews, nine
timeouts and no demonstrated benefit remain preserved.

A separate commit-command attribution gap is preserved in
`commit-transition-provenance/RECEIPT.json`: `c122e38` already existed when a
later root commit attempt reported nothing to commit. Its command actor/cause
remains unattributed. The commit object, parent, reviewed six-file delta, clean
tree and exact package linkage are verified. This does not infer byte-integrity
failure or change the observed test scopes; complete workspace provenance
closure is not claimed.

Delivery is layered recovery: the complete immutable R2 snapshot, exact final03
0.8.0 source/runtime packages, and the **entire expanded R3 epoch**, including
failed final01/final02 and intermediate repairs, as typed/hash-bound evidence. The R2
release is public at
https://github.com/nsahmed23/neon-commons/releases/tag/intune-r2-handoff-20261007
(2,289,864,715 bytes; SHA-256
`7117ab67ce6ae1912aa2c984774e6370216f3eb28be1510d0c6814cb4c295d0b`).
Release `intune-r3-handoff-20261007` will index every layer; this is not a new
replacement full-repository ZIP. No production mutation, deployment, credential
provisioning, paid service or privilege expansion was performed or authorized.
