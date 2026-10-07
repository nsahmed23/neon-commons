# Inactive native four-view inspection

The existing four-view engine now admits the exact native Workbench store for
policy and estate inspection. It reads the existing guarded SQLite schema and
raw capture reader; it does not duplicate normalization or weaken unsupported
mapping rules. Ordinary Windows host support remains disabled.

The qualification-only native text launcher now supports:

```text
python -B scripts/intune-windows-inspect.py --qualification-only --store C:\Pilot\Private\store --tenant TENANT_UUID views OBJECT_UUID
python -B scripts/intune-windows-inspect.py --qualification-only --store C:\Pilot\Private\store --tenant TENANT_UUID --limit 10 --offset 0 views --query QUERY
```

The shared terminal command engine also admits `views` and `views-page` for its
exact native store capability. No execution command is newly admitted. The
complete ordinary text interface remains unchanged. This is an inactive,
qualification-only integration until real Windows terminal/storage evidence
supports a declared profile.

The four views retain distinct scopes:

* Repository: recorded revision, source hashes, resolved inputs and scope in the
  stored artifact. Current native working-source rereading uses the same literal
  resolver through held private handles and exposes its read interval separately.
  It does not authenticate the recorded Git revision or prove future freshness.
* Observed: existing current/last-good snapshot, literal latest capture,
  collection/mapping coverage, timestamps and native byte revalidation result.
* Proposed: missing operation remains unknown. Linked protected-service or
  local modeled-operation journals are explicitly unsupported on this route;
  their POSIX paths are never opened. A supplied operation path is displayed as
  unsupported evidence access and cannot authorize any action.
* Coverage: original ownership completeness/freshness/conflicts, state-tracking
  evidence and mapping rules. Caller-imported ownership/provider refresh records
  retain their original assertion classes. A stored successful label does not
  establish a deployment baseline.

Each linked deployment candidate retains its immutable artifact ID and an
explicit unsupported/unverified reason. Missing receipts remain distinct from
stored metadata whose required execution evidence cannot be read. Repository
versus observation, prior collector snapshot and exact persisted state revision
comparisons keep the existing separate labels. No native execution journal,
worker identity, approved plan or deployment verification is synthesized.

`qualify-windows-readers.py` adds the real `views` subprocess to its existing
pinned native procedure, independent identity/raw-integrity assertions and
missing-deployment negative control. Its help and SOURCE_PINS contract remain
the executable procedure. Linux reports BLOCKED with zero native commands and
checks; recorded native API tests do not replace this gate.

The native repository accessor, intent import, bounded proposal and local source
edit/recovery are now integrated; see WINDOWS-REPOSITORY-R4.md,
WINDOWS-SOURCE-R4.md and WINDOWS-SOURCE-EDIT-R4.md. Protected execution
evidence must use its explicitly reviewed authenticated/signed delivery contract;
a stored local POSIX journal path never supplies that authority. Native OS
qualification remains separate from these implemented readers.
No cloud access, credential provisioning, scheduler activation, deployment or
organizational risk acceptance is introduced by this change.
