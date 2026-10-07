# Inactive native Windows SQLite snapshot component

`intune_iac/windows_sqlite.py` supplies a bounded, read-only prerequisite for the native inspection client. It is **not selected by WorkbenchStore or any supported host profile**. Windows Workbench storage remains unsupported. The Linux engine, schema, collector, worker, IO helpers and host capability gates are unchanged.

The implemented entrypoint is `read_snapshot(root, name='observations.sqlite3')`. It yields a bounded `query(sql, parameters=())` interface and a detached byte/identity receipt. It does not create a database, import captures, publish observations, recover a hot journal, migrate a schema, back up or restore a Workbench store. No extra dependency is introduced.

The existing native directory boundary pins all ancestors and the private current-token-owned NTFS root. Each database/sidecar guard opens with `GENERIC_READ | READ_CONTROL`, `FILE_SHARE_READ`, `OPEN_EXISTING` and `OPEN_REPARSE_POINT`. Ordinary pre-existing write handles must prevent admission; ordinary subsequent write/delete opens must fail while the guards remain held. Regular-file type, one link, private DACL, owner, volume and file identity are rechecked. This is a cooperative-account boundary, not containment of a hostile same-account or privileged process that can alter memory, ACLs or handles.

Only SQLite rollback-mode databases are admitted. An invalid header, unsupported page size or WAL-format header fails before SQLite dispatch. Any `-wal` or `-shm` file fails even when empty. A `-journal` file must be empty or have the first 28 bytes cleared, as an inactive PERSIST rollback journal does; every other journal requires explicit recovery. Neither a recovery-required journal nor an unexpected sidecar is removed or rewritten. The component retains the original bytes and returns a fixed failure code.

After those guards, SQLite receives the volume-GUID filename encoded as a file URI with `mode=ro&immutable=1`. `immutable` is used only inside the held native handle lifetime; it is not permission to ignore an active writer or sidecar. The actual Windows SQLite VFS handling of that exact URI remains an explicit native qualification gate. `query_only`, `trusted_schema=OFF`, extension disabling, SQL/attachment/expression limits and an allowlisted read authorizer provide additional controls. Queries return at most 1,000 rows/16 MiB and a bounded instruction count. Mutating statements, attach, extension loading and unapproved PRAGMA writes fail. This limit does not qualify a fleet scale envelope.

The connection closes before the file/directory guards. All original file IDs, lengths and hashes are checked again, and formerly absent sidecars must still be absent. A changed database, appearing sidecar, close failure or identity change cannot produce a successful context exit. A primary failure or cancellation survives an additional revalidation/cleanup failure. The context becomes unusable after close. No successful read is a namespace durability or power-loss claim; this component has no namespace mutation and does not bypass the storage component's missing native flush evidence.

## Local evidence and native procedure

Fourteen scoped local tests use real Linux SQLite against disposable literal database bytes and recorded Win32 API responses. They establish the query, denial, sidecar, identity, cleanup and bounds logic, not Windows sharing/DACL/VFS behavior. The initial evaluator had a Python argument-name collision in its `connect` wrapper; its nine errors remain in `windows-sqlite/contract-tests-01.log`. Correcting the evaluator parameter name produced `contract-tests-02.log` without a product change. No inherited full suite was rerun.

`scripts/qualify-windows-sqlite.py --help` exposes the native interface:

```text
python scripts/qualify-windows-sqlite.py --fixtures REVIEWED_FIXTURES_JSON --output NEW_EVIDENCE_DIRECTORY --powershell ABSOLUTE_PWSH7_EXE --powershell-sha256 REVIEWED_PWSH_SHA256 --module-sha256 EXACT_WINDOWS_SQLITE_MODULE_SHA256 --source-commit FULL_REVIEWED_COMMIT
```

The Windows endpoint/runner owner must supply a disposable native Windows, local fixed NTFS, 64-bit CPython 3.12 and pinned PowerShell 7 environment, plus four distinct private directories. Each holds the same reviewed synthetic schema-v2 Workbench `observations.sqlite3` bytes exported from the qualified Linux store. The root, database and any existing sidecar require the component's current-token owner-only protected DACL. Only the qualification host owner prepares ACLs and negative fixtures; the harness does not provision privileges or change them.

The manifest has these exact keys (replace illustrative paths and pins with independently verified values):

```json
{
  "clean": "C:\\Disposable Intune SQLite\\clean",
  "hot_journal": "C:\\Disposable Intune SQLite\\hot",
  "wal": "C:\\Disposable Intune SQLite\\wal",
  "hardlink": "C:\\Disposable Intune SQLite\\linked",
  "expected": {
    "database_sha256": "REVIEWED_SYNTHETIC_DATABASE_SHA256",
    "tenant_id": "11111111-1111-4111-8111-111111111111",
    "user_version": 2
  }
}
```

The clean root has no sidecar. The hot fixture additionally contains a nonzero rollback journal header; it is intentionally rejected without trying recovery. The WAL fixture additionally contains `observations.sqlite3-wal`, even an empty file. The linked fixture's database has one additional deliberate hard-link name within the disposable fixture. All artifacts stay in place. Use only synthetic data and preserve the reviewed exact database hash, fixture preparation and ACL evidence. Native PowerShell/.NET independently checks root/database ownership and DACLs before the component runs.

The native harness checks exact database hash, literal tenant value, schema version and SQLite integrity; known-bad mutation rejection; actual separate-process write/delete-access denial during the held snapshot and access after close; an already held write handle causing snapshot rejection; hot/WAL/hard-link denial; and every fixture's names and hashes unchanged. The access probes call `OPEN_EXISTING` and never write, truncate, rename or delete. Their own handle-only process is bounded and cleanup is recorded. Cooperative process cleanup is not host crash/power-loss evidence.

On Linux the harness returns `BLOCKED`, zero checks and zero native commands before reading the fixture manifest. This is the result retained in `windows-sqlite/linux-blocked-01/RESULT.json`. Native functional results remain absent. Exact artifact linkage is caller-declared until the final source/runtime package is independently verified.

## Remaining integration

The subsequent [inactive Workbench storage adapter](WINDOWS-WORKBENCH-ADAPTER-R4.md) implements schema/query reuse, private PERSIST journal handling, backup/restore, migration and explicit recovery into a new copy. It does not enable the ordinary Windows application route or establish native behavior. A private DACL inherited by SQLite-created sidecars is not automatically equivalent to the strict protected file DACL used here. Directory flush support and a qualified namespace/recovery protocol remain unresolved requirements. Keep capture/provenance readers, native scheduler/process containment and visual terminal support separate. AppSec and the accountable release owner must review these boundaries; neither component nor its future test pass approves production use.
