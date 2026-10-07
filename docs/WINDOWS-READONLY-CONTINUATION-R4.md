# Native read-only continuation

The inactive Windows component now has an integrated inactive package-reader seam for the
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
| Authenticated capture publication | `windows_observation.bind_native_target`, sealed reader capture/publication | Native storage and exact live/laboratory target binding are implemented. | Run the [native observation procedure](WINDOWS-OBSERVATION-R4.md); actual Graph identity and device evidence remain separate. |
| Independent observation jobs | `scripts/intune-windows-observer.py` create/run/status/prepare-task | Native job persistence, concurrency, credential reference and disabled Task Scheduler preparation are implemented. | Native scheduler/account/closed-terminal evidence and authorized activation remain; [job guide](WINDOWS-OBSERVER-JOB-R4.md). |
| Ordinary client selection | `workbench._store`, original init/restore handlers | Default routes deliberately retain guarded POSIX store selection. Exact inactive native composition exists. | Only enable a bounded ordinary profile after native gates and reviewed dispatch; do not weaken current denial. |
| Native visual workspace | `windows_workspace_binding`, `windows_terminal`, `windows_workspace_context`, existing Workspace | Native console and context composition are implemented over the same engine. | Actual native resize/input/restoration and supported terminal/layout behavior remain; [console guide](NATIVE-WINDOWS-CONSOLE-R4.md). |
| Four views and current source | Native `views`/`views-page`, `windows_repository` | Current guarded same-resolver readback, intent import and proposal are implemented. | Qualify native filesystem/shell behavior; recorded Git revision remains unauthenticated. |
| Bounded local source edit | Shared source-review/edit/status/recover; `scripts/intune-windows-source.py` | Exact local acknowledgment, two-rename journal, held recovery identities and explicit complete/rollback/abort are implemented. | Native metadata/durability gates and fresh reviewed protected plan remain; [source edit guide](WINDOWS-SOURCE-EDIT-R4.md). |
| Native shell/lifecycle | Existing host capability and external procedures | Ordinary Windows support remains disabled. | Qualify exact Git Bash/PowerShell, mintty/chosen terminal, spaces/Unicode/quotes/CRLF and scoped MSYS conversion. |
| Recovery/durability | `WindowsWorkbenchStore`, `windows_storage`, native store procedure | Local write/backup/migration/restore and failure contracts exist. | Actual Windows VFS, ACL/reparse/share rules, namespace flush, power loss and hostile-process evidence remain required. |

The normal protected execution worker belongs to the approved service profile;
this read-only client work does not authorize a second local production writer.
Actual service/device evidence, CI/backend identity and AppSec/organizational
approval remain distinct from these integrated local contracts and native qualification gaps.
