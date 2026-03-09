param(
    [switch]$Clean,
    [switch]$NoZip,
    [switch]$Debug,
    [switch]$SkipTests,
    [string]$VenvPath = ".venv_compat"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root
$venvPython = Join-Path $root "$VenvPath\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    throw "Missing build interpreter: $venvPython. Create $VenvPath first."
}

if ($Clean) {
    Remove-Item -Recurse -Force "$root\build" -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force "$root\dist" -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force "$root\release" -ErrorAction SilentlyContinue
}

& $venvPython -m pip install "pip<26"
& $venvPython -m pip install ".[build]"
& $venvPython -c "from PySide6.QtWidgets import QApplication; print('PySide6 import OK')"

if (-not $SkipTests) {
    Write-Host "Running test suite before packaging..."
    & $venvPython -m pytest -q
}

$version = (Get-Content -Raw "$root\pyproject.toml" | Select-String -Pattern 'version = "(.+?)"' -AllMatches).Matches[0].Groups[1].Value
$specName = if ($Debug) { "SSHFerryDebug.spec" } else { "SSHFerry.spec" }
$appName = if ($Debug) { "SSHFerryDebug" } else { "SSHFerry" }
$packageSuffix = if ($Debug) { "windows-debug" } else { "windows" }
$releaseDir = Join-Path $root "release\$appName-$version-$packageSuffix"
$zipPath = Join-Path $root "release\$appName-$version-$packageSuffix.zip"
$shaPath = Join-Path $root "release\$appName-$version-$packageSuffix.sha256"

if (Test-Path $releaseDir) {
    Remove-Item -Recurse -Force $releaseDir
}
if (Test-Path $zipPath) {
    Remove-Item -Force $zipPath
}
if (Test-Path $shaPath) {
    Remove-Item -Force $shaPath
}

Write-Host "Building with spec: $specName"
& $venvPython -m PyInstaller --noconfirm --clean (Join-Path $root $specName)

New-Item -ItemType Directory -Path $releaseDir | Out-Null
Copy-Item -Recurse -Force "$root\dist\$appName\*" $releaseDir

@" 
SSHFerry Windows package
========================

1. Keep the whole folder together; do not copy only the .exe file
2. Run $appName.exe
3. First launch may be slower due to initialization
4. sites.json is stored under:
   %USERPROFILE%\AppData\Local\SSHFerry\sites.json
5. startup diagnostics log is stored under:
   %USERPROFILE%\AppData\Local\SSHFerry\startup.log
6. If the GUI build does not start, build again with -Debug and inspect console output
"@ | Set-Content -Encoding UTF8 (Join-Path $releaseDir "README.txt")

$buildInfo = @(
    "app=$appName",
    "spec=$specName",
    "debug_build=$Debug",
    "tests_skipped=$SkipTests",
    "version=$version",
    "built_at_utc=$([DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ'))",
    "python=$(& $venvPython --version 2>&1)"
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
