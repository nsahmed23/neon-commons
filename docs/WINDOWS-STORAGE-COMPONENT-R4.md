# Inactive native Windows storage primitives

`intune_iac/windows_storage.py` implements the next bounded dependency over the existing inactive directory pin. It provides atomic private directory/file creation, exact-byte writes/readback, exclusive handle-relative publication and a cooperative named lock. **It is not wired into `WorkbenchStore` or any supported host profile.** Native Windows remains unsupported for the complete Workbench route.

The implementation uses only actual native system APIs when invoked on native Windows. Other platforms fail before filesystem dispatch; there is no `fcntl` shim, POSIX-permission fallback, replacement of failed durability barriers or new worker/network authority. The existing Linux engine and persistence remain unchanged.

The subsequent [inactive SQLite snapshot component](WINDOWS-SQLITE-COMPONENT-R4.md) reuses native metadata/read helpers for a separate read-only path. It does not bypass these namespace barriers, select a Workbench profile or make SQLite write/sidecar/recovery behavior qualified.

## Minimal integration seam

Actual store callsites are `WorkbenchStore._private/create/_connection/backup/restore/migrate` and `io.sync_directory/write_json/mkdir_durable`. A future store-filesystem dependency should supply validated/pinned roots and regular files, exclusive creation, namespace persistence and exclusive backup publication. Keep the existing SQLite schema, transactions, query limits and independent assertions intact.

SQLite's own Windows VFS supplies its transaction locks; do not wrap all SQLite operations in an invented `flock` replacement. The separate `exclusive_lock(root,name)` primitive serves cooperative named locks such as the existing synthetic model/scheduler locks or publication coordination. Native scheduler/process integration is a different requirement.

Public inactive interfaces:

```python
create_private_directory(existing_private_parent, new_child_name)
create_new_file(existing_private_root, new_file_name, exact_bytes)
publish_new(existing_private_root, stage_name, new_destination_name, expected_sha256)
with exclusive_lock(existing_private_root, lock_name):
    ...  # Explicit cooperative local critical section only.
```

Every root must already satisfy the current-token owner-only NTFS directory contract. Names are single validated components; relative traversal, device/UNC/alternate-stream aliases, control characters and unsupported names are rejected. Byte payloads remain binary, including CRLF, NUL and non-UTF-8 bytes. The 64 MiB bound is an implementation limit, not a fleet-performance claim.

Directories and files are created with an explicit protected owner-only security descriptor in `CreateDirectoryW`/`CreateFileW`. The ACL is attached at creation, without a permissive create-then-chmod interval. Files use `CREATE_NEW`, never truncate an existing destination, and must remain disk files with one link, the current owner and the pinned volume identity. Newly created directories carry supported child inheritance; file DACLs are explicit and protected.

Publication uses `SetFileInformationByHandle(FileRenameInfo)` with the still-open source handle, held root-directory handle, relative UTF-16 destination and `ReplaceIfExists=False`. The code verifies the approved byte digest before rename, retains file identity across rename and reads back exact bytes. It does not close/reopen the source by name or silently replace an existing destination.

Named locking uses `LockFileEx` with exclusive, fail-immediately semantics for byte zero of a dedicated private lock file. All participants must use this cooperative protocol. The file is retained, handles are non-inheritable, and locking is not a hostile same-account boundary. Existing lock-file content is not truncated. Unlock/close failures preserve a primary exception and remain visible.

## Durability and uncertain outcomes

Writes require successful `FlushFileBuffers` on the file and the held writable directory. New-directory creation requires barriers on the child and parent. Publication flushes before and after rename and requires a directory barrier. These are actual API calls, not boolean claims supplied by callers.

**Directory namespace flushing is not yet demonstrated on a native Windows host.** If the required call is unsupported or fails, the operation raises `windows_storage_namespace_flush_unavailable`, preserves every created/renamed artifact and adds a `storage_outcome` record identifying operation, phase and preserved names. There is no fallback to ignoring the error, flushing only file content, elevating to volume access or treating a move flag as equivalent proof. Native qualification reports this required dependency as UNSUPPORTED rather than passing the storage profile.

Even successful barriers return `native_power_loss_qualified: false`. API return values and cooperative process restart do not establish host power-loss durability. An actual native filesystem/recovery procedure and organizational security review are required before enabling a storage profile. Microsoft API references used for the bounded design are retained in R4 evidence under `windows-storage/api-references/`: `FlushFileBuffers`, `FILE_RENAME_INFO` and `MoveFileExW`. In particular, the documented copy/delete write-through behavior is not substituted for evidence about same-volume namespace durability.

A partial write, cancellation, lost rename acknowledgement or cleanup failure retains its primary failure. No code deletes a stage, overwrites a destination, requeues an operation or manufactures a successful publication. Inspect both stage and destination, exact bytes/file IDs and independent receipts before any explicit recovery. This module does not yet implement the full Workbench recovery journal or authorize replay.

## Executable native procedure

`scripts/qualify-windows-storage.py --help` exposes these exact arguments:

```text
python scripts/qualify-windows-storage.py --disposable-parent EXISTING_REVIEWED_PRIVATE_NTFS_PARENT --output NEW_EVIDENCE_DIRECTORY --powershell ABSOLUTE_PWSH7_EXE --powershell-sha256 REVIEWED_PWSH_SHA256 --storage-sha256 EXACT_WINDOWS_STORAGE_MODULE_SHA256 --directory-sha256 EXACT_WINDOWS_DIRECTORY_MODULE_SHA256 --source-commit FULL_REVIEWED_COMMIT
```

Run only on the authorized disposable native Windows CPython 3.12 64-bit environment, using the exact reviewed package and interpreter. The parent directory must satisfy the directory component's strict owner-only ACL contract. The harness writes a uniquely named new child, records the intended fixture before mutation, and never replaces or deletes existing parent contents. Evidence output must be new, outside the fixture parent and outside the package. Native evidence-directory ACLs remain an operator/host responsibility; POSIX `mode=0700` is not treated as proof of a Windows DACL.

The procedure independently checks exact payload bytes, existing-file preservation, exclusive rename and conflicting destination preservation. A separately pinned PowerShell 7/.NET oracle checks the actual created root/file/lock owner and protected DACLs plus the file hash. Separate native processes must demonstrate lock contention, release/reacquisition and release after abrupt termination of an owned holder process. That process termination is not a host crash, descendant-containment or power-loss claim. A deliberate hard link in the disposable child must prevent publication, and both link names remain intact as negative evidence.

All created files, conflicting stages and the intentional hard link remain for inspection. A failed barrier may leave only a newly created directory; that is retained evidence and does not justify skipping the required file, publication or locking gates. Timeout output and uncertain cleanup are preserved. The procedure returns BLOCKED with zero native commands when invoked on Linux.

Local contract tests use a recorded API fixture to assert exact operation ordering, known-bad identities/digests/links/names, no overwrite, partial writes, cancellation, uncertain rename, mandatory barriers, contention and primary-failure preservation. They do not establish native filesystem behavior. The final native SQLite namespace/sidecar adapter, concurrent native SQLite transactions, backup/migration/restore integration, real host-crash/power-loss tests, capture/provenance readers, terminal routes and accountable approval remain required before supporting the workplace profile.
