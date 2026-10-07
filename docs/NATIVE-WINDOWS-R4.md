# Native Windows continuation procedure

The launchers and qualification procedures are implemented. The private native store, observation binding/jobs, console/context, current-source/intent/proposal and bounded source-edit recovery now exist as inactive components over the existing engine. **The ordinary Windows profile remains UNSUPPORTED, and real native qualification is BLOCKED on the current Linux host.** Missing host evidence must not be reported as missing implementation, and local recorded Win32 controls must not be reported as native passes. See [the current adapter map](WINDOWS-WORKBENCH-ADAPTER-R4.md).

The native SID/DACL, reparse, VFS, locking and namespace durability behavior still requires real evidence. Git Bash/mintty, chosen-terminal and PowerShell execution are not qualified by Linux tests. A Linux invocation of the native qualifier writes a BLOCKED receipt and executes zero native probes. No installation, registry change, system configuration, cloud access or production operation is performed by these qualification preparations.

The initial native shell target is CPython **3.12**, Git for Windows Bash and
**PowerShell 7** using .NET `ProcessStartInfo.ArgumentList`. Exact binary hashes
must come from reviewed installed artifacts. Windows PowerShell 5.1 is rejected
because this implementation does not provide equivalent native argument
transport there. UNC paths are outside this first qualifier's admitted scope.
These exclusions do not remove the user's required native Windows/Git Bash and
native PowerShell 7 acceptance gates.

## Launch the existing application

`intune-workbench.sh` and `intune-workbench.ps1` always execute the sibling
`intune-iac.py` with an **explicit absolute Python path**, `-I` and `-B`. They
do not search PATH for Python, concatenate a shell command, evaluate supplied
arguments or choose a different application. They launch the existing complete
text interface, and any visual command the same candidate exposes. They are
client launchers, not protected execution workers or credential boundaries.

From an approved Git Bash session with trusted startup configuration:

```bash
BASH_ENV= ENV= /usr/bin/bash --noprofile --norc \
  '/c/Intune Pilot/package/scripts/intune-workbench.sh' \
  --python '/c/Intune Runtime/python.exe' -- workbench --help
```

The wrapper's child invocation clears `MSYS_NO_PATHCONV` and sets exactly
`MSYS2_ARG_CONV_EXCL='/beta/;/v1.0/'`. These are Graph API path prefixes, not
`*` or a global switch. Ordinary `/c/...` filesystem arguments still undergo
native MSYS conversion. The original caller environment is unchanged. The
current application's Graph reader builds its service routes internally;
preserving slash-prefixed argument data does not add arbitrary Graph endpoints.
An input containing a genuine local file under `/beta/` or `/v1.0/` is ambiguous
with this admitted API prefix and is outside this wrapper profile; use an
explicit drive-local path.

From PowerShell 7, use an argument array to retain literal values:

