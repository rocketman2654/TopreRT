param([string]$PythonPath)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

# Prefer the tested version, then accept another Python 3.10+ with Tkinter.
function Find-DemoPython {
    param([string]$Command, [string[]]$PrefixArgs = @())
    if (-not (Get-Command $Command -ErrorAction SilentlyContinue)) { return }
    try {
        $result = & $Command @PrefixArgs -c 'import sys, tkinter; assert sys.version_info >= (3, 10); print(sys.executable)' 2>$null
        if ($LASTEXITCODE -eq 0 -and $result) {
            return ([string]($result | Select-Object -Last 1)).Trim()
        }
    } catch {
        # Missing launcher versions and Windows Store aliases are not candidates.
    }
}

if ($PythonPath) {
    $demoPython = (Resolve-Path -LiteralPath $PythonPath).Path
} else {
    $demoPython = Find-DemoPython -Command 'py' -PrefixArgs @('-3.12')
    if (-not $demoPython) { $demoPython = Find-DemoPython -Command 'py' -PrefixArgs @('-3') }
    if (-not $demoPython) { $demoPython = Find-DemoPython -Command 'python' }
    if (-not $demoPython) { $demoPython = Find-DemoPython -Command 'python3' }
    if (-not $demoPython) {
        throw 'No Python 3.10+ with Tkinter found. Python 3.12 is recommended. Install Python with Tcl/Tk, or run Setup_Demo.bat -PythonPath "C:\path\to\python.exe".'
    }
}
Write-Host "Using Python: $demoPython"
& $demoPython -c 'import sys, tkinter; assert sys.version_info >= (3, 10)'
if ($LASTEXITCODE -ne 0) { throw 'Python/tkinter check failed.' }
& $demoPython -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Could not create the demo Python environment.' }
& '.\.venv\Scripts\python.exe' -m pip install -r requirements-demo.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check your connection and Python wheel compatibility.' }
& '.\.venv\Scripts\python.exe' -c 'import tkinter, hid'
if ($LASTEXITCODE -ne 0) { throw 'Runtime check failed.' }
Write-Host 'Demo ready. Open Start_TopreRT_GUI.bat'
