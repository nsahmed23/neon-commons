# Protected local native execution

`intune_iac.protected` now executes actual bounded child processes and actual
pinned OpenTofu saved binary plans against **new disposable local fixtures**. The pins are those of
`native_pins.py`: OpenTofu 1.13.1 is the current local qualification (`current_local_qualification`) and
OpenTofu 1.10.0 is the legacy profile (`legacy_reproduction_only`), kept to reproduce earlier fixtures.
It is not an Intune/provider/cloud mutation adapter. All public results retain
`execution_authorized: false`, which means no cloud authority. The enterprise
execution gate remains open.

Two concrete modes are supported on Linux AMD64 with `libseccomp.so.2`:

| Mode | Executed implementation | Support boundary |
|---|---|---|
| `synthetic_local_process_only` | A package-owned Python worker in a separate isolated child process | Bounded JSON state transition, useful for fault injection and the guided simulation; no provider semantics |
| `native_local_opentofu_only` | Exact Linux AMD64 executable of either pin: OpenTofu 1.13.1, SHA-256 `a325c8c2f6834575e440b03c2ba67f94256072754ac7787fea718be6f01fef6a` (`current_local_qualification`), or OpenTofu 1.10.0, SHA-256 `0a9eda0f0898896969492504a6ce778f310675e8a1eb960434c26806cd252627` (`legacy_reproduction_only`) | Package-generated configuration with one literal output, default workspace and local state; no provider, module, resource, hook, provisioner or cloud backend |

The modeled executor (`synthetic_local_process_only`) names the engine version of the profile of the project it
executes: a project generated under a 2.0.0 context gets OpenTofu 1.13.1, recorded as `engine_version` in the
executor manifest, and its modeled plan says 1.13.1. An executor with no recorded `engine_version` is the legacy one
(every executor made before the migration, and the frozen journeys): its plan says 1.10.0, byte for byte as before.
The modeled executor runs no OpenTofu binary.

The native pin was measured from the upstream release archive whose digest was
checked against the official release checksum list. This is checksum provenance,
not an independent signature-verification claim. The executable is copied into
the private fixture. Synthetic executable identity is independently checked
against the running host interpreter, not merely against a writable manifest.
The host interpreter, standard library, dynamic libraries, kernel and package
installation remain trusted runtime dependencies.

## API and exact action binding

```python
from intune_iac.protected import (
    create_native_local_executor, prepare_native_operation,
    approve_native_local_operation, execute_native_operation,
    read_native_operation, reconcile_native_operation,
)

executor = create_native_local_executor(
    "/absolute/new-local-fixture", executable="/qualified/tofu",
    initial_value={}, desired_value={"policy_hash": "synthetic-example"},
)
request = prepare_native_operation(executor, ttl_seconds=300)
approval = approve_native_local_operation(request, executor=executor)
result = execute_native_operation(
    request, "/absolute/private-receipts", executor=executor, approval=approval,
)
```

`create_synthetic_executor(root, *, initial_value, desired_value)` and
`approve_synthetic_operation(request, *, executor)` provide the explicit
synthetic equivalents. Open existing fixtures using `SyntheticExecutor(root)` or
`NativeLocalExecutor(root)`. Creation of a native fixture performs a local
bootstrap `init`, `plan`, and saved-plan `apply` to establish the initial value;
this is limited to the new generated output-only fixture. Existing arbitrary
Terraform repositories and executable paths with a different digest are rejected.
Top-level null native outputs are outside this slice because OpenTofu omits them
from state. Template delimiters `${` and `%{` are rejected recursively, both when
creating values and when reopening persisted configuration.

`prepare_native_operation` creates the binary plan itself, obtains JSON through
the same pinned executable, verifies state did not change during preparation,
and writes one exclusive preparation record. It accepts only a TTL from 1 to 300
seconds. No caller command, environment override, backend flag, target flag,
variable file, refresh suppression, import or destroy action is accepted.

The request binds the concrete action and mode, fixture path hash, executable,
worker and implementation bytes, configuration, binary plan, raw plan JSON,
complete pre-state bytes, pre-state lineage and serial, pre-value and desired
value. Approval is a nonserializable process-local object bound to the entire
request and its expiry. Serialized JSON cannot create an approval, and this
local helper cannot approve a cloud action. A process-local approval is consumed
before dispatch and a durable target-local consumption marker prevents replay after restart or through a different receipt directory.

`inspect_executor(executor)` returns only state/value/lineage hashes, serial, mode
and desired-value hash. `validate_native_operation(request, *, executor,
require_fresh=False, require_state=False)` validates all persisted request and
artifact bindings and returns a safe validation result or raises a fixed
`AppError`; callers use it during read-only journey reconstruction. Setting
`require_state=True` requires the original complete pre-state. Final execution
always requires freshness and the original state.

