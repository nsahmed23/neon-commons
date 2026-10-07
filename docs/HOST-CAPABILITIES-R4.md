# Native host implementation and qualification gates

Native Windows Workbench execution is an implementation gap as well as a missing qualification environment. The existing protected storage/process contracts use POSIX and Linux primitives. A native Python interpreter reached through Git Bash or PowerShell does not supply those primitives, and a usable help screen cannot establish native Workbench support.

`intune_iac.host_capabilities.report()` performs read-only discovery of platform, standard-library symbols and procfs paths. It creates no files, reads no credentials, starts no process and contacts no service. `require_profile(PROFILE)` rejects missing implementation primitives before adapter imports, store access, credentials or mutation. It raises `host_profile_unsupported` with a structured `details` record. This gate adds no compatibility shim and does not replace any adapter’s existing enforcement.

The declared profiles are `workbench_store`, `graph_observer`, `protected_worker`, `artifact_vault` and `visual_workspace`. A profile reporting `IMPLEMENTED` means its host prerequisites were discovered; the record explicitly keeps `platform_qualified: false` and `production_approved: false`. Discovery cannot prove actual file/ACL behavior, locks, namespace durability, native tool isolation, identity, service response or endpoint effect.

The vault currently imports the pinned validator from `approval_authority.py`; that module imports `fcntl`. Its profile therefore requires that dependency even though the encryption operation itself does not acquire an approval lock. The initial omitted dependency and its corrected negative control are preserved in the R4 host-capability evidence.

## Actual implementation gaps

| Existing boundary | Discovered entrypoints | Missing native Windows implementation | Required independent evidence |
|---|---|---|---|
| Private store and history | `workbench_store.py::_private`, `create`, `_connection`; imported `modeled_service.py` | Effective-UID/mode assumptions must become token/SID ownership and DACL checks; no-follow descriptor traversal must become validated handle-relative reparse-safe opens; hard links/file identity, private DB sidecars and atomic replacement/durability need equivalent checks. | Native NTFS private/foreign-owner/DACL/reparse/hard-link fixtures, no-outside-write assertions, concurrent DB use, failed writes, interrupted migration and backup/restore. |
| Cooperative locks | `modeled_service.py`, `workbench_scheduler.py`, `approval_authority.py`, `provider_execution.py` | `fcntl.flock` is unavailable to native Windows Python. A reviewed native locking primitive and abandoned-owner recovery are not implemented. | Native contention, stale/abandoned lock, PID reuse, interrupted acquisition and durable one-time dispatch/recovery. |
| Protected native worker/provider | `protected.py` supervisor/guard and saved-plan descriptors; `provider_execution.py`, `protected_worker.py` | `/proc/self/fd`, procfs descendant census, `waitid(WNOWAIT)`, Linux process/session ownership and seccomp are not Windows implementations. A Windows process/job/handle and network/filesystem authority boundary is required; adopting a process library alone is insufficient. | Exact Windows process tree and handles before/after timeout, cancellation and partial writes; descendant cleanup oracle, process escape variants, exact saved-plan binding and native provider lifecycle. |
| Persistent reader jobs | `observation_jobs.py`, `observation_reader.py`, `workbench_scheduler.py` | Jobs explicitly require Linux; protected job storage, locking, credential handoff, scheduler integration and native recovery are not implemented for Windows. | Native independent scheduling, reader identity, overlap, restart, partial publication, expiration, missing pages and authenticated last-good history. |
| Sensitive artifact protection | `artifact_vault.py`, `azure_backend.py`, `provider_journey.py` | Private POSIX descriptor opens and directory synchronization plus Linux-qualified crypto/runtime handling need reviewed native equivalents. Windows inherited handles/approved secret delivery are not a POSIX credential FD. | Actual ACL/encryption/key recovery, inherited-handle leakage checks, exported-JSON protection, state/plan byte equality, native backend identity and lease loss. |
| Visual workspace | `workbench_tui.py::visual_supported`, `terminal_session`, `KeyReader` | `termios`/POSIX input and mode restoration are not a native Windows console/mintty adapter. The current implementation falls back to text presentation, but the private store remains unsupported. | Actual mintty and chosen terminal keys, resize, Unicode width, control-sequence inertness, non-color/reduced-motion, detach/resume and restoration, including interrupted reads. |

The existing Linux implementation and its evidence remain valid within their recorded scope. Nothing in this report relabels Linux, WSL, a mocked `win32` string, mocked ACLs, an import-denial test or a successful PowerShell preview as native Windows qualification. Native macOS also cannot inherit Linux protected-worker/procfs/seccomp evidence.

## Safe gates now and continuation

The portable command parser supports help/discovery without importing the optional execution adapters. The application should gate before native imports:

- Workbench store/history/inspection and synthetic service routes require `workbench_store`.
- Observer/scheduler routes also require the Linux `graph_observer` primitives.
- Protected worker dispatch requires `protected_worker`.
- Sensitive artifact operations require `artifact_vault`.
- Visual mode additionally requires `visual_workspace`; no-TTY text presentation is only a rendering fallback.

On native Windows before the adapters exist, `workbench init`, store-backed terminal/inspection, worker and artifact routes must return structured `UNSUPPORTED` without creating the requested store, dispatching a process or accessing credentials. This is a successful **negative control**, not a passed functional requirement. The required Windows pilot route remains blocked by missing implementation.

The native Windows qualification procedure already exists at `scripts/qualify-windows-workbench.py`; its `--help` specifies exact package, source, native interpreter, Git Bash and PowerShell pins. Execute only on an authorized disposable native Windows host with the exact final package:

```text
python scripts/qualify-windows-workbench.py --plugin VERIFIED_EXTRACTED_PACKAGE --output NEW_EVIDENCE_DIRECTORY --python ABSOLUTE_NATIVE_PYTHON --python-sha256 PYTHON_SHA256 --bash ABSOLUTE_GIT_BASH --bash-sha256 BASH_SHA256 --powershell ABSOLUTE_PWSH7 --powershell-sha256 PWSH_SHA256 --package-zip EXACT_PACKAGE_ZIP --package-sha256 PACKAGE_SHA256 --source-commit FULL_REVIEWED_COMMIT
```

This is an existing executable procedure, not an assertion that its store/interactive gates currently can pass. Record unsupported private-store results explicitly. After a reviewed native adapter is implemented, qualify that adapter’s independent security invariants first, then rerun the actual launch/store/terminal routes. Keep native service/provider/backend/device evidence and organizational approval separate. The Bash wrapper’s invocation-local MSYS exclusions and the PowerShell wrapper’s exit/cleanup behavior still need their actual native shell evidence; they cannot repair the underlying storage or worker implementation.

Implementation owner: Intune Workbench host-adapter maintainer. Qualification environment owner: the organization’s Windows endpoint/runner owner. Security disposition: organizational AppSec. Production/pilot decision: the accountable service and release owners. None of these decisions can be inferred from the capability report.

Changed-scope local checks:

```sh
/workspace/intune-runtime/bin/python -B -m unittest plugin_tests.test_host_capabilities_r4 -v
```

These tests validate discovery, structured fail-closed gates and import-denial fixtures on the current Linux host. Their simulated missing primitives are explicitly not native Windows evidence. Source/artifact hashes and actual CLI integration receipts determine applicability.
