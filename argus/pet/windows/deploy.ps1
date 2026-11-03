# Deploy ARGUS main on winhvk: body (task MIRA-Pet) and brain (Startup shortcut "MIRA Companion", shell-launched).
# Once the ARGUS service houses her (argus/worker/windows/install.ps1), it owns her body and companion: this only
# updates ARGUS and lets the service start her companion again on the new code.
if (Get-Service ARGUS -ErrorAction SilentlyContinue) {
    Set-Location D:\Network\Projects\Argus
    git fetch --depth 1 origin main 2>&1 | Out-Null
    git reset --hard FETCH_HEAD 2>&1 | Select-Object -Last 1
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like "*companion run*" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
    "ARGUS service: her companion restarts on the new code within 30 s"
    exit 0
}
Stop-ScheduledTask -TaskName "MIRA-Pet" -ErrorAction SilentlyContinue
Get-Process MiraPet -ErrorAction SilentlyContinue | Stop-Process -Force
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like "*companion run*" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Set-Location D:\Network\Projects\Argus
git fetch --depth 1 origin main 2>&1 | Out-Null
git reset --hard FETCH_HEAD 2>&1 | Select-Object -Last 1
Set-Location argus\pet\windows\MiraPet
dotnet build -c Release -nologo -v q 2>&1 | Select-String -Pattern "error|warning CS|Build succeeded"
Start-ScheduledTask -TaskName "MIRA-Pet"
$lnk = Join-Path ([Environment]::GetFolderPath('Startup')) 'MIRA Companion.lnk'
$a = New-ScheduledTaskAction -Execute "explorer.exe" -Argument "`"$lnk`""
Register-ScheduledTask -TaskName "MIRA companion start (temporary)" -Action $a -Force | Out-Null
Start-ScheduledTask -TaskName "MIRA companion start (temporary)"
Start-Sleep 25
Unregister-ScheduledTask -TaskName "MIRA companion start (temporary)" -Confirm:$false
"pet: " + [bool](Get-Process MiraPet -ErrorAction SilentlyContinue)
"companion: " + [bool](Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like "*companion run*" })