## Fixed process boundary

The runner uses argument arrays, no shell, a private working directory and HOME,
a generated CLI configuration, fixed default workspace, closed inherited file
descriptors and a minimal environment. Parent cloud credentials, token files,
proxy variables, `TF_CLI_ARGS*`, logging overrides, `LD_PRELOAD`, `PYTHONPATH` and
user CLI configuration are not inherited. Linux seccomp denies socket operations
and fails closed if unavailable. It also denies `fork`, `vfork` and `clone` calls
that do not create a thread in the same thread group. `clone3` returns `ENOSYS`
so a runtime can use the inspected `clone` fallback. Ordinary runtime threads
remain supported; new child processes are forbidden after the initial launch.
File creation uses a private umask.

Before executing any native parser, every child receives hard resource ceilings:

| Resource | Maximum | Exact scope |
|---|---|---|
| Address space (`RLIMIT_AS`) | 4 GiB | Entire process, including all its runtime threads and mappings |
| CPU (`RLIMIT_CPU`) | 20 seconds | Process CPU consumption across threads; distinct from elapsed time |
| File size (`RLIMIT_FSIZE`) | 64 MiB | Each regular file; stdout/stderr pipes use the separate byte budget |
| File descriptors (`RLIMIT_NOFILE`) | 256 | Per-process descriptor ceiling |
| Core dumps (`RLIMIT_CORE`) | 0 | No core-file output |

A stricter inherited hard limit is retained rather than raised. Failure to set a
limit prevents exec. The limits are inherited across native exec and apply to
`tofu show` while it parses a saved plan **before** semantic admission. Tests
reserve, without touching, a 5 GiB mapping and attempt a 65 MiB sparse file;
both are denied. Native OpenTofu and Atmos qualification exercises the same
supervisor limits.

These are per-process/per-file bounds, not a disk-volume quota or a deployment
cgroup. Runtime threads remain allowed and share the process CPU/address-space
budgets; kernel task-count isolation still requires a qualified host cgroup or
container limit. No `RLIMIT_NPROC` claim is made: that control is UID-scoped and
is not a reliable per-operation/root process fence. Process creation is instead
rejected by the Linux AMD64 syscall policy above.

Each process also has a 30-second total deadline and a combined 2 MiB stdout/stderr
budget. A selector drains both pipes; timeout, nonzero exit and excessive output
produce fixed errors without returning command output, secrets or exception
text. The process group is killed on completion or failure as a cleanup fallback.
A controlled test independently verifies cleanup of a pipe-holding descendant
with the stronger no-fork guard disabled only inside that test. Descriptors and pipes are closed. The executable, synthetic worker
and saved plan are opened and hashed as file descriptors; execution/plan input
uses those pinned descriptors. All initialized local backend metadata and runtime
directory contents must stay within the fixed generated slice.

The reusable `_supervise` primitive is private trusted-code infrastructure; it
is not exposed as a command API. A caller using it directly must separately
qualify the executable and construct fixed arguments. The package's public
executor only dispatches its closed command registry. This is not a general
filesystem sandbox or a defense against a hostile administrator racing private
files, replacing the runtime, or bypassing the kernel. Windows, network
filesystems, power loss and multithreaded process-host qualification remain open;
the Linux process launcher uses a narrowly scoped `preexec_fn` to load the
prebuilt seccomp filter.

## Native output-plan counterexample

Actual OpenTofu 1.10.0 output-only plans demonstrated that refresh can recompute
`prior_state.values.outputs.fixture.value` to the new configured output while
`output_changes.fixture.before` correctly contains the old persisted value. The
generic conservative reviewer reports `prior_output_value_mismatch`; it remains
unchanged and that blocker is preserved in every relevant native request.

The native local slice separately checks the fixed generated configuration,
absence of all resources/modules, exact single output/change shape, known
non-sensitive before/after values and masks, and the independently read persisted
pre-state. Only this documented output-only discrepancy can be qualified there.
Before approval and each native execution-context check, the pinned engine re-derives JSON from the opened saved binary plan and must reproduce the bound raw JSON digest. The strict slice is reviewed again; rewriting both the preparation record and a JSON sidecar cannot substitute an embedded resource or provisioner. Synthetic saved-plan value/before-state and JSON review actions are also independently compared to the bound state and desired value. The raw plan is retained unchanged. This does not relax Intune plan review or
qualify any provider plan. See the measured native report and raw plan under
`research/completion/protected-native-*`.

