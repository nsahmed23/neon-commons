# Persistent maintenance workbench

Version 0.6.0 is a local engineering candidate extending the recovered engine. The first profile uses the existing bounded synthetic Settings Catalog service and protected local plan executor. It accepts no tenant credentials, sends no Graph requests, and grants no cloud mutation authority. Native provider RPC, actual GitHub/Azure/Intune controls and endpoint qualification are separate.

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

Remaining full-product requirements include broader vendor dictionary content/OIB attribution, complete repository inheritance navigation, authenticated read-only fleet collection, qualified scheduling, native GitHub controls and approved provider/tenant/device lifecycle. Unsupported families remain unsupported. Wally is optional and its negative/inconclusive results remain valid.

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
