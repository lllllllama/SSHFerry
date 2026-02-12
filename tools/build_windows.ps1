param(
    [switch]$Clean,
    [switch]$NoZip
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

if ($Clean) {
    Remove-Item -Recurse -Force "$root\build" -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force "$root\dist" -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force "$root\release" -ErrorAction SilentlyContinue
}

python -m pip install --upgrade pip
python -m pip install ".[build]"

$version = (Get-Content -Raw "$root\pyproject.toml" | Select-String -Pattern 'version = "(.+?)"' -AllMatches).Matches[0].Groups[1].Value
$appName = "SSHFerry"
$releaseDir = Join-Path $root "release\$appName-$version-windows"
$zipPath = Join-Path $root "release\$appName-$version-windows.zip"
$shaPath = Join-Path $root "release\$appName-$version-windows.sha256"

if (Test-Path $releaseDir) {
    Remove-Item -Recurse -Force $releaseDir
}
if (Test-Path $zipPath) {
    Remove-Item -Force $zipPath
}
if (Test-Path $shaPath) {
    Remove-Item -Force $shaPath
}

pyinstaller `
  --noconfirm `
  --windowed `
  --clean `
  --name $appName `
  --collect-all PySide6 `
  --hidden-import src.ui.main_window `
  --hidden-import src.ui.panels.local_panel `
  --hidden-import src.ui.panels.remote_panel `
  --hidden-import src.ui.panels.task_center `
  --hidden-import src.ui.widgets.site_editor `
  --paths $root `
  src\app\main.py

New-Item -ItemType Directory -Path $releaseDir | Out-Null
Copy-Item -Recurse -Force "$root\dist\$appName\*" $releaseDir

@" 
SSHFerry Windows package
========================

1. Run SSHFerry.exe
2. First launch may be slower due to initialization
3. sites.json is stored under:
   %USERPROFILE%\AppData\Local\SSHFerry\sites.json
"@ | Set-Content -Encoding UTF8 (Join-Path $releaseDir "README.txt")

$buildInfo = @(
    "app=$appName",
    "version=$version",
    "built_at_utc=$([DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ'))",
    "python=$(& python --version 2>&1)"
)
$buildInfo -join "`n" | Set-Content -Encoding UTF8 (Join-Path $releaseDir "BUILD_INFO.txt")

if (-not $NoZip) {
    Compress-Archive -Path "$releaseDir\*" -DestinationPath $zipPath -CompressionLevel Optimal
    $hash = (Get-FileHash -Algorithm SHA256 $zipPath).Hash.ToLower()
    "$hash  $([System.IO.Path]::GetFileName($zipPath))" | Set-Content -Encoding ASCII $shaPath
}

Write-Host ""
Write-Host "Build complete."
Write-Host "Package dir: $releaseDir"
if (-not $NoZip) {
    Write-Host "Zip: $zipPath"
    Write-Host "SHA256: $shaPath"
}