## Time authority for the approval window

The approval window, `created_at <= t < expires_at`, is judged on an effective
time that never goes backward, never on a bare wall-clock reading
(`intune_iac/clock.py`):

- **Time authority.** Wall time is the only persisted, portable timestamp. Beside
  each prepared request, `clock.json` records the latest wall time any check of
  that operation saw, as its effective time: the wall clock or the checking
  process's carried reading, whichever was later (its high-water mark; creation
  is the first point). It only
  rises: its read, comparison and write, and the expiry record below, happen
  under one lock (`clock.lock` beside it). Within one process, monotonic time
  carries the latest reading for the
  same operation forward by the elapsed time; it is never persisted or compared
  across processes. The effective time is the greatest of the wall clock, the
  high-water mark and that process floor.
- **Backward steps.** A wall clock reading earlier than the floor by more than
  two seconds means the true time cannot be established. Approval and every
  check before dispatch refuse with `clock_moved_backward`, and nothing is
  dispatched. Recovery: correct the host clock, or wait until it reads at or
  after the recorded time, then submit again (a long-running workbench carries
  the high reading forward, so restart it after correcting the clock), or
  prepare a new request. A damaged time record refuses for good
  (`clock_floor_invalid`, audited like the others): prepare a new request.
- **Expiry is recorded first.** When the effective time reaches `expires_at`, an
  exclusive `expired.json` is written beside the approval before the refusal
  (`expired_request`). Every later check refuses while it exists, after a clock
  rollback, a restart or from another process alike. The workbench's operation
  journal also records `approval_refused` with the code; its status stays
  `prepared`, since nothing was dispatched.
- **Restart and the boot session.** `clock.json` (schema `intune-clock-floor/2`) also records, in the same atomic write as
  the mark, the host's boot identity (`/proc/sys/kernel/random/boot_id`, read fresh at every observation), its clock domain
  (the time-namespace offset line, where the kernel has one) and `CLOCK_BOOTTIME`. Within the same boot and clock domain the
  floor includes the mark plus the boot time elapsed since it was recorded, which a wall clock cannot move, so a restart
  carries the time that passed while no process ran: an approval judged open at T50 is closed at T60 on the wall if the boot
  clock shows 70 seconds went by. Expiry compares with no added tolerance. A different boot, a different domain, a boot time
  that went backward or no readable boot source is lost continuity: the carried part is dropped and the mark alone remains.
  Schema 1 files stay readable and are never lowered. The stored boot time is only a difference within one boot.
- **Open judgments.** The shared decision (`intune_iac/validity.py`) records every open judgment as a durable row, committed
  on its own under the locks before the caller proceeds, so a later failure or process death cannot erase it. An artifact
  found judged open in a session that cannot be verified now (another boot or domain, an unreadable session, another
  process on a host with no boot source) is held with a distinct message: how much of its time has passed cannot be
  established; it stays held until the host clock reads at or after its expiry (then it is closed and recorded) or until it
  is prepared anew. Every deadline armed from an expiry takes the recorded floor's effective time, not the bare wall clock.
  The broker keeps its own recorded time and open judgment in its journal directory.
- **A recorded forward blip.** The floor carries the largest time any check recorded plus the boot time since. A wall
  clock that jumped forward and was recorded therefore holds for the rest of the boot, and restarting does not clear it:
  correct the host clock, prepare the approval anew, or start a new boot of the host (for example `wsl --shutdown`).
- **Limits.** A backward step is detected between readings this operation recorded or this process made and, within one
  boot, across processes. Skew between hosts that never shared a recorded time is not detected, and nothing here claims
  protection against it. The guarantee assumes the host's boot clock is continuous: under WSL2 a paused virtual machine may
  not count the paused time in `CLOCK_BOOTTIME` (to be measured on the host, not assumed), and then protection across the pause
  falls back to the mark. A snapshot restore that brings back both clocks and the records is outside the model, and a
  host with no boot source degrades to holding any approval judged open by another process. Artifacts first judged by code
  that predates the boot session have no recorded session; the guarantee starts with their first judgment under it. A source
  edit's acknowledgment window ends with its call, and a successor's service preimage is bound to the process that read it, so
  a restart needs a new acknowledgment or a new read.

The workbench store orders observations the same way. Between two of the store's
own collections from the same modeled service, the later run (local collection
order) is current, even when a clock step stamped the earlier one later. An
imported capture carries its source's capture time, which orders it against
anything else, except that a capture stamped later than the store's clock at
its import gives way to the store's next own collection. Migrating a v1 store
seeds its heads by the same run order. Original timestamps are kept as
recorded; age-based freshness,
a known source change and an incomplete collection stay separate conditions.

