# Inactive native capture readers and text inspection

This component imports retained local capture and source-reference bytes into
the existing SQLite Workbench engine. It does not authenticate a Graph tenant,
enable an ordinary Windows profile, or authorize a change. The host gate stays
UNSUPPORTED until native qualification and required security disposition.

`windows_capture.load_windows_capture` retains native owner-only directory and
read-only file handles through the shared capture validator. The directory
pins reject reparse paths and unsupported filesystems. Each file is a bounded,
single-link object belonging to the current token owner. Exact root/raw file
sets, identities and bytes are checked again before returning a batch. New
unexpected files fail validation and remain on disk. This is not isolation
against a hostile process using the same account or a privileged adversary.
The store adapter currently also inherits its 2,016-entry native namespace
listing bound; the standalone reader has the capture contract's 10,000-page
bound. Neither bound is a measured fleet-performance claim.

The POSIX reader remains the default. Capture mapping, types, raw order,
coverage, retry validation, unknown fields and tenant/object comparisons use
the existing validator. `WindowsWorkbenchStore.import_capture` and
`raw_capture_observation` now use the native file seam and the same persistent
query/history logic; unsupported and denied captures do not invent snapshots.
Source references preserve literal bytes and provenance labels. Their supplied
revision, URL or digest does not establish service authentication, ownership,
vendor authority or adoption support.

`scripts/intune-windows-inspect.py --qualification-only --store STORE --tenant
TENANT overview` is the explicit read-only text qualification route. Commands
are `overview`, `inspect OBJECT`, `history OBJECT`, `raw OBJECT`, `collections`,
`operations`, `artifacts`, and `storage-status`. `--limit` and `--offset` precede
the command. It prints escaped bounded JSON and never calls a write operation.
The supported ordinary `intune-iac.py` interface and host gate are unchanged.
Mapping/vendor dictionary files still use the POSIX package reader; that
native route is not claimed or exposed here. Git Bash argument conversion,
mintty, terminal restoration, live observation and scheduled native collection
remain separate qualification requirements.

Local acceptance uses actual SQLite and exact capture files with recorded
Win32 effects. Thirteen controls cover import/reopen/raw inspection, denied and
unsupported records, changed bytes/file sets, owner/link/volume and tenant
rejection, byte-exact reference provenance, size/pin denial, text-route state
invariance, actual Linux subprocess rejection, and timed-out native command retention. These are not thirteen native
Windows passes. The Linux capture/store/provenance regression set has 84
cases; repeated runs overlap and must not be added together. A prior run had
three missing staged data-file errors; that failed attempt is retained.

## Native procedure

Use native 64-bit CPython 3.12 on an approved disposable Windows NTFS host.
Prepare an owner-only protected capture fixture using the native storage
component, retain the separate expected capture digest and source-pin manifest,
and keep output outside the package and source fixture. The output parent must
already have a reviewed current-token owner-only protected DACL. Native output
creation uses the same private storage primitive; if it fails, the procedure
prints a blocker, retains any uncertain directory, and writes no raw output. Run:

```
python -B scripts/qualify-windows-readers.py --capture C:\Pilot\Private\capture --expected-capture-sha256 CAPTURE_SHA256 --tenant TENANT_UUID --disposable-parent C:\Pilot\Private --output C:\Evidence\new-reader-run --source-pins C:\Evidence\reader-pins.json --source-pins-sha256 MANIFEST_SHA256 --reference C:\Pilot\Private\reference.json --reference-sha256 REFERENCE_SHA256 --reference-revision REVIEWED_SOURCE_COMMIT --reference-url https://example.invalid/policy.json --reference-license GPL-3.0
```

The manifest is exactly `{"source_commit":"40-hex reviewed commit",
"files":{"each REQUIRED_FILES entry":"exact SHA-256"}}`; use the actual
`REQUIRED_FILES` tuple in the script, independently linked to the reviewed
release. Placeholders above must be replaced with verified values. The capture
must describe an entirely disposable fixture and have complete collection
coverage. Import acceptance is not service qualification. The harness creates
a new private store, imports through the public native APIs, compares literal source-reference bytes with the separately pinned input, asserts independent
SQLite row counts, invokes the actual text launcher in separate processes and
checks all original capture files remain byte-exact. It retains the store,
source pin copy, commands, output and receipt on failure.

The Linux execution records BLOCKED with zero native checks or commands.
Unavailable native namespace barriers fail with retained uncertain artifacts;
they must not be replaced with ordinary file flushes to get a pass. Native
owner ACLs, sharing/no-delete behavior, reparse attacks, SQLite VFS paths,
crash/power-loss behavior, concurrent hostile processes, Git Bash and chosen
terminal remain owned by the Windows qualification/security owners.

Independent compound-fault review retained two failing reader controls: a
cleanup cancellation replaced a primary validation failure, and directory
cleanup stopped attempting remaining handles. The staged lower guards now
preserve primary errors and finish every remaining close attempt before
propagating lone cleanup cancellation; failed close outcomes remain uncertain.
The identical named-lock release case has its own failing-before local control.
These repairs do not prove that a failed native CloseHandle released a handle.
