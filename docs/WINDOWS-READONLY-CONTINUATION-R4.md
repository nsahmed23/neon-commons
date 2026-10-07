# Native read-only continuation

The inactive Windows component now has a staged package-reader seam for the
existing dictionary. Fixed `capability-map.json` and `vendor-documentation.json`
paths are derived from the installed module's package directory. Caller-selected
asset names and alternate package roots are not command-line options. The
native reader retains owner-only directory/file guards and bounds bytes at
512 KiB. The existing vendor-documentation digest remains unchanged; altered
vendor bytes fail. The private callback only changes file access, not the
dictionary's fact taxonomy, mapping semantics, identities or authorities.

The POSIX default continues to use its original reader. The qualification-only
native text launcher adds `dictionary [--query TEXT] [--object-id UUID]`,
`lineage UUID [--pointer JSON_POINTER]`, and
`reference-compare UUID REFERENCE_ARTIFACT_ID`. Comparison intentionally does
not accept a company-file argument on this route yet; no company desired state
or approval is inferred. This is an explicit local qualification interface,
not native platform support or permission to write a tenant.

Seven local controls exercise actual SQLite and the real text command handlers
with recorded Win32 effects: six fact categories, exact observed values,
unverified reference provenance, vendor digest failure, fixed asset admission,
foreign-owner failure, missing assets, readonly database invariance, unknown
lineage and typed comparison. The before run records the missing APIs/routes;
subcase errors are not extra independent tests. Twenty-two existing provenance
cases and six actual staged POSIX CLI taxonomy tests retain their own scopes.
None establishes native Windows behavior.

Run `scripts/qualify-windows-readers.py --help` and the exact procedure in
`docs/WINDOWS-READERS-R4.md` after native private package extraction is available.
The procedure's `REQUIRED_FILES` now includes both dictionary asset files.
Independently bind these bytes and the source files to the reviewed release.
The installed package's `corrections\contracts` directory must itself have the
reviewed current-token owner-only protected DACL; broader installation ACLs
fail closed. The native procedure adds real subprocess dictionary, lineage and
reference-comparison commands to its retained capture/import/history journey.
Its Linux receipt is BLOCKED with zero native checks or commands.

## Remaining implementation and qualification dependencies

| Dependency | Actual current entrypoint | Missing local behavior | Required next work and native evidence |
|---|---|---|---|
| Authenticated capture publication | `capture.capture`, `observation_reader._Reader.capture`, `CapturedObservation`, `publish_batch` | Capture creation is POSIX descriptor-based; the sealed observation capability rereads with the POSIX reader and publication requires exact `WorkbenchStore` type. | Implement a reviewed private native capture/staging capability and authenticated-reader binding, retain the live/laboratory split, then admit the native store through a sealed contract. Do not relax the exact-type check alone. Verify atomic publication and denied/partial/interrupted pages with actual native handles; real Graph identity is separate. |
| Independent observation jobs | `observation_jobs.run_due`, `scheduler_artifacts`; `workbench_scheduler` is the separate finite modeled scheduler | Durable job files, lock and runtime admission still use POSIX paths/primitives. No native independent scheduler adapter is connected. | Port job persistence and locks through native storage first; prepare an inactive Windows Task Scheduler specification bound to exact executable/account/config. Activation is separately authorized. Prove closed-terminal execution, restart, concurrent invocation and retained failures on Windows. |
| Ordinary client store selection | `workbench._store`, init/restore handlers | They deliberately select guarded POSIX `WorkbenchStore`. | After native semantics and platform gates pass, review one explicit bounded profile selection across the full text route. Keep unsupported routes explicit and regression-check all Linux behavior. This is code work still required, not merely missing credentials. |
| Native visual workspace | `workbench_tui.visual_supported`, `terminal_session`, `KeyReader`, `Workspace` | POSIX termios/select-based input and direct POSIX store/context persistence; native Windows console/mintty path is not implemented. | Add a narrowly declared terminal and context-storage adapter over the same engine. Exercise actual resize, Unicode width, non-color/reduced-motion input, cancellation and terminal restoration; preserve text fallback. |
| Native launcher and lifecycle qualification | Existing host-capability gate and external procedures | Ordinary Windows support remains disabled. Native Git Bash argument conversion, PowerShell exit precedence and chosen-terminal evidence remain absent. | Qualify exact Windows/Git Bash and PowerShell routes with spaces, leading hyphens, Unicode, quotes, CRLF, slash Graph paths and real filesystem paths. Do not globally disable MSYS conversion. |
| Recovery and durability | `WindowsWorkbenchStore`, `windows_storage`, native store procedure | Local contracts exist; native PERSIST-journal VFS, ACL/reparse/share rules, namespace flush, power loss and hostile-process behavior are unproven. | Windows endpoint/runner owner supplies disposable NTFS environment; storage owner resolves unavailable barriers without waiver. Retain every uncertain stage and perform recovery into a new independently pinned copy. |

The normal protected execution worker belongs to the approved service profile;
this read-only client work does not authorize a second local production writer.
Actual service/device evidence, CI/backend identity and AppSec/organizational
approval remain distinct from the implementation gaps above.
