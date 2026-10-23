$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$setupSource = Get-Content -LiteralPath (Join-Path $projectRoot 'Setup_Demo.ps1') -Raw

function Test-Selection {
    param([string]$Name, [string[]]$Available, [string]$Success, [string[]]$Expected, [string]$Explicit = '')
    & {
        param($Name, $Available, $Success, $Expected, $Explicit, $Source)
        $script:calls = @()
        $script:available = $Available
        $script:success = $Success
        function Set-Location {}
        function Get-Command { param($Name, $ErrorAction) if ($Name -in $script:available) { $Name } }
        function Resolve-Path { param($LiteralPath) [pscustomobject]@{ Path = 'SelectedPython' } }
        function Invoke-Probe {
            param($Key)
            $script:calls += $Key
            if ($Key -eq $script:success) { $global:LASTEXITCODE = 0; 'SelectedPython' }
            else { $global:LASTEXITCODE = 1; Write-Error 'Mock unavailable interpreter' -ErrorAction Continue }
        }
        function py { Invoke-Probe "py $($args[0])" }
        function python { Invoke-Probe 'python' }
        function python3 { Invoke-Probe 'python3' }
        function SelectedPython {
            if ($args[0] -eq '-m') { throw 'TEST_STOP_BEFORE_VENV' }
            $global:LASTEXITCODE = 0
        }
        $failure = ''
        try { & ([scriptblock]::Create($Source)) -PythonPath $Explicit } catch { $failure = $_.Exception.Message }
        if (($script:calls -join '|') -cne ($Expected -join '|')) { throw "$Name wrong probes: $script:calls" }
        if ($Success -or $Explicit) {
            if ($failure -ne 'TEST_STOP_BEFORE_VENV') { throw "$Name unexpected result: $failure" }
        } elseif ($failure -notlike 'No Python 3.10+*') { throw "$Name wrong failure: $failure" }
        Write-Output "PASS: $Name"
    } $Name $Available $Success $Expected $Explicit $setupSource
}

Test-Selection 'Prefer 3.12' @('py','python') 'py -3.12' @('py -3.12')
Test-Selection 'Only 3.14 via launcher' @('py') 'py -3' @('py -3.12','py -3')
Test-Selection 'No launcher, PATH Python' @('python') 'python' @('python')
Test-Selection 'Failed launcher, PATH Python' @('py','python') 'python' @('py -3.12','py -3','python')
Test-Selection 'python3 fallback' @('python','python3') 'python3' @('python','python3')
Test-Selection 'No Python' @() '' @()
Test-Selection 'Invalid Python or missing Tkinter' @('py','python') '' @('py -3.12','py -3','python')
Test-Selection 'Explicit path bypasses discovery' @('py') '' @() 'C:\Python with spaces\python.exe'

# Run the real BAT wrapper against a harmless fixture with Windows PowerShell.
$fixtureDir = Join-Path $projectRoot ('.setup-test-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $fixtureDir -Force | Out-Null
try {
    Copy-Item -LiteralPath (Join-Path $projectRoot 'Setup_Demo.bat') -Destination $fixtureDir
    'param([string]$PythonPath); if ($PythonPath -cne "C:\Python with spaces\python.exe") { exit 9 }; exit 7' |
        Set-Content -LiteralPath (Join-Path $fixtureDir 'Setup_Demo.ps1') -Encoding ASCII
    Push-Location -LiteralPath $fixtureDir
    try {
        & cmd.exe /d /c 'Setup_Demo.bat -PythonPath "C:\Python with spaces\python.exe" <nul'
    } finally { Pop-Location }
    if ($LASTEXITCODE -ne 7) { throw "BAT forwarding/exit code failed: $LASTEXITCODE" }
    Write-Output 'PASS: BAT forwards quoted path and preserves exit code'
} finally {
    Remove-Item -LiteralPath (Join-Path $fixtureDir 'Setup_Demo.bat'), (Join-Path $fixtureDir 'Setup_Demo.ps1')
    Remove-Item -LiteralPath $fixtureDir
}