```powershell
$arguments = @('workbench', 'overview', '--root', 'C:\Intune Pilot\private store')
& 'C:\Intune Pilot\package\scripts\intune-workbench.ps1' `
  -PythonExecutable 'C:\Intune Runtime\python.exe' -CliArguments $arguments
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
```

Start the PowerShell host itself with `-NoProfile`. A wrapper cannot undo
already executed parent shell profiles, `BASH_ENV`, exported shell functions,
DLL search behavior or a compromised executable. The qualification runner
clears Bash/Python startup injection variables before invoking its explicit
tools. Organizational host policy and actual native startup/containment tests
remain required. The launcher is not a hostile-parent sandbox.

PowerShell records the native child's exit code. A failed start/wait returns
125; cleanup failure after a successful native result returns 126. When a
native failure and cleanup failure both occur, the original native exit wins.
Only fixed error codes are emitted by launcher errors, without echoing
untrusted executable paths. Console streams remain attached for ordinary
interaction. Native interruption and descendant cleanup must still be tested
on Windows; `Dispose()` is not claimed to kill a process or prove cleanup.

## Execute the pinned native shell procedure

First prepare the exact final package in a **new** directory with its verified
source/release linkage. Do not use a mutable source checkout for package
acceptance. The qualifier reads the supplied ZIP without extracting it and
checks its SHA-256, every member's bytes, collisions, supported types and exact
extracted file-set closure. Unexpected files cause rejection and remain intact.
Outputs must be new and outside the package. Supplied source commit is a
declared label until matched by the independent release receipt; the procedure
does not authenticate a commit merely because it was passed on the command line.

The following command is a template with **required reviewed inputs**, not a
record of a native run. Arguments below match the actual `--help` interface:

```powershell
& 'C:\Intune Runtime\python.exe' -I -B `
  'C:\Intune Pilot\source\scripts\qualify-windows-workbench.py' `
  --plugin 'C:\Intune Pilot\exact-runtime' `
  --output 'C:\Intune Pilot Evidence\NEW-native-run' `
  --python 'C:\Intune Runtime\python.exe' --python-sha256 REVIEWED_PYTHON_SHA256 `
  --bash 'C:\Program Files\Git\bin\bash.exe' --bash-sha256 REVIEWED_BASH_SHA256 `
  --powershell 'C:\Program Files\PowerShell\7\pwsh.exe' --powershell-sha256 REVIEWED_PWSH_SHA256 `
  --package-zip 'C:\Intune Pilot\Intune_IaC_Plugin_RUNTIME.zip' `
  --package-sha256 REVIEWED_RUNTIME_SHA256 --source-commit REVIEWED_FULL_COMMIT
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
```

The reviewed qualifier script also needs its source package/hash bound by the
release receipt. Tool pin mismatches, missing tools, non-native executable
inputs and reused evidence outputs reject before probes. The procedure installs
nothing and discovers no ambient credentials. It preserves all raw stdout,
stderr, exit codes, argv and byte hashes in a private evidence directory; these
are synthetic/local records, not authorization to publish tenant captures.

The native automated cases drive the exact launcher bytes against a disposable
argv observer, then the actual application. The observer has CRLF source and
checks graph paths versus real filesystem paths, spaces, leading hyphens,
Unicode, single/double quotes, literal shell substitutions/backticks, inert
terminal control bytes, and exact CRLF/NUL/non-UTF-8 payload bytes. It verifies
isolated Python and native exit 37. A harmless modeled PowerShell process
injects cleanup failure to exercise the actual exit-resolution function; this
does not claim an OS cleanup failure was observed. The application cases run
help, doctor and invalid-command rejection. The exact candidate's doctor report
must declare the storage implementation prerequisites before any store probe.
Missing or inconsistent reports fail this gate. When the route is UNSUPPORTED,
store initialization, overview and the text terminal must return the explicit
`host_profile_unsupported` contract with exit 2 and create no store. These are
negative controls; the required native storage gate remains UNSUPPORTED and
functional qualification BLOCKED. The overall qualifier exits 3 / UNSUPPORTED
even if its automated negative and shell assertions pass.

After the reviewed native adapter exists, the same procedure requires successful
private store initialization, overview and piped text terminal. Independent SQL
then asserts the known tenant and zero observations/operations; product display
output is not its own oracle. The implementation contract is documented in
`docs/HOST-CAPABILITIES-R4.md`; no permission or lock fallback is enabled.

The piped text terminal is explicitly **not** a mintty, ConPTY or visual
interaction test. Once the required store implementation exists, `receipt.json`
can PASS its named native shell/smoke scope
while `native_windows_qualified`, `platform_qualified` and
`production_approved` remain false. A timeout preserves a descendant-cleanup
uncertainty blocker; inspect task-owned processes before cleanup or retry.
The 45-second child timeout and output accounting are qualification bounds,
not worker isolation or whole-process-tree guarantees.

## Complete the remaining Windows and platform evidence

Each run emits `procedure-manifest.json` with exact scope and required next
procedures. Do not delete or normalize a failed attempt before repeating in a
new directory.

| Required route | Owner and preparation | Evidence still required |
| --- | --- | --- |
| Git Bash/mintty and chosen terminal | Windows host owner supplies actual terminal/version and approved disposable account; use verified wrapper, interpreter, package and private store | Actual key/input stream and captures for full investigation/change/recovery, narrow layout, resize, Unicode width, non-color/reduced motion, back/edit/cancel/resume, context preservation and terminal restoration; independent state/operation assertions. |
| Windows filesystem/process boundary | Windows/security owner supplies suitable ACL/reparse/supervisor fixtures and authorization for bounded faults | No-outside-write probes, startup/argument attacks, acquisition/write/receipt cancellation, descendants and recovery; preserve cleanup uncertainty, not only process exit. |
| Native PowerShell 7 | Windows host owner provides reviewed pin and no-profile route | Actual argument transport and native exit results, primary-versus-cleanup behavior, interactive restore/cancel tests. Linux/static assertions do not substitute. |
| Authentic Graph/provider/Azure/CI | Tenant, identity, backend and execution-service owners approve named scope and chosen protected platform | Receiving-service identity, exact-plan protected lifecycle, native backend leases/state, independent policy/assignment readback and second-plan convergence. No normal production apply is performed by the terminal wrapper. |
| Devices and production decision | Device/pilot, AppSec/risk and release owners provide cohort and review decisions | Enrolled endpoint effects and denominators, stop/recovery observations, operations approval and accountable intended-use authorization. |

For local Linux engineering only, replay the changed contract scope:

```bash
/workspace/intune-runtime/bin/python -B -m unittest plugin_tests.test_native_host_contract_r4
/workspace/intune-runtime/bin/python -B scripts/qualify-windows-workbench.py \
  --plugin /absolute/PROJECT --output /absolute/NEW-linux-blocker-receipt
```

The second command is expected to exit **3 / BLOCKED** on Linux. The local
tests are wrapper/parser/negative-control evidence, never native Windows
support or organizational production approval. Original R2/R3 suites and
failed native attempts remain preserved with their existing scopes.