## Durable outcomes and recovery

The exact fsynced, hash-linked event prefix is:

`prepared → authorized → dispatch_started → readback_verified → completed`

Directories and records use exclusive creation and restrictive permissions.
Target-local locking is independent of receipt directory, so choosing another
receipt path cannot start a second writer. There is no timeout-based lock theft.
Ownership is rechecked before dispatch, after it and before release. A missing or
changed owner record is never removed by the old operation.

The persisted `dispatch_started` boundary makes later failures uncertain even if
native invocation fails. Successful completion requires independent state
readback, unchanged lineage, a legal serial transition, the desired value,
unchanged artifact bindings, and a successfully persisted and reread final
receipt. A changed value requires exactly one serial increment in this slice;
a no-op may retain the byte-identical pre-state or advance the serial once.
Failures during readback or receipt persistence retain the target lock and
return `outcome_unknown`.

`read_native_operation(operation_id, state_dir)` validates the bounded exact
schema, contiguous prefix, chain links and state transition before returning
`status`, `request`, `events` and `receipt_sha256`. Corruption returns `unknown`.
`reconcile_native_operation(operation_id, state_dir, *, executor)` independently
rereads the state and returns `desired_state_observed`, `matches_precondition`,
`diverged` or `unknown`; `replay_authorized` is always false. Matching a value
cannot establish who caused it, and a replaced lineage cannot claim success.
Reconciliation never dispatches, reapproves or releases a retained lock.
Local journals establish consistency and cooperative filesystem durability, not
authenticated audit storage against an actor able to replace the whole history.

## Azure backend readback and unresolved authentic context

`intune_iac.native_context.collect_backend_observation(document, *,
storage_token, timeout=10)` adds a real read-only Azure Blob REST collector. It
uses the validated target's exact public Azure storage origin and resolved blob,
with an independent opaque storage credential:

1. HEAD the existing blob and require bounded length, a strong ETag and lease properties.
2. GET the same blob with `If-Match` for that ETag.
3. Validate full raw state digest, version, lineage and serial against the bound target.
4. HEAD again with the same `If-Match` and require unchanged properties.

Redirects, partial responses, compression, duplicate relevant headers, oversized
state, changed ETags and unavailable reads fail closed. There are no writes,
lease acquisition, account keys, state initialization or follow-up service URLs.
TLS uses the default verified trust store. Socket/body reads have a deadline;
DNS remains bounded by the OS resolver, so a deployment must additionally
supervise the collector to guarantee a total wall-clock limit. Test responses
are simulated; no credential or live tenant call was available here.

An enterprise operator with independently supplied read-only credentials can invoke
this collector explicitly through Python; credentials are never CLI arguments:

```python
import json
import os
from intune_iac.io import load_json
from intune_iac.native_context import collect_backend_observation

# The host supplies this ephemeral, storage-audience credential independently.
# This package does not obtain a token or infer its executing principal.
report = collect_backend_observation(
    load_json("/protected/observed-target.json"),
    storage_token=os.environ["INTUNE_READONLY_STORAGE_TOKEN"],
    timeout=10,
)
print(json.dumps(report, sort_keys=True))  # Hashes/status only, never the token.
```

The target must be fresh, include its exact state byte digest/lineage/serial,
and identify the existing blob. This invocation was **not run against Azure**.
The API does not save the bearer credential or raw state. Missing credentials
are a visible dependency, not a reason to supply a placeholder token or claim a
live observation. To replay the available native local qualification instead:

```console
python research/completion/protected-qualify.py --executable /qualified/tofu
python -m unittest plugin_tests.test_protected_completion -v
```

An accepted service read establishes service access for the supplied credential,
not the executing principal or federation subject. Lease status does not prove
ownership of that lease. `inspect_native_context(document, *, attestations=None)`
always reports the remaining hard gates; supplied signed-looking JSON cannot
satisfy them. `qualification_contract()` defines exact separately protected
credential-provider, runtime, backend, ownership/fencing and approval bindings
for an enterprise host implementation. No live credential adapter, approver
trust root or distributed operation service is fabricated.

The Microsoft Azure Identity and Blob Storage skill sources and companion
references were read in full and are hashed in the protected source ledger.
Their guidance informs explicit credential scoping, service metadata reads and
transport cleanup. This implementation does not add or claim execution evidence
for an unpinned Azure SDK. Ambient developer credential chains, logging of
credential exceptions, sovereign-cloud examples and write examples are outside
this read-only public-Azure contract.
