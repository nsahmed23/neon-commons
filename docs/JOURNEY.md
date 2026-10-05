# Auditable local Intune journey

`wizard --journey` runs discovery, target review, complete capture inventory, UUID selection, preservation, mapping, ownership review, Atmos placement, generation, validation, adoption review, plan, approval, local execution, reconciliation, convergence and handoff. It uses the existing source engine, independent preservation oracle, and a protected local executor. The default executor is a fixed synthetic child process; explicit pinned native options add configuration comparison and output-only saved-plan execution. Completion is `complete_simulation`; it is never evidence that an Intune tenant, provider or Atmos deployment was changed.

```bash
python scripts/intune-iac.py wizard --journey \
  --session /absolute/new/session.json \
  --input /absolute/capture.json \
  --context /absolute/context.json \
  --output /absolute/new/proposals
```

The supplied capture remains the source of generation. The context must be an emit-only context accepted by the engine. Production captures retain their inactive `.tf.txt` candidates and provider qualification blockers. Unsupported mappings still generate review material but cannot proceed to an executable simulation. Repository mode observes bounded literal Atmos sources; a synthetic reference mapping never becomes a qualified arbitrary repository mapping.

At the first three stages enter `continue`, then select observed immutable policy UUIDs separated by commas. Continue through preservation, mapping, ownership and Atmos. Enter `generate`, then `continue` for validation and adoption review. Enter `plan`, `approve`, `execute`, `reconcile`, `continue`, and `finish` at the corresponding stages. Every prompt presents the current action's prerequisites, reads, writes and recovery rule. `approve` authorizes only the exact saved plan for the described local executor. An accepted command prints `Working:` before rechecking current evidence; this feedback grants no authority and does not skip a validation.

The saved plan contains the full selected semantic estate: immutable policy IDs, names, descriptions, platforms, technologies, scope tags, nested settings and assignments including exclusions and filters. The protected child process adopts that complete state into its private model. A separate raw-capture projection checks preservation independently of the production normalizer. A durable synthetic service models the preexisting estate and records GET pagination/readback before and after adoption; adoption makes zero service-policy mutations. The journey checks the exact saved plan, operation journal, full resulting state and second semantic comparison. These are modeled service semantics and actual bounded local process effects. They do not establish native provider import, Microsoft Graph mutation or tenant convergence. Optional native Atmos resolution is separately labeled configuration-only evidence.

Use `--journey-mode live` for a live-readiness review. It can generate and independently verify local proposals. At planning it reports unresolved gates: provider qualification, authenticated target, observed backend state, single-writer ownership, protected cloud approval, and an available cloud executor. There is no live mutation path. JSON, session flags and synthetic receipts cannot satisfy these gates. The optional connected native OpenTofu output-only fixture also cannot establish provider or tenant qualification.

## Resume, edits and recovery

- `save`, EOF and Ctrl-C suspend. Resume with the same session path and `--journey`.
- Missing or malformed source evidence on resume presents a recovery prompt. Restore the evidence or edit its path; no completed flags are trusted while observation fails. Pending uncertain operations require their original bound paths and target before reconciliation.
- The connected modeled lifecycle supports one to eight selected policies. Full inventory may include up to 1,000. Deterministic per-policy capture projections preserve the original inventory hash and all selected fields; the strict single-policy normalizer remains unchanged.
- `cancel` preserves evidence and requires `resume` before another action. Saving a cancelled session does not erase cancellation.
- `back STAGE` archives that stage's receipt and all descendants. Earlier generated files remain preserved.
- `edit input PATH`, `edit context PATH`, `edit output PATH`, `edit stack NAME`, `edit component NAME`, and `edit selection UUID,UUID` invalidate their dependent stages. Selection is by UUID, never display name.
- Existing proposal trees are never overwritten. Choose a fresh output after editing inputs or target intent.
- Approval capabilities exist only in process memory. Suspension before execution archives the approval receipt; resumed execution requires a fresh `approve` command.
- Generation and execution write an in-flight checkpoint before dispatch. An uncertain outcome enters `recovery_required`. Only `reconcile`, `save`, or `cancel` is useful there; no automatic replay is available. Complete independently verified generation can recover without rewriting it. An uncertain process without complete verifiable operation evidence remains blocked for investigation. A definite rejection before dispatch removes the approval and returns to review, allowing a new plan and approval.

A cooperative exclusive lock guards each interaction and is rechecked before writes. A stale-looking lock is not proof that the owner is dead. An abruptly interrupted process may require manual lock investigation; the journey never breaks locks based on age.

## Evidence and contracts

The sibling `SESSION.journey` directory holds receipts, generated contexts, fixed-runner attempts, the selected protected local executor, operation journal and archived receipts. Receipts form an ordered hash chain. Reconstruction rereads the current source, context, repository, generated file closure, executable, saved plan and operation state. It reruns the independent engine checks. A session's `completed` list is a display hint only; it cannot advance progress. Missing receipts, symlinks, edited source bytes, forged assurance labels and rehashed generated manifests stop the chain at the earliest unsupported stage.

`contracts/journey-actions.json` is the closed action vocabulary with ordered prerequisites, read/write scope, authority and recovery. `contracts/journey-semantics.json` states what each evidence class establishes and what it cannot establish. `contracts/journey-receipt.schema.json` validates the envelope; runtime reconstruction also derives and compares the exact stage payload. `check_action()` is read-only: it cannot claim possession of a process-local execution grant.

