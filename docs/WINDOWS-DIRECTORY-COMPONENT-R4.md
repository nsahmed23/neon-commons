# Inactive native Windows directory component

`intune_iac/windows_directory.py` is the first implemented native storage dependency. Its public `pin_private_directory(path)` context manager reads native identity/security metadata and retains verified directory handles. It does not enable the Workbench Windows profile, create a store, connect SQLite, provision credentials, change an ACL, launch execution or contact a service. Full Windows storage, native readers and the visual terminal remain unsupported implementation/qualification requirements.

The narrow component accepts 64-bit native Windows, a local fixed NTFS volume, an absolute drive-local path of at most 240 characters, and a directory owned by the current effective token SID. Its protected DACL must contain only that SID's allow ACEs with supported flags (none, or object/container inheritance). SYSTEM/admin/broad/inherited/unknown ACEs are outside this first contract; rejection is intentional, not a statement that other reviewed ACL policies cannot be safe. The first qualification runtime remains the project's pinned native CPython 3.12 route.

The implementation loads `kernel32.dll` and `advapi32.dll` from the system directory using the Windows DLL search restriction. It reads an effective thread token when present, falls back to the process token only for `ERROR_NO_TOKEN`, and compares the native owner SID. It selects a volume GUID, opens and retains every ancestor and the leaf with `OPEN_REPARSE_POINT` and without `FILE_SHARE_DELETE`, rejects reparse components/non-directories/non-NTFS volumes, and records volume identity plus a 128-bit file ID. Metadata and effective identity are rechecked before use and on context exit. All acquired handles close in reverse order. Cleanup failure preserves an existing primary exception and records uncertainty; successful context exit cannot hide cleanup failure. Closed pins cannot be reused.

The interface permits spaces, leading hyphens, Unicode and single quotes in admitted paths. It rejects relative/UNC/device paths, alternate streams, ambiguous separators, dot components, trailing dot/space aliases, reserved DOS device names including superscript aliases, unpaired surrogates and control characters. Errors use fixed descriptions and do not echo untrusted paths.

```python
from intune_iac.windows_directory import pin_private_directory

with pin_private_directory(r'C:\Intune Pilot\private directory') as pin:
    observation = pin.revalidate()
    # No store or SQLite adapter exists here yet. Retained handles expire
    # at context exit; this metadata grants no execution or tenant authority.
```

This is a cooperative-account filesystem boundary. An owner can change its own ACLs, and a hostile process with the same account is not isolated by owner-only DACLs. Merely validating directory metadata does not prove safe SQLite pathname/sidecar integration, file creation, backup publication or namespace durability. Those remain the next implementations in `docs/WINDOWS-STORAGE-ADAPTER-R4.md`. The active host capability report remains unchanged and rejects native Windows Workbench dispatch.

## Executable native qualification

`scripts/qualify-windows-directory.py --help` describes the actual interface. The procedure is read-only against operator-prepared disposable fixture directories; it creates only a new evidence directory. It uses a separately pinned native PowerShell 7/.NET oracle to establish actual current SID, owner, protected DACL, ACEs and reparse ancestors before applying the product helper. It does not accept caller-assigned fixture labels as evidence of those properties.

Prepare a reviewed JSON manifest containing these five absolute native paths:

```json
{
  "private": "C:\\Disposable Intune Test\\private",
  "broad_acl": "C:\\Disposable Intune Test\\broad",
  "reparse": "C:\\Disposable Intune Test\\junction",
  "reparse_ancestor": "C:\\Disposable Intune Test\\junction\\child",
  "foreign_owner": "C:\\Disposable Intune Test\\foreign"
}
```

The private fixture must grant the current SID full control with the supported protected owner-only DACL and have no reparse ancestors. The broad fixture must actually grant another principal access while retaining the current owner. The reparse fixtures must expose a real directory reparse leaf and a non-reparse child reached through a reparse ancestor. The foreign fixture must actually have a different owner while permitting read-control/attribute inspection to the qualification account. A host/security owner must prepare any fixture requiring rights unavailable to the operator; the procedure does not expand privileges, change ownership or synthesize that evidence.

Invoke the exact reviewed source/runtime with independently verified pins:

```text
python scripts/qualify-windows-directory.py --fixtures REVIEWED_FIXTURES_JSON --output NEW_EVIDENCE_DIRECTORY --powershell ABSOLUTE_PWSH7_EXE --powershell-sha256 REVIEWED_PWSH_SHA256 --module-sha256 EXACT_WINDOWS_DIRECTORY_MODULE_SHA256 --source-commit FULL_REVIEWED_COMMIT
```

The procedure retains raw oracle output, exact fixture bytes, hashes, declared source linkage and explicit pass/fail records. It requires:

- Private directory admission and independently matching token SID.
- Broad ACL, foreign owner, reparse leaf and reparse ancestor rejection with specific failure codes.
- An independent native DELETE-access open denied with sharing violation while the pin is active, then allowed after release. No directory is actually deleted or renamed.
- Exact process handle count restoration after every case.
- Same-user `ImpersonateSelf` followed by a verified actual thread token, helper revalidation, `RevertToSelf` and handle restoration. This changes only the qualification process's thread token and adds no privilege or credential.
- A deliberate invalidation of the helper's own retained leaf handle, preserving the resulting primary metadata failure and actual cleanup-failure note while releasing remaining handles. This is an owned-process fault, not a hostile-process containment claim.

No native Windows run occurred in the current Linux session. The Linux invocation records `BLOCKED`, zero native commands and no native checks. Local API fixtures verify ordering, strict denial, identity/security changes, partial acquisition and cleanup behavior; they do not prove Win32 ABI behavior or native ACL/locking guarantees. Source review is also distinct from independent organizational AppSec approval.

Once these native checks pass on the exact reviewed component, their scope is still only the directory prerequisite. Keep Workbench storage unsupported until native file/SQLite namespace and sidecar handling, contention, durability, backup/migration/restore, readers and application journeys are implemented and independently qualified. A component receipt cannot approve the declared pilot.
