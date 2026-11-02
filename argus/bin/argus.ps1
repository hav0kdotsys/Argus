# argus.ps1 - the ARGUS command on Windows (PowerShell 5.1+ / pwsh). See argus/bin/argus for the why.
# Runs this checkout's core under $env:ARGUS_HOME (default %LOCALAPPDATA%\argus), with the ARGUS overlay, in the
# environment Hermes' package manager built for it - the same steps as activate.ps1, applied to this process only.
$ErrorActionPreference = 'Stop'
$OutputEncoding = [System.Console]::OutputEncoding = [System.Console]::InputEncoding = [System.Text.Encoding]::UTF8

$argusDir = Split-Path -Parent $PSScriptRoot          # <repo>\argus
$repo = Split-Path -Parent $argusDir                  # the checkout

if (-not $env:ARGUS_HOME) { $env:ARGUS_HOME = Join-Path $env:LOCALAPPDATA 'argus' }
$env:HERMES_HOME = $env:ARGUS_HOME
$env:ARGUS_REPO = $repo

& (Join-Path $argusDir 'install.ps1') -Quiet

function Find-BootPython {
    # The package manager's own interpreter, which setup-hermes.ps1 put in the home's tools folder.
    foreach ($root in @($env:HERMES_RUNTIME_DIR, (Join-Path $env:HERMES_HOME 'tools'))) {
        if (-not $root) { continue }
        foreach ($entry in @(Get-ChildItem -LiteralPath $root -Directory -Filter 'python-*' -ErrorAction SilentlyContinue)) {
            $candidate = Join-Path $entry.FullName 'python.exe'
            if (Test-Path -LiteralPath $candidate) { return $candidate }
        }
    }
    return $null
}

function Get-Composed([string]$py) {
    $saved = $env:PYTHONPATH
    try {
        $env:PYTHONPATH = $repo
        Remove-Item env:PYTHONHOME -ErrorAction SilentlyContinue
        $json = (& $py -m pm.environments) -join "`n"
        if ($LASTEXITCODE -ne 0 -or -not $json) { return $null }
        return $json | ConvertFrom-Json
    } finally {
        if ($null -eq $saved) { Remove-Item env:PYTHONPATH -ErrorAction SilentlyContinue } else { $env:PYTHONPATH = $saved }
    }
}

# First run (or after an update that changed a pin): build the runtime. It is quick when everything is current.
$boot = Find-BootPython
$composed = if ($boot) { Get-Composed $boot } else { $null }
if (-not $composed) {
    & (Get-Process -Id $PID).Path -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$repo\setup-hermes.ps1" -RuntimeOnly | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'argus: runtime setup failed' }
    $boot = Find-BootPython
    if (-not $boot) { throw 'argus: no bootstrap Python after setup' }
    $composed = Get-Composed $boot
    if (-not $composed) { throw 'argus: could not read the installed environment' }
}
foreach ($p in $composed.PSObject.Properties) { Set-Item -Path "env:$($p.Name)" -Value ([string]$p.Value) }

$py = if ($env:PYTHON) { $env:PYTHON } else { 'python' }
& $py (Join-Path $repo 'hermes') @args
exit $LASTEXITCODE
