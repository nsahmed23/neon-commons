# Inactive native signed-worker evidence verifier

`windows_worker_evidence.py` implements a guarded Windows verification component
for the same signed read-only evidence contract. It never starts a worker,
provisions a key, chooses a second platform, opens a new service listener or
activates the ordinary Windows profile. `windows_worker_evidence_store.py` implements
persistent ingestion/reopen over the existing inactive native Workbench store.
Shared views and navigation reverify received signed snapshots; direct POSIX
worker journals remain unsupported on native Windows.

An independently approved `windows-worker-evidence-verifier/1` descriptor pins the
exact private Windows libsodium DLL path, byte length, SHA-256, library version,
`win64-cdecl-ed25519-v1` ABI and `system32_only` dependency policy. Supported ABI
versions are explicitly 1.0.18, 1.0.19 and 1.0.20. No binary is downloaded or chosen
from PATH. The operator must supply and authorize the actual reviewed image and
its dependency provenance; a caller label alone does not qualify it.

The adapter verifies the pinned image as an AMD64 PE DLL, copies exact bytes into
a NEW private directory, checks that copy, and holds no-reparse owner-only native
file/directory handles for both source and copy throughout loading and calls.
A unique path avoids reuse of an old loaded image through a recycled filename.
`LoadLibraryExW` uses only `LOAD_LIBRARY_SEARCH_SYSTEM32` for dependencies; no
current directory, PATH or local-DLL-directory fallback is admitted. Missing
System32 dependencies, exports or exact version fail closed. No loader search
configuration or machine trust is changed.

The image provides existing native Ed25519 detached verification plus the same
strict point/subgroup checks used by the POSIX verifier. There is no Python curve
arithmetic or replacement signature algorithm. Every call revalidates guarded
bytes before and after native functions. Explicit close deactivates the verifier,
unloads its owned reference and releases handles. Primary errors and cleanup
errors remain separate; cleanup interrupts propagate with the primary cause.
Generated private DLL copies remain retained, including failures. This depends
on actual NTFS/Win32 handle and loader behavior; recorded calls do not establish
native protection or ABI safety.

Actual inactive CLI:

```text
python -B scripts/intune-windows-evidence.py --qualification-only inspect --envelope PRIVATE_ENVELOPE --request PRIVATE_REQUEST --trust PRIVATE_TRUST --verifier-pin PRIVATE_DLL_PIN --scratch PRIVATE_SCRATCH
```

`--historical` still verifies current trust and original signatures but returns
historical-only evidence with unknown current status and no admissible baseline.
No flag changes laboratory capture into authenticated live evidence.

`inspect` of a loose file is historical-only: without `--historical` it is refused with
`worker_evidence_inspect_requires_store`, because a loose file has no store to hold the
durable clock mark that keeps an expired or stale envelope from becoming admissible again
after a wall step back or a restart. For current admissibility use `ingest --root` into a
native Workbench store, then `reopen`; both record that mark in the store's own write
transaction (a failed record refuses with `worker_evidence_clock_unrecorded`).

The executable native procedure is
`scripts/qualify-windows-worker-evidence.py --help`. Prepare an approved disposable
Windows x64 CPython 3.12 host, pinned native DLL/ABI/dependency descriptor, fresh
private scratch/output, independently authored positive and negative Ed25519
vectors, the exact signed request/export/trust, literal expected identity and
baseline outcome, and the complete source-file pins plus source commit. Pin each
input's bytes. The harness calls the real guarded loader/verifier, compares each
literal expected signature decision and exact export identity/outcome, retains
result bytes and never sends a tenant mutation. Include weak/mixed-order keys,
bad/truncated signatures, wrong message/domain, changed DLL, missing dependency,
reparse/ACL/replacement and close-interruption negatives in separate preserved
runs. Native process/DLL lifetime and power-loss qualification are still required.

Local tests use recorded Win32 storage/loader/functions and exact source/type
assertions. They do not count as native cryptographic, native platform, AppSec or
organizational approval. The real Linux harness reports BLOCKED with zero native
calls; no permission or host support gate is bypassed.

