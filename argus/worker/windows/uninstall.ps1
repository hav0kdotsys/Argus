# Takes the ARGUS service off winhvk and puts her companion's startup shortcut back. Admin PowerShell.
$ErrorActionPreference = 'Continue'
$data = Join-Path $env:ProgramData 'ARGUS'
$user = 'C:\Users\HavoK'
if (Get-Service ARGUS -ErrorAction SilentlyContinue) { Stop-Service ARGUS -Force; sc.exe delete ARGUS | Out-Null }
Get-Process Mira -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$user\AppData\Local\Programs\Mira*" } | Stop-Process -Force
$saved = Join-Path $data 'rollback\MIRA Companion.lnk'
$startup = Join-Path $user 'AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\MIRA Companion.lnk'
if (Test-Path $saved) { Move-Item $saved $startup -Force }
"ARGUS service removed; the MIRA Companion shortcut is back (log on again, or run the shortcut, to start her companion)."
