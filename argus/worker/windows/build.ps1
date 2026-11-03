# Builds ArgusService.exe beside this script with .NET Framework 4.8's own compiler (no SDK needed). No admin.
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$csc = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
$out = Join-Path $here 'ArgusService.exe'
$src = Join-Path $here 'ArgusService.cs'
& $csc /nologo /target:exe /optimize+ "/out:$out" /r:System.ServiceProcess.dll /r:System.Management.dll $src
if ($LASTEXITCODE -ne 0) { throw 'ArgusService.cs did not build' }
"Built $out"
