# Her body's newest build into %LOCALAPPDATA%\Programs\Mira, as HavoK (no admin). The ARGUS service starts it again
# within 30 s. Run after pulling mira-body.
$ErrorActionPreference = 'Stop'
$root = 'D:\Network\Projects\Argus\mira-body'
$to = Join-Path $env:LOCALAPPDATA 'Programs\Mira'
& (Join-Path $root 'ci\build-windows.ps1') | Select-Object -Last 1
New-Item -ItemType Directory -Force $to | Out-Null
$running = @(Get-Process Mira -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$to*" })
$running | Stop-Process -Force
# Stop-Process returns before Windows lets go of the exe.
$running | Wait-Process -Timeout 15 -ErrorAction SilentlyContinue
Copy-Item (Join-Path $root 'out\windows\Mira.exe') $to -Force
"her body is updated at $to; the ARGUS service starts it within 30 s"
