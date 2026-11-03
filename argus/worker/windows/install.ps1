# ARGUS's worker on winhvk as a Windows service. Run from an admin PowerShell, in this folder:
#   powershell -ExecutionPolicy Bypass -File .\install.ps1
# What it does:
#   - builds ArgusService.exe and installs it as %ProgramFiles%\ARGUS\ArgusService.exe, service "ARGUS" (LocalSystem,
#     automatic, restarts on failure)
#   - writes %ProgramData%\ARGUS\argus.yaml from argus.winhvk.yaml if there isn't one, writable by admins only
#   - puts her body (mira-body's out\windows\Mira.exe) in %LOCALAPPDATA%\Programs\Mira, where it updates without admin
#   - stands the old body and companion down: the MIRA Companion startup shortcut moves to %ProgramData%\ARGUS\rollback,
#     and the service turns off the MIRA-Pet logon task itself while her body is on
# Rollback: set body.enabled: false in argus.yaml (MiraPet comes back within 30 s), or uninstall.ps1 for all of it.
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) { throw 'Run this from an admin PowerShell.' }
$user = 'C:\Users\HavoK'
$bodyFrom = 'D:\Network\Projects\Argus\mira-body\out\windows\Mira.exe'
$bodyTo = Join-Path $user 'AppData\Local\Programs\Mira'
$program = Join-Path $env:ProgramFiles 'ARGUS'
$data = Join-Path $env:ProgramData 'ARGUS'

& (Join-Path $here 'build.ps1')
New-Item -ItemType Directory -Force $program, $data, (Join-Path $data 'rollback'), $bodyTo | Out-Null
if (Get-Service ARGUS -ErrorAction SilentlyContinue) { Stop-Service ARGUS -Force }
Copy-Item (Join-Path $here 'ArgusService.exe') $program -Force

$config = Join-Path $data 'argus.yaml'
if (-not (Test-Path $config)) { Copy-Item (Join-Path $here '..\argus.winhvk.yaml') $config }
# Only admins and SYSTEM change what the service starts.
icacls $data /inheritance:r /grant:r 'SYSTEM:(OI)(CI)F' 'Administrators:(OI)(CI)F' 'Users:(OI)(CI)RX' | Out-Null
& (Join-Path $program 'ArgusService.exe') --check $config
if ($LASTEXITCODE -ne 0) { throw 'argus.yaml has a problem; fix it and run this again.' }

Get-Process Mira -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$bodyTo*" } | Stop-Process -Force
Copy-Item $bodyFrom $bodyTo -Force

# The old companion's startup shortcut goes to rollback; the service starts her companion from now on.
$startup = Join-Path $user 'AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\MIRA Companion.lnk'
if (Test-Path $startup) { Move-Item $startup (Join-Path $data 'rollback\MIRA Companion.lnk') -Force }
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like '*companion run*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Get-Process MiraPet -ErrorAction SilentlyContinue | Stop-Process -Force

if (-not (Get-Service ARGUS -ErrorAction SilentlyContinue)) {
    sc.exe create ARGUS binPath= ("`"" + (Join-Path $program 'ArgusService.exe') + "`"") start= auto obj= LocalSystem DisplayName= 'ARGUS' | Out-Null
}
sc.exe description ARGUS 'ARGUS: houses MIRA on this PC (her body and companion in your session, from ProgramData\ARGUS\argus.yaml).' | Out-Null
sc.exe failure ARGUS reset= 86400 actions= restart/5000/restart/5000/restart/30000 | Out-Null
Start-Service ARGUS
Start-Sleep 12
Get-Service ARGUS | Format-Table -AutoSize Name, Status, StartType
Get-Content (Join-Path $data 'service.log') -Tail 8
