# Inactive Windows Workbench storage adapter

`intune_iac/windows_workbench.py` implements the next native persistence seam over the existing engine. It is available through the explicit `WindowsWorkbenchStore` component API, qualification harness and qualification-only read-only text launcher. **The ordinary Windows Workbench CLI remains UNSUPPORTED.** No host capability gate, collector, worker, UI route or credentials are enabled by this change.

The existing schema and read/query/history/health code are reused. `workbench_schema.py` holds the same schema SQL, signatures and validation; `observation_contract.py` holds the same field set, model URL and eight-object laboratory bound. The original imports remain reexported. The POSIX `WorkbenchStore` class now checks its host profile in its constructor, create, connection and restore entrypoints before filesystem dispatch. Modeled collection imports its POSIX service only inside that guarded route. This permits importing the inactive native component without pretending a POSIX store is portable.

## Implemented component routes

```python
from intune_iac.windows_workbench import WindowsWorkbenchStore

store = WindowsWorkbenchStore.create(new_private_child, tenant_id)
store.record_operation('review-receipt', {'phase': 'review', 'cloud_authority': False})
store.operations()
store.overview()
backup = store.backup(new_private_backup_path)
restored = WindowsWorkbenchStore.restore(
    backup['path'], new_restore_child, tenant_id, expected_sha256=backup['sha256'])
store.migrate(new_private_v1_backup_path)
store.storage_status()
WindowsWorkbenchStore.storage_status_at(existing_private_root)
```

The actual native filesystem API must be available; Linux public entrypoints fail before creation. Test-only recorded APIs use an internal seam and are never native evidence. The public class does not accept a filesystem implementation supplied by JSON, an environment variable or the terminal.

Creation writes a validated SQLite image and a separate empty rollback journal with explicit protected owner-only DACLs. Normal write connections keep the database and precreated journal file identities held without delete sharing. SQLite uses `PERSIST`, `synchronous=FULL`, foreign keys, memory temp storage and its native VFS transaction locking. Attach, extension loading and journal/durability overrides are rejected. There is no second invented lock around SQLite transactions. Native Windows sharing and actual PERSIST behavior still require the harness below.

Before opening a write connection, the adapter creates and flushes a unique immutable `store-intent-<operation>.json`. If that intent cannot be persisted, no SQLite mutation starts. It records a pre-session byte observation, **not an exact compare-and-swap baseline or exclusive attribution across concurrent connections**. A completed connection must close, flush database/journal and directory barriers, revalidate file identities and close all database/directory guards before publishing its outcome receipt. A failed barrier, receipt write, cancellation or late guard failure propagates uncertainty and retains the intent, DB, journal and partial files. The adapter never silently retries or removes them. `storage_status_at` can inspect unresolved intents without opening SQLite or attempting recovery.

Receipt scope is explicit: it records the database connection, guards and barriers completed before publication. A file cannot prove its own later handle cleanup or host power-loss durability. Reopening validates current private receipt bytes; these are cooperative local records, not an independently anchored audit trail. A hostile same-account or privileged process remains outside this boundary.

Backup uses SQLite's consistent backup API into bounded memory, validates the exact schema/tenant and SQLite integrity, then writes and exclusively publishes a new private binary file. An existing destination is preserved and the failed stage remains. Restore requires an independently retained exact SHA-256 and tenant match before creating a new directory. It restores local history only, never remote policies or infrastructure. Version-1 migration first produces a separately retained version-1 backup, then reuses the existing migration SQL inside an actual SQLite transaction. Failed migrations retain their backup and uncertainty.

## Explicit recovery preserves the interrupted source

Ordinary open rejects a hot rollback journal. Recovery is a separate action:

```python
recovered = WindowsWorkbenchStore.recover_into_new(
    interrupted_root, new_private_recovery_child, tenant_id,
    database_sha256=independently_recorded_database_hash,
    journal_sha256=independently_recorded_journal_hash)
```

Both original files are guarded, read and rechecked before copying. The approved hashes must match, the destination must be new, and original files remain unchanged. Native SQLite recovery runs only on this private copy. During that explicit operation SQLite may remove the copied journal; the adapter then reestablishes a protected empty PERSIST journal without overwriting an existing file. The source DB/journal hashes and recovery input/outcome records remain inspectable. A failed recovery or flush keeps the new copy for investigation, with no automatic retry or restoration over the original.

SQLite integrity and a requested tenant label do not authenticate a service or approve recovery. Verify the source receipts and target with the operator. Power-loss, hostile-process containment and organizational approval remain separate gates.

## Evidence and native procedure

