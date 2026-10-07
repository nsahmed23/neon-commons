# R4 initial reconciliation checkpoint

This is a continuation checkpoint, not a completed milestone or release.
Source baseline is **0.8.0**, commit
`289ee9477372825aad848f4482cf681c2ff43b02`, on dedicated branch
`continuation/r4-20261007`. The root coordinator recorded a clean starting tree
in `work/evidence/epoch-20261007-r4/BASELINE.json`. No older source was restored
over newer work. The current implementation agents may have subsequent
uncommitted changes; inspect Git status before continuing.

The complete user-supplied contract is persisted byte-identically at
`work/docs/INTUNE-WORKBENCH-STRICT-CONTRACT-20261007.md` and this project's
`docs/STRICT-CONTINUATION-CONTRACT-R4.md`: **26,294 bytes**, SHA-256
`88192ac7e2627368fedcbc01e8f1faeb0f26120983f70bcdbb89e87bbdcb2c5a`.
It supersedes the earlier “brief not yet supplied” observation without rewriting
that historical receipt.

`docs/CONTINUATION-R4-LEDGER.json` records 91 requirement rows with the requested
identity, profile, status, evidence class, source/artifact applicability,
procedure, evidence, environment, limitation, next action and owner fields.
It includes 18 explicit fault families. Only baseline continuation linkage is
PASS; new implementation/qualification remains NOT_STARTED or externally
BLOCKED until actual receipts justify an update. Status here does not erase
existing implementation or original qualification. The initial ledger is also
saved unchanged in `work/evidence/epoch-20261007-r4/reconciliation/INITIAL-LEDGER.json`.

The historical R3 acceptance ledger remains unchanged: **310,833 bytes**, SHA-256
`7c1e5839c1c470199fd31f849b67730f7236c2a61e7375b1a6075e0e99f8b6a7`.
The baseline 1,242/1,242 exact-source strict result, 64-check/34-command/10-PTY
connected journey and separate 1,141-test R2 result were **not rerun**. Failed
final01/final02 candidates, cleanup/acquisition repairs and failed intermediate
repairs, all six threads, raw inputs, old skips, Wally negatives, unexpected
files/reappearance and commit-actor gaps stay immutable. The original three
unexpected files and attribution gap are not closed by successful new work.

The first unblocked dependency is accurate repository/observed/proposed/coverage
views, distinct collector/provider-state/deployment baselines, and complete
declared cross-stack ownership. Extend the existing store and application
entrypoints. Independently challenge merged-only, portal-only and simultaneous
changes, state-absent objects, conflicting owner, stale index, incomplete
collection, bad IDs/targeting/types and collection semantics. Then integrate
the common protected worker/backend contract; implement authentic reader and
independent scheduling; present those shared contracts in the visual workspace;
qualify required native routes; and qualify/package the exact reviewed release.
These dependencies and scoped external gates are recorded in the ledger.

Read `docs/OPERATING-PROFILE-R4.md` before expanding support. Native Windows/Git
Bash is a required external route, not removed because this host is Linux.
Current source pins are OpenTofu **1.13.1** and Atmos **1.230.1**; older
1.10.0/1.199.0 lab/fixture contracts retain historical scope. The new production
CI choice is unresolved: GitHub Actions is the existing documented candidate,
Azure DevOps Pipelines is unconfirmed. Implement the common worker contract
locally first; deployment needs the actual organizational choice and applicable
authorization. Do not disable the restricted lab network boundary.

The actual launcher is `scripts/intune-iac.py`. Root, `workbench`, `provider`,
`capture` and `target` help were invoked with the retained runtime; all five
exited zero. Raw stdout/stderr, argv and hashes are saved in
`work/evidence/epoch-20261007-r4/reconciliation/HELP-RECEIPT.json` and sibling
files. These are entrypoint discovery records, not tests or service evidence.
No new qualification command is claimed until its implementation and help exist.

Resume by reviewing current status and the preserved plan:

```bash
cd /workspace/intune-continuation/work/projects/intune
git status --short
git log -5 --oneline
cat docs/CONTINUATION-R4-CHECKPOINT.md
cat docs/OPERATING-PROFILE-R4.md
/workspace/intune-runtime/bin/python -B scripts/intune-iac.py workbench --help
```