This is local consistency evidence under a cooperative filesystem model, not cryptographically authenticated evidence against an adversary controlling the plugin, source, executable and operating system. Production ownership and authenticated cloud evidence remain independent requirements.

Run the retained qualification with the installed runtime dependencies:

```bash
python scripts/qualify-journey.py --output /absolute/fresh/qualification
python scripts/qualify-journey.py --cli --output /absolute/fresh/operational --snapshot /absolute/fresh/evidence
python -m unittest plugin_tests.test_journey_completion
```

The qualification runs all stages with the bundled synthetic capture and records the exact answers, results and hashes. `--cli` runs the actual command from another working directory. An optional compact snapshot omits the copied executable and labels itself as record-only evidence, with the omitted runtime hash and reproduction instructions. Tests exercise stale source, changed generated bytes, forged receipts, closed actions, back/edit, cancellation, interrupted approvals, uncertain-write recovery without replay, output conflicts, production gate preservation and live mode blocking. The qualification does not claim a live acceptance run.

## Stateful service and optional native tool qualification

`intune_iac/modeled_service.py` supplies a bounded, durable, synthetic-only request model. It implements complete GET pagination, immutable IDs, revision/ETag checks, create/update/delete, wrong-tenant rejection, denied/throttled requests, partial policy-before-assignment writes, lost responses and fresh readback. Its local request ledger records intended input, revisions, outcome and actual modeled mutation effects. It opens no network connections, receives no real credentials and does not emulate Microsoft authorization or service timing. The standard adoption journey uses only GETs; mutation/fault cases run separately through the explicit model API.

The model oracle treats nested JSON scalar types strictly, binds continuation paths to the same collection/owner, rejects absent/null assignments and retains allowed list permutations. Shared process/filesystem access is a cooperative integrity boundary; local receipts do not establish hostile-host or organizational attestation.

For actual pinned Atmos configuration comparison within the connected journey, supply `--atmos-executable /absolute/pinned/atmos --repo /absolute/inert/repository --stack physical-manifest --component component-name`. The current local qualification profile admits Atmos 1.230.1 by exact Linux AMD64 SHA-256 and artifact byte count. It forces full descriptive output, disables provenance expansion and treats native evaluation errors strictly. Atmos 1.199.0 remains an explicitly legacy reproduction profile only. Unsupported repository execution, hooks, functions and templates remain rejected. The stage invokes the native comparator in its existing network-denied profile and persists a source/tool-bound receipt. Resume reconstructs its independent section comparisons and invalidates changed tools, source files or selectors. Atmos context labels never authenticate Entra identities or backend ownership. This option does not enable provider/Graph mutation.

For actual OpenTofu saved-plan execution, supply `--tofu-executable /absolute/pinned/tofu`. The selected Linux AMD64 executable must match the admitted OpenTofu 1.13.1 SHA-256 and artifact byte count for the current local qualification profile. OpenTofu 1.10.0 is retained only for legacy reproduction. The journey copies it into a private disposable output-only fixture, initializes a local backend, and saves a plan containing the complete modeled semantic estate. The source locator and hash, copied tool, configuration, saved plan, initial state, lineage and serial are checked before approval and execution. `approve` creates a process-local grant; `execute` applies that exact saved plan. Convergence creates a distinct `second.tfplan` and verifies its native JSON has no changes while retaining the original approved plan, state lineage and serial. Resume inspects the existing second plan; it does not replay plan or apply. The fixture uses no Microsoft365 provider, imports no Intune resource and invokes no Graph request. This is `native_local_opentofu_only` evidence and completion remains `complete_simulation`.

Both options can be combined. Replay a full connected native comparison and output-only execution with:

```sh
python scripts/qualify-connected-atmos.py --output /absolute/fresh/evidence \
  --atmos-executable /absolute/pinned/atmos --tofu-executable /absolute/pinned/tofu
```

The normal wizard support limit is eight selected modeled policies; complete raw capture inventory may be larger within its separate inventory bounds. Full service mutation, denied requests, partial assignment writes and lost responses are model API qualification, separate from this adoption journey’s GET-only service readback.

Replay new connected navigation evidence with:

```sh
python scripts/qualify-journey-navigation.py --output /absolute/fresh/pty-evidence
python -m unittest plugin_tests.test_stateful_service_epoch
```

The PTY qualification drives back, multi-policy selection, cancellation, SIGINT, restart, fresh approval, execution, readback, output editing and missing-source recovery through real CLI processes. Fault/mutation API tests and native-tool evidence are reported separately. Failed attempts remain retained; a fresh output path is always required.

## Current durability limitation

This epoch retained two unexplained workspace-path PTY outcomes: a session lock remained after a child reported success, and an old plan receipt appeared after a later replanning attempt. The later instrumented five-process run succeeded with no immediate intended-write/hash mismatch or lost lock ownership, but that nonreproduction does not establish the cause or close the earlier finding. Do not claim the affected supported-host restart/replan durability gate is qualified. `scripts/qualify-journey-storage.py --output /absolute/fresh/evidence` records task-owned process IDs, commands, absolute paths, intended/observed byte hashes and file/lock identities to continue investigation. Retain the prior artifacts; never delete another process’s lock or infer cloud success from a local completion flag.

Exact admitted artifacts and profile labels are in `intune_iac/native_pins.py`. The current release candidates were acquired and signature-verified separately from the legacy tools. Remaining dependency advisories and missing native provider/host/tenant gates preclude production acceptance. Earlier performance receipts retain their original source and tool hashes; they are not measurements of the upgraded native profile. A source or pin change invalidates bound approvals and native comparison receipts.