R4 evidence is under `windows-store/`. Eighteen scoped adapter/import controls use **actual Linux SQLite with recorded Win32 effects**, including rollback, commit followed by barrier failure, lost outcome recording, writer contention, exact backup/restore, v1 migration and an owned process exiting before commit. One test includes three compound-failure variants for owned in-memory SQLite cleanup; these are not three additional top-level cases. The process interruption produces a real SQLite hot journal and qualifies recovery into a new copy locally; it is not Windows VFS, device, host crash or power-loss evidence. Existing history/relationships and the literal eight successful reports out of 100 targeted are checked through inherited store queries.

The shared-schema extraction also passed 82 selected Linux regression cases. Their direct engine calls use staged code; subprocess tests that locate the repository through their original test-file paths retain their existing repository scope. A separate six-command staged CLI journey explicitly runs the changed engine's real launcher through init, overview, backup, restore, reopened overview and wrong-tenant rejection with independent SQLite assertions. Its initial evaluator expected the wrong CLI error exit; the raw attempts remain and the corrected assertion reuses them without rerunning successful commands.

Independent review found and retained failing-before evidence for primary errors replaced by recovery-close failures, a premature outcome before guard cleanup, and a missing early public restore host guard. The after controls preserve primary validation/cancellation, leave late guard failures as unresolved intents, and reject unsupported restore before any filesystem dispatch. These scoped repairs do not establish native Windows or AppSec approval.

Further fault controls reproduced primary validation/cancellation being replaced by a secondary close failure in the owned in-memory backup, image validation and initialization helpers. Those three failed subcases remain in `helper-close-before-01.log`; a narrow shared cleanup context preserves the primary and records the secondary cleanup type. The passing 18-case replay is `helper-close-after-01.log`. This repair follows the separately retained reviewed patch02 and does not silently change that candidate's historical assessment.

Run the exact native component procedure only on an authorized disposable Windows x64 CPython 3.12, local fixed NTFS and pinned PowerShell 7 host:

```text
python scripts/qualify-windows-store.py --disposable-parent EXISTING_REVIEWED_PRIVATE_NTFS_PARENT --output NEW_EVIDENCE_DIRECTORY --source-pins REVIEWED_SOURCE_PINS_JSON --source-pins-sha256 REVIEWED_MANIFEST_SHA256 --powershell ABSOLUTE_PWSH7_EXE --powershell-sha256 REVIEWED_PWSH_SHA256
```

`--help` is the executable interface. The pin document has exactly `source_commit` and `files`; `files` maps every relative path in the script's `REQUIRED_FILES` tuple to its independently verified SHA-256. All pins must match before fixture creation. A caller-declared commit is not sufficient release provenance; first match these bytes against the recovered reviewed source/runtime package.

The parent must already have the reviewed private owner-only DACL. The harness creates uniquely named new stores, backups and recovery copies; it changes no existing parent asset or ACL. Its independent native SQLite and PowerShell/.NET observations check actual rows, tenant/schema, protected DACLs, journal persistence, pinned backup/restore, migration and recovery. An owned helper exits before commit to leave a real interrupted journal. Every stage and original remains retained. It does not run the unsupported ordinary CLI and call the rejection a functional Windows pass.

On the current Linux host the native procedure returns BLOCKED with zero native checks or commands. Native directory `FlushFileBuffers` support remains unestablished. If that required barrier fails on Windows, the harness reports UNSUPPORTED, preserves all artifacts and leaves dependent cases unqualified. File-only flushing, an ignored error or a move flag is not a replacement. A reviewed namespace durability protocol is a real blocker to enabling the profile.

## Remaining required work

The Windows endpoint/runner owner supplies the actual host and independent native evidence. The storage owner must resolve native VFS, sharing, DACL inheritance/sidecar and namespace durability findings. Capture/provenance readers now use the inactive native file seam described in [WINDOWS-READERS-R4.md](WINDOWS-READERS-R4.md); `collect` still rejects explicitly and the authenticated observation publisher has not admitted this class. Native packaged dictionary reads remain unported. Native scheduling/process containment and TUI/terminal restoration remain separate implementations/qualification. After those dependencies, wire the reviewed component to the actual Windows application route and qualify complete init, collection/import, inspection/history, change/recovery and closed-terminal journeys on exact packages. AppSec and accountable organizational pilot approval remain required.


## Native capture reader extension

The capture import and raw inspection seam is implemented in the inactive
Windows adapter; see [WINDOWS-READERS-R4.md](WINDOWS-READERS-R4.md) for exact
local scope, qualification-only text entrypoint and native procedure. The required native host qualification and ordinary host support gate remain open.