At this checkpoint the ledger agent changed only four project documentation
files (`STRICT-CONTINUATION-CONTRACT-R4.md`, `CONTINUATION-R4-LEDGER.json`,
`CONTINUATION-R4-CHECKPOINT.md`, `OPERATING-PROFILE-R4.md`), the work-level brief
copy, and new `reconciliation/` evidence. The agent did not commit; the
coordinator owns the integrated durable commit. New candidate/artifact
identities remain null rather than incorrectly borrowing baseline hashes.

The initial reconciliation's structural checks validate required fields,
normalized statuses, unique IDs, dependency references, existing source paths,
brief equality and historical reference hashes. They do not count as product
tests. Save new independent product assertions and failed attempts in new R4
subdirectories, update exact revision/artifact applicability, and commit a
durable checkpoint after each meaningful increment.

**Outcomes:** laboratory work under the new contract is incomplete; required
platform qualification is blocked on concrete native environments and approved
service scopes; organizational production approval is absent. Continue all
independent local work. No production change, credential provisioning, platform
administration, paid resource or privilege expansion is authorized by this
checkpoint.

## Increment 1 — exact capture replay repair

The initial two new regressions failed: sequential replay produced two observations; four concurrent imports produced four. Publication now serializes duplicate detection and insertion in one SQLite write transaction. Every import attempt remains visible, exact raw capture bytes and original timestamps remain unchanged, and duplicates reference the original observation without refreshing it. The changed-scope run passed 37 tests (overlapping existing suites; not added to the historical strict count). Before/after argv, output and source hashes are in `work/evidence/epoch-20261007-r4/capture-reimport/`.

This commit checkpoints the store repair, its two actual-entrypoint/concurrency regressions and the R4 contract/ledger/profile. It is not an integrated R4 release. Additional working-tree files for views, authenticated collection, visual presentation, backend and worker are being implemented on the same continuation branch; preserve them and inspect `git status --short`. The complete old 1,242-test suite has not been rerun. The new baseline/pending reader evidence-class and inert artifact-kind plumbing is additive; imported evidence remains non-authoritative.

Resume this repair with:

```bash
/workspace/intune-runtime/bin/python -B -m unittest plugin_tests.test_capture_reimport_r4 plugin_tests.test_capture_adapter plugin_tests.test_workbench_capture_store plugin_tests.test_workbench_paging
```

Continue integrating the pending A/B/C/D lanes and independent acceptance. This checkpoint does not close the milestone, service, native Windows or production gates.

## Increment 2 — integrated local implementation, native boundary still in progress

Parent commit is `984b8d491d54a4805d1fb2d925b684131ded0373`. This increment
records the four views and real local state ownership scan; pinned Git object
verification; versioned field semantics and source patch preparation; common
protected worker and Azure state contracts; authentic-reader implementation
and independently invocable scheduler adapter; visual shared-engine workspace;
native Windows qualification preparation; and private encrypted archival.
`CONTINUATION-R4-LEDGER.json` now records implemented scope, exact file hashes
and receipt hashes. Its null final-applicability fields are intentional until
committed/package qualification establishes them. This is not a release.

New actual application routes include `workbench views`, `repository-import`,
`ownership-scan`, `source-acceptance-propose`, `observer-create/run/status`,
`observer-scheduler`, `workspace`, `worker prepare/review/run/status/attach/
cancel/reconcile`, and `artifact seal/inspect/restore`. Inspect each route's
`--help`; argument schemas in the corresponding R4 guides are authoritative.
The text workspace also supports `views-page` with retained global filters.

Scoped evidence lives under `work/evidence/epoch-20261007-r4/`: `views/`,
`observation/`, `visual/`, `protected-worker/`, `azure-backend/`,
`native-host-preparation/`, `artifact-vault/`, `terminal-interrupt/`, and
`independent/`. Independent candidate checks demonstrated distinct comparisons,
ownership/field negative controls, closed-terminal observation and capture
restore, exact local worker approval/state effects, and the visual intentional
change/lost-response/reopen/reconcile journey. These independent grouped
assertions and overlapping developer suites are not one combined test total.
Receipts identify which exact candidate each result applies to.

