# Inactive Windows observation continuation

This component implements the missing native storage route for the existing
bounded Graph capture engine and atomic observation publisher. It does not
activate the ordinary Windows host profile, install a schedule, load a live
credential, authorize a service write or establish platform qualification.

`windows_observation.bind_native_target(root, tenant_id)` constructs a target
using actual Win32 private storage. The target exposes `capture(reader,
object_id, output)`, `publish(captures, job_id=..., attempt_id=..., failures=...)`
and `close()`. Capture and publish reuse the existing typed reader, semantic
validator, SQLite schema, comparison/history and last-good behavior. No alternate
normalizer or replacement engine is introduced. The original POSIX `capture`
and `publish_batch` entrypoints preserve their guards and exact store admission.

The target binds its process, root, tenant, actual directory/database identities
and filesystem instance. Native handles are retained through capture validation
and database publication; schema and tenant are checked again after SQLite's
`BEGIN IMMEDIATE`, before mutation. Captures belong to that exact target storage
instance. Restart requires newly authenticated reads: serialized metadata cannot
reconstruct an authenticated process-held observation capability.

The public POSIX publisher explicitly rejects native-storage captures before
transaction dispatch. A retained failing control showed that otherwise the
ordinary public API could relocate a target-bound capture into a different
same-tenant POSIX store. Native publication must use its original sealed target.

The laboratory target is a private test seam and rejects a typed LiveGraphReader
before policy GET. A LaboratoryGraphReader on a physical Windows host remains
laboratory service evidence. Raw imported captures continue to carry unverified,
caller-supplied source facts. Native storage does not promote these labels.
`CapturedObservation` now checks a digest of both its semantic batch and bound
source facts: mutating source labels was previously publishable. This repair is
cooperative in-process integrity, not a sandbox against hostile same-process
Python that can access private constructors or arbitrary object internals.

Output consists of a NEW protected directory and raw subdirectory, CREATE_NEW
files, exact ordered raw response bytes and existing export/context/receipt
formats. Required file and namespace barriers cannot be skipped. Failed and
uncertain directories, raw attempts and temporary artifacts are retained.
Before mutation the target records an observation intent in addition to the
store connection's intent. An observation outcome is recorded only after the
SQLite session, barriers and outer target guards finish. These are different
journal scopes, not duplicated observations. A receipt describes database
publication, not subsequent result delivery, its own future cleanup or power-loss
durability. A failure after commit is not a failed mutation; retain both the
exception's storage/observation outcome and every intent/outcome before recovery.
No automatic mutation retry is inferred from these receipts.

The new contract tests use actual capture/SQLite and recorded Win32 effects.
They are not native Windows proof. The native procedure independently checks
raw bytes and SQLite counts and invokes the actual qualification-only readonly
text launcher. It uses invented Graph replies, so even a native PASS does not
establish authenticated Graph/service/device evidence.

From the exact reviewed source, inspect the command help first:

```text
python -B scripts/qualify-windows-observation.py --help
```

Prepare an exact source pin manifest with `source_commit` and `files` matching
the procedure's `REQUIRED_FILES`; retain its SHA-256 and independently verify
that those bytes match the reviewed commit. On native 64-bit CPython 3.12,
owner-only NTFS parent and Windows SQLite VFS, run:

```text
python -B scripts/qualify-windows-observation.py --qualification-only --disposable-parent C:\Pilot\Private --output C:\Pilot\Evidence\observation-01 --source-pins C:\Pilot\Evidence\source-pins.json --source-pins-sha256 EXACT_SHA256
```

All paths must already have reviewed private ancestors; output/store/capture
children must be new. Retain RESULT.json, exact source pins, command stdout/stderr,
all created fixture files, native journal outcomes and any failed attempts.
A missing namespace FlushFileBuffers barrier reports UNSUPPORTED/uncertain,
retains outputs and blocks enablement. Linux reports BLOCKED with zero native
checks and commands before creating a native store or invoking native APIs.

Remaining implementation is the native independently scheduled job filesystem,
Task Scheduler adapter and chosen credential delivery route. Those must reuse
this sealed target rather than manufacture authentication from JSON. Native
Windows/Git Bash/mintty/PowerShell, actual DACL/reparse/SQLite VFS sidecars,
locking, restoration and host failure still require real native evidence.
Live Graph observation requires separately authorized identity and independent
service readback. Provider/apply, backend, devices, security disposition and
organizational approval remain separate gates.
