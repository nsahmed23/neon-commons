# Text/visual client launcher; normal apply belongs to the protected worker.
# Run with a pinned PowerShell 7 host and -NoProfile. No ambient Python fallback.
[CmdletBinding()]
param(
    [string] $PythonExecutable,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $CliArguments = @()
)

function Resolve-WorkbenchExitCode {
    param([int] $PrimaryExit, [bool] $CleanupFailed)
    if ($PrimaryExit -ne 0) { return $PrimaryExit }
    if ($CleanupFailed) { return 126 }
    return 0
}

function Invoke-WorkbenchProcess {
    param($Process)
    $primaryExit = 125
    $cleanupFailed = $false
    try {
        if (-not $Process.Start()) { throw 'native_start_failed' }
        $Process.WaitForExit()
        $primaryExit = [int] $Process.ExitCode
    }
    catch {
        # Fixed messages do not echo attacker-controlled paths or child output.
        [Console]::Error.WriteLine('workbench_launcher_native_failure')
    }
    finally {
        try { $Process.Dispose() }
        catch {
            $cleanupFailed = $true
            [Console]::Error.WriteLine('workbench_launcher_cleanup_failure')
        }
    }
    return Resolve-WorkbenchExitCode -PrimaryExit $primaryExit -CleanupFailed $cleanupFailed
}

# Permit direct function testing without starting an application or changing
# host state. This is normal PowerShell dot-source semantics, not an app flag.
if ($MyInvocation.InvocationName -eq '.') { return }

if ($PSVersionTable.PSVersion.Major -lt 7) {
    [Console]::Error.WriteLine('workbench_launcher_powershell_argument_list_required')
    exit 64
}
if ([string]::IsNullOrWhiteSpace($PythonExecutable) -or
    -not [IO.Path]::IsPathFullyQualified($PythonExecutable)) {
    [Console]::Error.WriteLine('workbench_launcher_absolute_python_required')
    exit 64
}
if (-not [IO.File]::Exists($PythonExecutable)) {
    [Console]::Error.WriteLine('workbench_launcher_python_unavailable')
    exit 66
}
$launcher = [IO.Path]::Combine($PSScriptRoot, 'intune-iac.py')
if (-not [IO.File]::Exists($launcher)) {
    [Console]::Error.WriteLine('workbench_launcher_application_unavailable')
    exit 66
}

$start = [Diagnostics.ProcessStartInfo]::new()
if ($null -eq $start.ArgumentList) {
    [Console]::Error.WriteLine('workbench_launcher_powershell_argument_list_required')
    exit 64
}
$start.FileName = $PythonExecutable
$start.UseShellExecute = $false
$start.CreateNoWindow = $false
$start.ArgumentList.Add('-I')
$start.ArgumentList.Add('-B')
$start.ArgumentList.Add($launcher)
foreach ($argument in $CliArguments) { $start.ArgumentList.Add($argument) }
$process = [Diagnostics.Process]::new()
$process.StartInfo = $start
$nativeExit = Invoke-WorkbenchProcess -Process $process
exit $nativeExit
