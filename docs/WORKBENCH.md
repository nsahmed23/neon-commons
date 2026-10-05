# Persistent maintenance workbench

Version 0.7.0 is a local engineering candidate extending the recovered engine. The first profile uses the existing bounded synthetic Settings Catalog service and protected local plan executor. It accepts no tenant credentials, sends no Graph requests, and grants no cloud mutation authority. Native provider RPC, actual GitHub/Azure/Intune controls and endpoint qualification are separate.

The actual entrypoint is `python -B scripts/intune-iac.py workbench --help`. Commands are connected through the same on-disk store so collection can run with the terminal closed. `wizard --journey` remains the existing adoption/generation journey; `repository` and `graph` retain existing inspection/resolution behavior. The new workbench provides subsequent investigation and modeled maintenance.

The concrete first journey is: collect an unmanaged policy, inspect its exact values and targeting, compare observations, investigate incomplete deployment reporting, propose one bounded correction, review the exact local plan, explicitly approve its digest, execute the protected synthetic operation, independently read back the modeled service, then reopen persisted history and freshness. Synthetic service acceptance never establishes endpoint application or health.

## Runtime and commands

Use the existing Linux x86_64 CPython 3.12 hash-locked wheels. During this continuation the interpreter is `/workspace/intune-runtime/bin/python` and the complete checkout is `/workspace/intune-continuation/work/projects/intune`. No new runtime dependency is introduced.

Use command `--help` for admitted parameters; the independent qualifier records executed commands and persisted-state assertions. Always choose fresh lab/service/store/operation/output paths. Do not reuse another operation's output or edit retained passing evidence.

## Evidence meanings

Observations are tenant/object scoped, timestamped and separate from desired configuration. Unknown change time or attribution remains unknown. Typed relationships express settings use, include/exclude/filter targeting and attributed source metadata; assignment does not imply membership. Identical observations can share content while collection attempts remain individually recorded. A denied or incomplete collection retains last-good data with its stale/partial status and does not turn missing policies into empty desired state.

Health keeps targeted and fresh-reporting denominators separate. Eight successful reports from 100 targeted means 100% of fresh reporters, 8% of targeted, and 92 unknown/stale. It is not sufficient to advance a rollout. Configuration equality, modeled request acceptance, deployment reporting and endpoint effective state are different facts.

Maintenance uses immutable object IDs, exact plan bytes, before-state and selected service/revision bindings. Unrelated policy facets and objects must remain preserved. Changed inputs/state or substituted artifacts require fresh review. The approval digest is explicitly synthetic local consent; it is not organizational identity/approval or a security boundary against a malicious same-user host process.

After an uncertain or partial mutation, inspect the journal and reconcile before any retry. Known IDs survive partial outcomes. A historical restoration is a newly reviewed desired change, not a guaranteed provider rollback or endpoint undo. No automatic retry, deletion or recreation is authorized by an unsuccessful command.

## Collection and operations

A separately invoked `workbench collect` is the closed-terminal collection entrypoint. An external scheduler may invoke it under an approved local reader profile. This continuation does not install a cron/system service or enable GitHub/Azure scheduling. Last attempted and last successful collection evidence is authoritative; a requested schedule is not proof of a run. No production capture is admitted into this synthetic service route.

SQLite transactions and atomic evidence files provide local restart behavior under the declared cooperative filesystem model. Local hashes and a writable DB are not tamper-proof. Native host crash/power-loss durability, secret storage/encryption, production retention and organizational access controls require their own qualification. Preserve old durability/reappearance findings even when current checks pass.

## Qualification and boundaries

Run `python -B scripts/qualify-workbench.py --output /absolute/fresh/evidence` for the actual CLI and independently checked persisted-state journey. The checker compares fixed expected values and detects deliberately corrupted identities, exclusions, filters and types. Shared-host independent checking is not private-oracle isolation against a hostile process. The exact source suite remains `scripts/verify-plugin.py --include-core --output /absolute/fresh/results`; any required skip or failure remains unsuccessful.

The existing validation workflow now calls the same qualification script and retains its evidence. This is an authored repository integration with local-script evidence until it actually runs in an authorized GitHub repository. Existing workflow action pins are preserved. No deployment workflow, OIDC permission or credential route is added.

Remaining full-product requirements include broader vendor dictionary content, complete repository inheritance navigation, authenticated read-only fleet collection with bounded throttling/transient retries, fleet scheduling qualification, native GitHub controls and approved provider/tenant/device lifecycle. Unsupported families remain unsupported. Wally is optional and its negative/inconclusive results remain valid.

## Runnable local sequence

From the checkout, set `PY` to the qualified interpreter and choose an unused private parent directory. This sample uses the shipped synthetic policy. The complete independent qualification below constructs its own two-policy estate and expected truth.

```bash
PY=/workspace/intune-runtime/bin/python
LAB=/workspace/intune-workbench-demo
mkdir -m 700 "$LAB"
"$PY" -B scripts/intune-iac.py workbench lab-create --service-root "$LAB/service" --input examples/supported/input/export.json --object 22222222-2222-4222-8222-222222222222
"$PY" -B scripts/intune-iac.py workbench init --root "$LAB/store" --tenant 11111111-1111-4111-8111-111111111111
"$PY" -B scripts/intune-iac.py workbench collect --root "$LAB/store" --service-root "$LAB/service"
"$PY" -B scripts/intune-iac.py workbench terminal --root "$LAB/store" --service-root "$LAB/service"
```

Inside the terminal, enter `search Privacy`, `select 22222222-2222-4222-8222-222222222222`, `settings`, `relationships`, `dictionary`, `history`, `health`, `queue`, `back`, or `quit`. `help` displays exact routes. Commands also work through redirected stdin. Values are safely escaped for ordinary terminals; this is a keyboard-driven line interface, not a full-screen graph application.