The original duplicate-capture repair also passed 37 checks from an exact clean
checkout of `984b8d4`; see `capture-reimport/committed-01.json`.
A new real SIGINT-inside-SQLite-callback reproducer failed before repair:
SQLite translated KeyboardInterrupt to a database error and the terminal read
another command. The terminal now retains interrupt intent outside the callback
and restores the original signal handler. `terminal-interrupt/before.stderr`
and `after-01.stderr` preserve the counterexample and passing changed-scope run.
Independent active-callback replay is recorded separately; idle SIGINT is not
substituted for it. The earlier visual timeout remains preserved.

Active working-tree lanes excluded from this checkpoint include the Unix/TLS
broker, Docker host, native provider/Atmos integration, and persistent queue
review metadata. Preserve their files and evidence. The broker's Graph-PUT
mislabeled-as-lease negative was independently found and repaired, with original
and passing counterexamples retained. Actual Atmos 1.230.1 probing found an
advertised `--from-plan=...` form that attempted a fresh plan and stopped at EOF;
no mutation occurred. An exact saved-plan route must be proven before admission.
The existing restricted laboratory network boundary remains intact.

Resume the integrated local changed scope with the retained Linux interpreter:

```bash
git status --short
git log -3 --oneline
INTUNE_TEST_VALIDATOR_LIBRARY=/workspace/intune-continuation/work/evidence/epoch-20261005/approval-prerequisite/libsodium.so.23.3.0 /workspace/intune-runtime/bin/python -B -m unittest plugin_tests.test_workbench_views_r4 plugin_tests.test_observation_reader_r4 plugin_tests.test_observation_jobs_r4 plugin_tests.test_workbench_tui_r4 plugin_tests.test_terminal_interrupt_r4 plugin_tests.test_protected_worker_r4 plugin_tests.test_azure_backend_r4 plugin_tests.test_native_host_contract_r4 plugin_tests.test_artifact_vault_r4 plugin_tests.test_capture_reimport_r4
```

Continue native host/broker/provider integration, persistent queue metadata,
independent review and exact final-byte journeys. Then run required release
gates, reproducible packaging and public/saved readback. Do not rerun the entire
old strict suite simply to increase a count. Required external evidence still
includes native Windows/Git Bash and PowerShell; chosen CI controls; authorized
disposable Intune lifecycle and independent tenant/principal readback; real
Azure identity/state; enrolled pilot devices; approved hostile/crash host tests;
and AppSec/operations/risk approval. No real tenant or platform write was
authorized or executed by this increment. Laboratory completion remains
incomplete, platform qualification blocked, organizational approval absent.

## Increment 3 — persistent review, bounded history and native host preparation

Parent commit is `03d7096edcb939ddd3b077f78211c170dfecf065`. This checkpoint
preserves immutable queue review metadata with concurrent-update rejection,
policy-bound reporting gaps, shared ownership evidence in the inspector,
versioned dictionary provenance, portable parser/host readiness gates,
bounded recent history and native host/provider adapters. It also repairs
archival native initialization and parent-directory replacement races.
The commit receipt under `integration/COMMIT-03.json` records the resulting
commit, explicit Git actor/argv, exact files and remaining working tree.

The root changed-scope integration run passed **109 tests** in 12 selected
modules; raw output is `integration/increment3-precommit.stderr`. The separate
history scope passed **31 tests**, including actual CLI and Linux PTY navigation
over 1,001 retained observations and workflow import referencing the oldest
snapshot. These runs overlap other evidence and are not summed into a new
strict-suite count. The composed history run's earlier 79/80 result is retained:
the failed health fixture rounded a timestamp into the future. The fixture now
uses its serialized time; the product's future-evidence rejection is unchanged.

Independent archival review reproduced two ancestor-replacement races before
repair. Descriptor-relative no-follow traversal now keeps reads and publication
bound to the held directory inode. Ten focused tests and three independent
native-crypto controls pass; old failures and a test invocation missing its
pinned library variable remain in `artifact-vault/`. This does not provide
same-account hostile-process isolation or encrypt the running SQLite/job volume.

Actual pinned Atmos/OpenTofu/provider work against local TLS fixtures completed
import, an unchanged first plan, one description correction, exact saved-plan
application, independent policy/assignment fixture readback and convergence.
The valid Atmos invocation uses separate `--from-plan --planfile` arguments.
The advertised combined form that replanned and stopped at EOF is retained.
Nine actual Docker host checks cover restrictions, native invocation, timeout,
output limits, interruption, controller loss and cleanup. Neither fixture nor
container results establish authenticated Azure/Intune platform qualification.

