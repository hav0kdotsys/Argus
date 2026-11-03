# Takes the ARGUS service off winhvk and puts the old body and companion back, exactly as they were. Admin PowerShell.
$ErrorActionPreference = 'Continue'
$data = Join-Path $env:ProgramData 'ARGUS'
$user = 'C:\Users\HavoK'
if (Get-Service ARGUS -ErrorAction SilentlyContinue) { Stop-Service ARGUS -Force; sc.exe delete ARGUS | Out-Null }
Get-Process Mira -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$user\AppData\Local\Programs\Mira*" } | Stop-Process -Force
schtasks.exe /Change /TN "MIRA-Pet" /ENABLE | Out-Null
schtasks.exe /Run /TN "MIRA-Pet" | Out-Null
$saved = Join-Path $data 'rollback\MIRA Companion.lnk'
$startup = Join-Path $user 'AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\MIRA Companion.lnk'
if (Test-Path $saved) { Move-Item $saved $startup -Force }
"ARGUS service removed; MiraPet and the MIRA Companion shortcut are back (log on again, or run the shortcut, to start her companion)."