Write an intentionally changed full supported policy body to a fresh desired JSON file (the exact body is visible in `inspect`). Then use `propose DESIRED_JSON FRESH_OPERATION_DIR`, `review OPERATION_DIR`, and `execute OPERATION_DIR EXACT_REVIEW_DIGEST` inside the terminal. `reconcile OPERATION_DIR` reads observable state and never replays mutation. The same names exist as headless workbench subcommands; their help specifies flags. `restore-propose` creates a fresh historical-restoration proposal where available; a consumed digest never authorizes another operation.

A synthetic deployment file for the explicit coverage example is:

```json
{"targeted":100,"reporting":8,"successful":8}
```

Pass it with `workbench collect --root STORE --service-root SERVICE --deployment FILE`. These are explicitly collection-scoped counts, not assumed per-policy device telemetry. `--source FILE` accepts bounded attributed provenance; actual model source/revision metadata is independently bound by the collector, and user-supplied labels do not grant authority.

`workbench backup --root STORE --output BACKUP` and `workbench restore --input BACKUP --root FRESH_STORE --tenant TENANT` preserve tenant identity/history in a fresh local store. Check actual `--help` for final parameter names and retain the returned backup hash independently. A DB consistency check does not authenticate its creator.

The existing main validation workflow runs the same local checker. No GitHub workflow dispatch or production schedule was enabled. Run a closed-terminal collection explicitly, then reopen the terminal to view the new observation.

Repository context can be collected with explicit `--repo ROOT --stack STACK --component COMPONENT`; all three are required together. This reuses the existing bounded literal resolver, records inherited-source hashes and provenance, and executes no repository commands. It does not authenticate an Entra tenant or prove native Atmos evaluation. `history` and `operations` accept `--limit` and `--offset`; unpaged queries beyond 1,000 rows fail visibly instead of silently truncating history.

## Linux child-process cleanup

Local and provider runners retain their direct child until group cleanup completes. They send SIGKILL, inspect bounded Linux procfs process/thread state in the original session/group, and require repeated complete observations with no live member before reaping the direct child. Timeout, output-limit, cancellation and ordinary completion use the same cleanup boundary. The original execution error is retained separately from a cleanup error. A missing observation capability or unresolved deadline blocks verification; signal delivery alone is not success.

This requires readable procfs and Linux waitid WNOWAIT in the caller's PID namespace. Protected local execution denies new processes; the pinned provider profile allows process creation but denies session/group escape. These supported profiles are not hostile-host or cgroup isolation, arbitrary detached-process containment, power-loss durability, or native Windows qualification. Dead zombies may remain pending their actual parent's reap; they cannot execute or mutate state. Exact test and package receipts establish the qualified scope.

## Connected observation and reference commands (0.7.0)

Fresh stores use schema v2. Existing v1 stores remain readable; `workbench migrate --root STORE --backup NEW_BACKUP` explicitly creates a verified backup before transactional migration. Capture import is a separate inert observation route: `workbench import-capture --root STORE --capture CAPTURE_DIRECTORY`. It reads the existing collector's exact export/context/receipt/raw-page set, checks hashes, collection scope and paging completeness, and preserves caller-asserted assurance. Import does not contact Graph or authorize the modeled maintenance executor. Unsupported mappings retain raw evidence; denied or partial reads keep the last good observation and visible collection coverage. Unknown collection results never become empty desired state.

Use `collection-history --root STORE [--object UUID]` and `collection --root STORE --run RUN_ID` to inspect attempts after reopening. `device-evidence-import --root STORE --input FILE`, `health --root STORE --object UUID`, `workflow-import --root STORE --input FILE`, and `workflows --root STORE --object UUID` bind inert evidence to the selected tenant/object. The `workbench-device-evidence/1` envelope contains `schema_version`, `tenant_id`, `object_id` and the existing evidence-schema `evidence` object. Reported coverage does not authenticate the device or prove effective state. Workflow claims do not dispatch a workflow or establish remote approval.

`reference-import --root STORE --input FILE --sha256 SHA256 --revision COMMIT --source-url URL --license LICENSE` records immutable attributed bytes. `references`, `dictionary` and `reference-compare --root STORE --object UUID --reference REFERENCE_ID [--company FILE]` separate observed values, community reference recommendations and explicit company desired state. Missing company intent and vendor recommendations remain unknown. Pinned OpenIntuneBaseline evidence is retained with its GPL license in qualification evidence; the product does not execute upstream scripts, fetch remote code, or widen supported provider mappings.

`workbench schedule-create --root STORE --service-root SERVICE --output NEW_JOB --interval-seconds SECONDS` binds a local reader job. `schedule-run --job JOB --max-runs COUNT --max-duration-seconds SECONDS` runs a finite timer independent of the interactive terminal; `schedule-status --job JOB` inspects it. This is an explicitly invoked local runner, not an installed operating-system/cloud service. Fixed collector arguments, interpreter/source and filesystem identities are checked; overlapping runners are locked, interrupted attempts remain visible, and collection failures retain last success. No scheduler retries a mutation. Actual fleet scheduling and authenticated Graph collection remain external qualification work.

Local evidence is bounded (including the store's document-size limits), caller-writable and not tamper-proof. Capture importer validation establishes consistency of supplied bytes, not service authenticity. The current capture HTTP collector does not yet provide bounded throttling/transient retries; this remains an implementation gap rather than a passed external gate. The expanded actual terminal journey still needs a dedicated independent oracle covering every new 0.7.0 command; the existing full checker qualifies the original connected maintenance route only.