A separate native negative uncovered a real provider robustness defect:
malformed Graph error content causes an SDK nil dereference. Conformant 400/403
errors return ordinary diagnostics; all three preserve exact state bytes with
zero Graph writes and zero OOM kills. The isolated source candidate is untested,
and no replacement binary exists. Automated agent execution rejected the repair
task for possible cybersecurity risk without identifying a specific command.
No retry was attempted. See
`worker-provider/provider-negative/PRESERVATION-STOP-RECEIPT.json`; this remains
a release blocker, independent of the valid successful local lifecycle.

The exact detached checkout of commit
`2b0bcb998fbba49a8a232174c1858da162639957` then ran 144 selected tests and
reported three import errors: native provider tests require `worker_broker`,
which was intentionally left in the active integration lane. The other 141
completed without assertion failure; the run as a whole is **FAIL**, not a
qualified checkpoint. See `integration/INCREMENT3-COMMITTED-CHECK.json` and raw
logs. Commit the complete broker/service dependency and replay this required
scope; do not remove the three tests or reuse the working-tree109 result as an
exact-commit pass. The detached checkout remained clean.

Native Windows is **UNSUPPORTED at implementation level**, not merely waiting
for a test host. Capability checks now explain missing storage/security
primitives and reject before creating a store. Native qualification records
functional cases as unsupported/blocked even when these negative gates pass.
Linux import-denial probes do not substitute for Windows/Git Bash/mintty or
PowerShell evidence. An isolated Windows private-storage component is the next
unblocked implementation dependency; the Linux path remains unchanged.

Active work excluded from this commit includes native broker lease/metadata/
chunked-body integration, authenticated fresh-read preconditions, the protected
service orchestrator, and the isolated Windows component. Preserve their files.
The broker's independently reproduced metadata-effect admission failure stays
open until its owner records repair and independent replay. Source/runtime
packages remain version 0.8.0 pending a reviewed final candidate; no R4 release
or public readback is claimed.

Resume at the actual checkout and inspect current work before executing:

```bash
cd /workspace/intune-continuation/work/projects/intune
git status --short
git log -3 --oneline
/workspace/intune-runtime/bin/python -B scripts/intune-iac.py doctor
/workspace/intune-runtime/bin/python -B scripts/intune-iac.py workbench history-recent --help
```

Continue service/broker/precondition integration, independent boundary review,
final source-bound journeys, release gates and reproducible layered recovery.
The CI platform choice remains pending; no tenant or platform change is
authorized. Laboratory completion remains incomplete, platform qualification
blocked, and organizational production approval absent.

## Increment 4 — protected service composition and persistent evidence

Continuation parent is `2b0bcb998fbba49a8a232174c1858da162639957` on
`continuation/r4-20261007`. The next commit receipt in
`evidence/epoch-20261007-r4/integration/` records its exact resulting commit,
file list and actor. This is an implementation checkpoint, not a release.

The protected service now has independent exact-manifest signatures, external
one-use consumption and ownership, fixed native broker routes, fresh sealed
Graph preconditions, computed native state admission, durable lease recovery
inputs, independent state/Graph reconciliation and full execution-runtime
identity. Terminal preparation/observation cannot create execution authority.
The real controller rechecks its complete reviewed runtime before execution;
read-only preparation can run from a different terminal process.

Independent `independent/service-native-01/RESULT.json` passed a connected
Docker/relay/TLS journey with exact signature, wrong-reviewer rejection,
terminal detach/reattach, literal external-state assertions, cleanup and replay
denial. Its 23 assertions include six setup assertions; do not add it to suite
totals or describe it as native provider/live Azure/CI evidence. Broker/state
focused scope is 46 tests, and the read-only expired-lease inspector has five
tests. Receipt scopes and source hashes remain separate.

