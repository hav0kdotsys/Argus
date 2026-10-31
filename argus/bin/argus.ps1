# argus.ps1 - the ARGUS command on Windows (PowerShell 5.1+ / pwsh). See argus/bin/argus for the why.
# Runs this checkout's Hermes core under $env:ARGUS_HOME (default %LOCALAPPDATA%\argus), with the ARGUS overlay.
$ErrorActionPreference = 'Stop'
$OutputEncoding = [System.Console]::OutputEncoding = [System.Console]::InputEncoding = [System.Text.Encoding]::UTF8

$argusDir = Split-Path -Parent $PSScriptRoot          # <repo>\argus
$repo = Split-Path -Parent $argusDir                  # the Hermes checkout

if (-not $env:ARGUS_HOME) { $env:ARGUS_HOME = Join-Path $env:LOCALAPPDATA 'argus' }
$env:HERMES_HOME = $env:ARGUS_HOME
$env:ARGUS_REPO = $repo

& (Join-Path $argusDir 'install.ps1') -Quiet

# First run (or after an update): let Hermes' own setup build the runtime; it is a no-op when current.
$py = $null
foreach ($c in @("$repo\.venv\Scripts\python.exe", "$repo\venv\Scripts\python.exe")) { if (Test-Path -LiteralPath $c) { $py = $c; break } }
if (-not $py) {
    & (Get-Process -Id $PID).Path -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$repo\setup-hermes.ps1" -RuntimeOnly | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'argus: Hermes runtime setup failed' }
    foreach ($c in @("$repo\.venv\Scripts\python.exe", "$repo\venv\Scripts\python.exe")) { if (Test-Path -LiteralPath $c) { $py = $c; break } }
}
if (-not $py) { throw 'argus: no Python runtime in this checkout after setup' }

# The environment `activate.ps1` would give a shell, applied to this process only.
$env:PYTHONPATH = $repo
$composed = ((& $py -m pm.environments) -join "`n") | ConvertFrom-Json
Remove-Item env:PYTHONPATH -ErrorAction SilentlyContinue
foreach ($p in $composed.PSObject.Properties) { Set-Item -Path "env:$($p.Name)" -Value ([string]$p.Value) }

Push-Location -LiteralPath $repo
try { & $py (Join-Path $repo 'hermes') @args; $code = $LASTEXITCODE }
finally { Pop-Location }
exit $code
