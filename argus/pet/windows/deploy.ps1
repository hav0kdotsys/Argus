# Deploy ARGUS main on winhvk. The ARGUS service (argus/worker/windows/install.ps1) owns her body and companion: this
# updates ARGUS and lets the service start her companion again on the new code. Her body updates with
# argus\worker\windows\deploy-body.ps1.
if (-not (Get-Service ARGUS -ErrorAction SilentlyContinue)) { throw 'The ARGUS service is not installed: run argus\worker\windows\install.ps1 as admin.' }
Set-Location D:\Network\Projects\Argus
git fetch --depth 1 origin main 2>&1 | Out-Null
git reset --hard FETCH_HEAD 2>&1 | Select-Object -Last 1
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like "*companion run*" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
"ARGUS service: her companion restarts on the new code within 30 s"
