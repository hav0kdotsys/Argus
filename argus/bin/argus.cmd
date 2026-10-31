@echo off
rem argus.cmd - lets `argus` work from cmd.exe and Windows Terminal profiles; the real launcher is argus.ps1.
where pwsh >nul 2>nul && (pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0argus.ps1" %*) || (powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0argus.ps1" %*)
exit /b %ERRORLEVEL%