## Persistent native receipt and navigation

The same launcher has `ingest`, `reopen`, `link` and `history` subcommands; use
`--help` on each for exact required paths. `ingest --root` requires an existing
inactive native Workbench store. `reopen --request-sha256` revalidates exact retained
bytes using current trust and the pinned DLL. `link` additionally takes the selected
`--object` and `--evidence-store`; it records only an inert local pointer. The shared
text commands `evidence-link` and `evidence-history` use that same engine. The
History pane may resume `evidence-history`; mutations, ingestion and link creation
are never replayed from saved navigation context.

An `evidence-attempt-<uuid>` directory holds exact original envelope/request bytes,
including CRLF and malformed input within the bound. Existing guarded CREATE_NEW
files and namespace barriers provide persistence. Received request indexes and
publisher high-water records commit together in the existing native store's
`metadata` table; no schema or host-profile change is introduced. Both POSIX and
Windows invoke `worker_evidence.admit_received` inside their SQLite transaction.
The scope is issuer/publisher identity, tenant/object/operation/manifest; signing
key rotation cannot create a second ordering stream. Indexes are never signature
or approval authority. A later output/barrier failure is uncertain and preserved;
there is no automatic retry or deletion. A same-request replay is idempotent only
for the already retained canonical signed content.

Native store qualification still requires its actual NTFS locks, ACLs, directory
barriers, SQLite/VFS, interruption/recovery and host power-loss routes. Local
component tests use real SQLite and real POSIX signatures with explicitly recorded
Win32 storage effects. DLL tests record loader/export calls separately. Neither
scope establishes a native Windows signature or storage qualification.

The native harness now requires `--evidence-store NEW_PRIVATE_STORE`, creates it
without replacing any destination, then verifies signed ingest, reopen,
shared review/baseline views and persistent history (current admissibility is judged on the
reopened store result, since loose-file inspect is historical-only). It checks complete runtime
source hashes before and after. Native vectors, DLL supply-chain/ABI review,
organizational publisher trust and private artifact transport remain required.
Explicit raw `source_is_synthetic=true` cannot establish an authenticated live
baseline even when both signatures and live classification labels are present;
the contradiction is retained with a non-admissible evidence class.

Current `reopen` and the evidence views read the store's durable clock mark first and open a write connection (which leaves
two permanent root receipts) only to record something: a closed window the mark does not yet cover, a successful judgment at
the observed time that differs in any field from the judgment at the stored mark (a transition), or an observed time more than
60 seconds ahead of the mark. The mark, the decision and the receipt check are one read transaction. The time-dependent checks of a judgment are the two terminal
refusals (`worker_evidence_expired`, `worker_evidence_stale_snapshot`), the earliest-time check (an envelope issued more than the
skew ahead of `now` is refused) and the timestamp range check on `now`; no field of a successful result depends on the time.

While the wall clock reads earlier than the recorded time (the mark or this process's floor) by more than the clock tolerance
(2 seconds), current admission, on `reopen` and on `ingest`, is held with `worker_evidence_clock_moved_backward` (wait until the
system clock passes the recorded time, or correct the clock; `--historical` reads stay available). A refusal at the effective
time is still returned as it is, so a closed window still wins, and a held read records nothing. After the wall passes the
recorded time again, a transition not yet recorded can be observed at most 60 seconds plus the tolerance of real time later than
with a mark written on every read. No observed judgment is ever reversed.

Precondition: the 60 seconds plus tolerance bound holds only while the system clock tracks elapsed time within the tolerance.
The hold compares the wall with this process's own monotonic carry of the wall, as the authorization clock does (`clock.py`,
`clock_moved_backward`), so it cannot tell a backward step from a slow clock or a stopped time service. If the wall drifts from
the process's monotonic clock by more than the tolerance, current admission is held in that process, indefinitely if the drift
keeps growing, until the clock is corrected or the process restarts; `--historical` reads stay available. A held read never
raised the mark, so a new process whose wall has passed the stored mark admits again. The host clock is the remedy.

