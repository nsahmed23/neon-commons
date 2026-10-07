# Inactive native local source edit and recovery

This is a qualification-only extension of the existing source resolver, private Windows store, source proposal, full text command engine and native workspace. It does not enable the ordinary Windows profile. A local file-edit acknowledgment is not protected-plan approval, tenant write authorization, Git review or organizational approval. Every completed edit still requires normal change review, a fresh resolved saved plan, exact protected approval and independent service/device evidence.

## Actual application routes

The shared text engine and explicit native workspace expose these commands. The default POSIX engine denies the native edit routes without the exact native store capability.

```text
source-review PROPOSAL_DIR DIGEST
source-edit PROPOSAL_DIR DIGEST EXPIRY ACK-LOCAL-FILE-EDIT
source-edit-status SOURCE_ROOT OPERATION_ID
source-edit-recover SOURCE_ROOT OPERATION_ID complete|rollback|abort EXPIRY ACK-LOCAL-FILE-EDIT
```

`source-review` validates the four immutable proposal files, exact digest, actual owner/tenant and source binding. It displays metadata and inheritance impact; review the private `source.before.yaml`, `source.after.yaml` and complete `change.patch` as well. An expiry must be in the next hour. The exact proposal/root/file/digest/actor/expiry bind the local acknowledgment. Reusing that exact acknowledgment is rejected.

The same routes are available through `scripts/intune-windows-source.py --qualification-only --store STORE --tenant TENANT`. Run `--help`, then each subcommand's `--help` for the exact named options. The edit and recovery options require both `--expires-at` and `--acknowledge-local-file-edit`. The CLI prints retained operation identity and uncertainty on application errors; a process/host interruption may require the retained root journal to locate the operation.

## Files, guarantees and limits

The cooperative `.intune-source-edit.lock` is created when importing intent or editing. It is metadata, not a change to authoritative YAML. Native source intent publication happens after all source and lock guards close successfully. Unresolved canonical intent blocks subsequent source reads/imports; four-view current-source output carries the exact `source-edit-status` action. Existing historical intent remains explicitly historical.

An edit binds current root identity, exact target file identity/bytes, recorded resolver input hashes and the immutable proposal. The original file moves to a unique backup; a separately verified candidate then moves to the original name, with no overwrite. The two renames are **not atomic**. Both names, identities, hashes and original owner-only protected DACL/attributes are retained in immutable journals. Supported file attributes are only hidden/system/archive or NORMAL alone. Read-only, compressed, encrypted, offline, unknown flags and unsupported DACL forms fail closed. No original ACL is relaxed; WRITE_DAC is requested solely for the new privately owned candidate to preserve the original admitted ACL.

Canonical intent and candidate-ready records are staged, flushed, read back and published with no-overwrite rename. Partial staging records remain on disk. Partial final closure attempts remain byte-exact and appear as invalid historical records; recovery can append a new bounded closure generation without replacing them. Conflicting closure states are rejected. At most 256 operations, 32 closure attempts per operation and a 4 MiB parsed root journal budget are admitted. Exceeding bounds requires an accountable archival procedure; no automatic deletion is implemented.

Recovery first inspects the actual original/candidate/backup files. Immediately before mutation it reacquires and holds the exact original root, parent and every present transition file, rechecks bytes, identity and security metadata, and keeps those handles through the selected renames. Same-byte file substitution is rejected before mutation. `complete` additionally holds and verifies every originally recorded dependency except the already-bound target. `rollback` restores only the exact retained original target; unrelated changed inputs remain changed. Both operations label the limit: they are not a fresh Atmos resolution, do not prove the impact of new/unrecorded source files, do not restore surrounding inputs, and require a fresh resolved plan. The cooperative lock does not establish hostile-process containment.

`abort` is permitted only when the original is still before-state; unqualified candidates can only be explicitly aborted. A missing immutable proposal, mismatched root/file, foreign destination, changed dependency on completion, failed namespace flush, failed close, expired acknowledgment or unknown state remains denied/uncertain. No automatic mutation retry is performed. Keep all proposals, journals, staged files, backups and failed attempts. A new successful receipt does not erase a lost acknowledgment, invalid receipt or historical provenance finding.

Closure records describe independently re-read file facts after mutation guards close. They explicitly do not self-authenticate acknowledgement of their own publication. The status route rechecks current file identity/bytes against closure state. A stored local receipt is not authenticated external evidence. Namespace durability, native ACL equivalence, actual SQLite, shell behavior and host power-loss recovery require their own native gates.

## Native qualification procedure

Owner: Windows endpoint/runner owner. Required environment: approved disposable 64-bit Windows host, CPython 3.12, private local NTFS roots accepted by the existing native guards, exact reviewed source/artifact pins and three distinct disposable source checkouts/stores/proposals created through the existing capture/import/proposal route. No tenant mutation is needed for this local procedure. Native Git Bash, PowerShell, mintty/terminal and real service qualification remain separate gates.

Prepare a private independently reviewed cases document with exactly `cases`, containing three entries. Each entry has `id`, `store`, `tenant`, `repo`, `proposal`, `digest`, relative `source_path`, independent `before_sha256`, independent `after_sha256`, `fail_after_rename`, and `recovery`. Required case pairs are `(null, null)`, `(1, "rollback")`, `(2, "complete")`. Do not derive the expected before/after hashes using the product normalizer. Each repo is a distinct disposable checkout; retain exact proposals and independently inspect all changes first.

Prepare source pins as `{ "source_commit": "40 hex reviewed commit", "files": { "relative/path": "sha256" } }` using the qualifier's exact `FILES` tuple. That tuple covers all package Python runtime modules and the source CLI/qualifier. Independently verify each pinned byte against the reviewed commit and artifact; a caller-supplied commit label is not Git proof.

```text
python -B scripts/qualify-windows-source-edit.py --cases C:\private\cases.json --cases-sha256 EXACT_SHA256 --source-pins C:\private\source-pins.json --source-pins-sha256 EXACT_SHA256 --output C:\private\new-evidence --acknowledge-disposable-source-edits
```

The qualifier runs actual application CLI entrypoints. The interrupted cases subclass the actual native API only to fail acknowledgment after a real native rename; the retained command record labels this injection. Recovery/status run as separate real processes. Independent raw-byte hashes and direct native security descriptor/attributes comparisons verify final state. A successful result qualifies only these native operations, not power loss, adversarial containment or production use. A failure leaves every disposable source/proposal/evidence file for inspection. Never automatically clean up an unknown outcome. On Linux the qualifier returns BLOCKED with zero native checks/commands.

## Local evidence and replay

```text
python -B -m unittest plugin_tests.test_windows_source_edit_r4 -v
```

Local controls drive actual source bytes, SQLite, the shared terminal and CLI with recorded Win32 boundaries. They are not native qualification. Historical failing writer candidates and logs are under the R4 `windows-source-edit` evidence directory. They include overlong recovery filenames, partial intent/ready/final receipt publication, publication before lock cleanup, and hash-only recovery rename substitution. Their repaired source identities, exact replay scope and independent results are recorded separately. Counts overlap previous suites and must not be summed as independent coverage.
