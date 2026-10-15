param([string]$PythonPath)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if ($PythonPath) {
    $demoPython = (Resolve-Path -LiteralPath $PythonPath).Path
} else {
    if (-not (Get-Command py -ErrorAction SilentlyContinue)) { throw 'Install Python 3.12 with the Python Launcher and tkinter.' }
    $demoPython = (& py -3.12 -c 'import sys; print(sys.executable)')
    if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.12 with tkinter, or pass -PythonPath to this script.' }
}
& $demoPython -c 'import sys, tkinter; assert sys.version_info >= (3, 10), "Python 3.10+ required"'
if ($LASTEXITCODE -ne 0) { throw 'Python/tkinter check failed.' }
& $demoPython -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Could not create the demo Python environment.' }
& '.\.venv\Scripts\python.exe' -m pip install -r requirements-demo.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check your connection and Python wheel compatibility.' }
& '.\.venv\Scripts\python.exe' -c 'import tkinter, hid; print("Demo ready. Open Start_TopreRT_GUI.bat")'
if ($LASTEXITCODE -ne 0) { throw 'Runtime check failed.' }