## Backup and restoration of received history

The ordinary Workbench database-only `backup`/`restore` does not contain received
envelope/request sidecars and cannot by itself restore this history. This was
reproduced with real SQLite: restored indexes pointed to missing attempt files.
Use the separate bounded dedicated-evidence-store route:

```text
python -B scripts/intune-windows-evidence.py --qualification-only copy-store --root RECEIVED_STORE --destination NEW_BACKUP_STORE
python -B scripts/intune-windows-evidence.py --qualification-only copy-store --root BACKUP_STORE --destination NEW_RESTORED_STORE
python -B scripts/intune-windows-evidence.py --qualification-only reopen --root NEW_RESTORED_STORE --request-sha256 REQUEST_CONTENT_SHA256 --trust CURRENT_TRUST --verifier-pin CURRENT_DLL_PIN --scratch PRIVATE_SCRATCH
python -B scripts/intune-windows-evidence.py --qualification-only link --root WORKBENCH_STORE --object EXACT_OBJECT_ID --evidence-store NEW_RESTORED_STORE --request-sha256 REQUEST_CONTENT_SHA256 --trust CURRENT_TRUST --verifier-pin CURRENT_DLL_PIN --scratch PRIVATE_SCRATCH
```

Use `--historical` for an expired proof when the purpose is inspection, never a
current baseline. Current trust, verifier DLL/pin and scratch are supplied separately;
the copy route does not add trust policies, verifier DLLs, signing keys or
credential configuration. Arbitrary received bytes, including failed inputs, stay
unchanged and may contain restricted data; use the existing approved private
retention/transport route and its content review.

The copy admits only a dedicated receiving store: its exact logical SQLite image,
all bounded `evidence-attempt-*` directories (including failed/partial attempts),
original `store-intent-*`/`store-outcome-*` records and earlier copy receipts.
The initial bound is 256 attempt directories, 1,000 received/head metadata rows,
2,048 root nodes and 64 MiB total copied bytes. Unknown names, extra attempt files,
changed indexed bytes, overlapping destinations and existing targets fail closed;
nothing is silently omitted. A new empty PERSIST journal accompanies the logical
database image; the original cold rollback journal remains unchanged at source.
Original receipt paths/scopes are retained and are not relabeled as new durability
proof. A copy receipt lists every included file/hash and attempt directory. It is
recorded only after independent destination reads and exact root-set verification.
A failure leaves the original and partial destination for inspection; do not blindly
retry into the same path. No generic Workbench backup guarantee is expanded.

Every restored reopen verifies signatures and current trust again, and the replay
heads survive the copy. Existing observation/worker links are not automatically
rewritten: explicitly link the new receiving root. Local qualification drives
backup → second new restored root → original-path denial → re-link/reopen and a
signed older-sequence rejection, with exact source bytes unchanged and failed
attempt bytes retained. These are recorded Win32 effects with real SQLite/POSIX
cryptography. Actual native qualification must repeat the commands with the
original receiving store unavailable and independently assert the retained bytes,
indexes, failures, ACLs, VFS/barriers and current-trust rejection. It remains an
external host procedure, not a native PASS inferred from local tests.

The native receiver uses the same closed ordinary-apply, state-adoption and
adoption recovery-Plan decoders as POSIX. `evidence-history` therefore does not
need POSIX service SQLite access on Windows. Copied JSON never creates an
execution capability; state-only domains cannot advance the Graph deployment
baseline. The actual native host/DLL vectors, supplied current trust, independent
expected values, exact-package source pins and original-unavailable restore
procedure remain required platform gates. Local recorded-API fixtures are not
those native results.

Copy closure includes the exact nested name set of every attempt directory at
source and destination, plus whole root membership and listed byte readback.
Late extra members are preserved and cause failure; no complete-copy receipt is
returned for a partial or unexpected file set.