`worker-provider/native-service-prepare-01/receipt.json` preserves actual pinned
Atmos/OpenTofu/provider Azure-protocol initialization/import, no-change first
plan and a description-only saved correction: 85 fixture requests and 11
independent preparation assertions, zero Graph apply writes. The signed native
composition then exposed a failure: attempt01 lacked the explicit pinned
libsodium location and was rejected before dispatch. Attempt02 consumed exactly
one dispatch, returned native exit1, removed its container, and retained
`outcome_unknown` plus native lease recovery evidence. Its 101 fixture requests
and failure receipt remain unchanged. Diagnose the concrete error and preserve
the previous state/lease before any new isolated attempt; a passing simpler
transport journey does not close this native composition gate.

Workbench `service-link` persists exact tenant/object/manifest navigation.
`views` exposes the protected proposal and journal, and compares a deployment
only against its exact independently published capture. Unknown execution stays
separate. Unsupported mapping exposes literal raw captures, timestamps and
blockers without replacing normalized last-good values. Development evidence:
33 related tests plus one newly added unsupported-capture test, not overlapping
aggregate claims. Missing validator configuration, fixture mistakes and a
misspelled test-module command are retained in `service-views/attempt01/`;
corrected commands pass in `attempt02/`.

Inactive native Windows directory/storage components and native harnesses are
implemented. Their local state-machine tests do not establish native Windows
behavior. Functional Workbench Windows support remains UNSUPPORTED pending
store integration and actual Windows/Git Bash/mintty/PowerShell evidence. A
missing namespace durability barrier retains artifacts and reports uncertainty.

Type-aware evidence extraction and the eight-layer recovery wrapper are being
qualified with literal negative-test links and control-byte filenames retained
inertly. All diagnostics must escape them. The outer manifest remains a template
until final R4 archive pins exist; it must fail before extraction when incomplete.
No final package, R4 public readback or complete file-set closure is claimed.

The 18 required fault families now have an independent assertion/source map at
`independent/FAULT-FAMILY-MAP-01.json`. Remaining local composition cases include
policy success with assignment failure, acquisition/evidence-recording
cancellation, reviewed restoration as a new operation and final integrated
workflow/ref controls. Earlier failures, provider SDK nil-dereference finding,
automatically rejected repair lane and provenance anomalies remain open.

Resume without rebuilding the baseline:

```bash
cd /workspace/intune-continuation/work/projects/intune
git status --short
git log -3 --oneline
/workspace/intune-runtime/bin/python -B scripts/intune-iac.py service --help
/workspace/intune-runtime/bin/python -B scripts/intune-iac.py workbench service-link --help
/workspace/intune-runtime/bin/python -B scripts/intune-iac.py workbench views --help
```

Next: complete native composition and missing fault controls; commit the whole
dependency closure and replay the earlier failed exact-checkout scope; then
qualify the exact final source/runtime packages and full layered recovery.
Laboratory completion is incomplete, platform qualification is blocked, and
organizational production approval is absent. Do not retry the separately
rejected provider repair task or turn a checkpoint into a finish-line claim.

The native attempt02 root cause was subsequently confirmed with a deny-only
native CONNECT capture: pinned Go clients emit the exact optional
`User-Agent: Go-http-client/1.1` header. The broker previously rejected it before
any upstream request. The narrow repair retains surrounding denials and has
failing-before/passing-after evidence. No policy/provider gate was weakened.

`worker-provider/native-service-journey-03/receipt.json` now passes the complete
local native composition: exact saved Azure plan, signed protected service,
network-none Docker/relay/broker, pinned Atmos/OpenTofu/provider, policy and
assignment writes, fresh Graph preconditions, computed state write and lease
release, independently authenticated laboratory Graph/backend readback,
reconciliation, persistent service-linked views, and a no-change second native
plan. Its 17 assertions and 33 broker requests are one scoped journey. Of 181
fixture requests, 85 belong to preserved preparation and 96 are new. None are
live tenant/CI/device evidence. Unsupported mapping of the complete raw capture
remains explicit; normalized comparisons are not invented.

Independent review then reproduced raw SQLite projection substitution under a
capture's unchanged digest label. `raw_capture_observation` now validates the
retained type-aware capture bytes, exact projection and artifact commitments
before service-baseline use. Independent `service-views-after-03/RESULT.json`
passes 14 assertions, including tampering, missing/changed pages and restored
exact bytes; before failures and evaluator errors remain retained. The current
seven local view tests pass. An additional useful raw-observation test class has
unresolved original actor attribution; root reviewed and retained it at
`service-views/ATTRIBUTION-OBSERVATION-01.json`, without claiming attribution
closure.

