# argus/install.ps1 - the ARGUS overlay into $env:ARGUS_HOME on Windows. Same rules as install.sh, except that
# files are COPIED when changed (symlinks need Developer Mode or admin on Windows): skins and plugins follow the
# repo, config.yaml is seeded once and then belongs to the user.
param([switch]$Quiet)
$ErrorActionPreference = 'Stop'
$argusDir = $PSScriptRoot
$home_ = if ($env:ARGUS_HOME) { $env:ARGUS_HOME } else { Join-Path $env:LOCALAPPDATA 'argus' }
foreach ($d in @('skins', 'plugins', 'mira-skills')) { New-Item -ItemType Directory -Force -Path (Join-Path $home_ $d) | Out-Null }

function Sync-Tree([string]$src, [string]$dst) {
    # Mirror $src into $dst, copying only files whose content differs.
    Get-ChildItem -LiteralPath $src -Recurse -File | ForEach-Object {
        $rel = $_.FullName.Substring($src.Length).TrimStart('\')
        $target = Join-Path $dst $rel
        if (-not (Test-Path -LiteralPath $target) -or
            (Get-FileHash -LiteralPath $target).Hash -ne (Get-FileHash -LiteralPath $_.FullName).Hash) {
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
            Copy-Item -LiteralPath $_.FullName -Destination $target -Force
            Write-Host "argus: updated $rel"
        }
    }
}

Sync-Tree (Join-Path $argusDir 'skins') (Join-Path $home_ 'skins')
if (Test-Path -LiteralPath (Join-Path $argusDir 'plugins')) { Sync-Tree (Join-Path $argusDir 'plugins') (Join-Path $home_ 'plugins') }

$config = Join-Path $home_ 'config.yaml'
if (-not (Test-Path -LiteralPath $config)) {
    # Windows has no ~/.argus: point MIRA's skills folder at this home instead.
    (Get-Content -LiteralPath (Join-Path $argusDir 'config\config.yaml') -Raw).Replace('~/.argus/mira-skills', ($home_ -replace '\\', '/') + '/mira-skills') |
        Set-Content -LiteralPath $config -Encoding utf8
    Write-Host "argus: wrote a starting $config (yours from now on)"
}
$envFile = Join-Path $home_ '.env'
if (-not (Test-Path -LiteralPath $envFile)) { New-Item -ItemType File -Path $envFile | Out-Null; Write-Host "argus: created $envFile for provider keys" }
