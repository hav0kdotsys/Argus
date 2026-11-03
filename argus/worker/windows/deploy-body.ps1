# Her body's newest build into %LOCALAPPDATA%\Programs\Mira, as HavoK (no admin). The ARGUS service starts it again
# within 30 s. Run after pulling mira-body.
$ErrorActionPreference = 'Stop'
$root = 'D:\Network\Projects\Argus\mira-body'
$to = Join-Path $env:LOCALAPPDATA 'Programs\Mira'
& (Join-Path $root 'ci\build-windows.ps1') | Select-Object -Last 1
New-Item -ItemType Directory -Force $to | Out-Null
$exe = Join-Path $to 'Mira.exe'
$old = "$exe.old"
# The service starts her again the moment she exits, so the running exe can't be overwritten. It can be renamed: the new
# one goes in beside it, then she's stopped and comes back as the new build.
Remove-Item $old -Force -ErrorAction SilentlyContinue
if (Test-Path $exe) { Move-Item $exe $old -Force }
Copy-Item (Join-Path $root 'out\windows\Mira.exe') $exe -Force
Get-Process Mira -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$to*" } | Stop-Process -Force
"her body is updated at $to; the ARGUS service starts it within 30 s"