Final service component scope is 30/30 at
`worker-service/qualified-08/QUALIFICATION.json`; its earlier 27/30 failure is
retained. New inactive Windows SQLite snapshot code has 14 Linux contract
controls with recorded Win32 boundaries, not native qualification. Packaging
inventory check05 admits 3,185 source members and 193 runtime members. Recovery
helper scopes are 22 typed-extraction controls, 11 wrapper controls and six
inventory controls; independent eight-layer miniature reconstruction passes 12
assertions. These counts overlap other scopes and are not a release-suite total.

Native fault/restoration exercises are continuing in new fixtures after this
checkpoint. The old full-suite results remain unchanged; final integrated and
package gates are still required.

Increment4 committed as `beb9daf7424e42f30c2d58c02014b7568289a3ae` with
explicit actor, staged-byte and file-list receipt `integration/COMMIT-04.json`.
An exact detached checkout passed 221 tests in 16 listed changed-scope modules;
the tracked tree remained clean. This includes all three previously failing
missing-broker cases. It is not a replay of the complete older 144-test selection
or either historical strict suite. See
`integration/INCREMENT4-COMMITTED-CHECK-ADDENDUM.json` for the exact command and
scope. Further native fault controls, explicit exceptional recovery and inactive
Windows store integration continue beyond this checkpoint.


## Increment 5 in progress — visual evidence and bounded Windows persistence

The actual native journey was independently navigated through three Linux PTY
sessions and the complete no-TTY route. Seventeen assertions pass, including
selection of unsupported raw captures, exact setting ID 37 and targeting,
protected-plan review, same-operation reattach, duplicate-name immutable identity
and no journal mutation. Earlier missing selection/raw-value failures remain in
`independent/visual-native-before-*`; root repair/source/replay receipt is
`service-views/VISUAL-REPAIR-RECEIPT-03.json`. Unsupported mapping remains visible.

The reviewed inactive Windows store reuses the exact schema and query engine,
with native handle-bound persistence, intent/outcome receipts, bounded backup,
pinned restore and recovery only into a new copy. Independent fault injection
found primary errors masked by close failures, premature completed receipts and
a missing early restore host guard; failing-before and passing-after receipts
remain under `independent/windows-store-*`. Ordinary Windows support is still
UNSUPPORTED pending native implementation integration and real host evidence.
The Linux/recorded-Win32 component tests are not native Windows qualification.

Native signed historical restoration completed with a new plan and operation,
independent readback, state serial14-to15 and a second no-change plan. Native
assignment403 and cancellation during acquisition, policy write and state
evidence recording preserve uncertain/partial results, leases and ownership.
See `worker-provider/NATIVE-SERVICE-EVIDENCE-INDEX.json` and the separate broker
acquisition receipt; counts remain separate and overlapping. Explicit signed
lease recovery, narrow description-drift state admission and same-authority
successor transfer are being implemented and qualified separately. No original
approval or failed plan grants new execution authority.

Current durable parent remains `beb9daf7424e42f30c2d58c02014b7568289a3ae`.
The working tree contains this increment; the next commit receipt will record
its exact paths and actor. Resume with `git status --short`, this checkpoint,
and the latest `integration/COMMIT-*.json`, then continue the pending integrated
recovery journey and exact-package gates. Laboratory completion remains
incomplete; platform qualification and organizational approval remain blocked.

The narrow description-recovery state contract is now integrated with exact-type
broker/readback branches; ordinary drift rejection is unchanged. The one-shot
lease recovery module is also preserved in this checkpoint; concurrency and
actual TLS evidence is scoped to its recorded source. Successor transfer and
its cancellation ownership repair remain staged outside runtime pending review.
A new independent finding identifies laboratory capture export/context labels
as non-synthetic and template tool versions despite correctly limited typed
reader receipts. Historical captures remain unchanged; root is repairing future
labels without minting live authority from caller-supplied context.

An additional actual22-command source conflict journey passed11 independent
assertions: competing proposals bind the same inherited source, first reviewed
Git commit wins, stale patch/product proposal reject, and a freshly based
proposal still requires review and a fresh plan. Native-success healthCLI also
retains all endpoint/device unknowns and null denominators (five assertions).
No live service, device or protected organizational review is inferred.
