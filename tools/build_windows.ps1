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

function Invoke-CheckedCommand {
    param(
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command,
        [Parameter(Mandatory = $true)]
        [string]$FailureMessage
    )

    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw $FailureMessage
    }
}

function Test-PyInstallerWarnings {
    param(
        [Parameter(Mandatory = $true)]
        [string]$WarnFilePath
    )

    if (-not (Test-Path $WarnFilePath -PathType Leaf)) {
        throw "Missing PyInstaller warnings file: $WarnFilePath"
    }

    $knownOptionalModules = @(
        "_frozen_importlib_external",
        "pwd",
        "grp",
        "posix",
        "resource",
        "_scproxy",
        "termios",
        "_posixshmem",
        "_posixsubprocess",
        "fcntl",
        "pyimod02_importers",
        "shiboken6.isValid",
        "yaml",
        "lexicon",
        "fluidity",
        "pyasn1",
        "pyasn1.codec",
        "sspi",
        "sspicon",
        "pywintypes",
        "gssapi",
        "vms_lib",
        "java",
        "java.lang",
        "_winreg"
    )

    $unexpectedTopLevel = @()
    foreach ($line in Get-Content $WarnFilePath) {
        if ($line -match "^missing module named (.+?) - imported by .+\(top-level\)") {
            $moduleName = $matches[1].Trim("'")
            if ($knownOptionalModules -notcontains $moduleName -and -not $moduleName.StartsWith("multiprocessing.")) {
                $unexpectedTopLevel += $moduleName
            }
        }
    }

    if ($unexpectedTopLevel.Count -gt 0) {
        $uniqueMissing = $unexpectedTopLevel | Sort-Object -Unique
        throw "Unexpected top-level missing modules in PyInstaller analysis: $($uniqueMissing -join ', ')"
    }
}

if (-not (Test-Path $venvPython)) {
    throw "Missing build interpreter: $venvPython. Create $VenvPath first."
}

if ($Clean) {
    Remove-Item -Recurse -Force "$root\build" -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force "$root\dist" -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force "$root\release" -ErrorAction SilentlyContinue
}

Invoke-CheckedCommand -Command { & $venvPython -m pip install "pip<26" } -FailureMessage "Failed to install constrained pip version."
Invoke-CheckedCommand -Command { & $venvPython -m pip install ".[dev,build]" } -FailureMessage "Failed to install build dependencies."
Invoke-CheckedCommand -Command { & $venvPython -c "from PySide6.QtWidgets import QApplication; print('PySide6 import OK')" } -FailureMessage "PySide6 import smoke check failed."

if (-not $SkipTests) {
    Write-Host "Running test suite before packaging..."
    Invoke-CheckedCommand -Command { & $venvPython -m pytest -q } -FailureMessage "Test suite failed. Packaging stopped."
}

$version = (Get-Content -Raw "$root\pyproject.toml" | Select-String -Pattern 'version = "(.+?)"' -AllMatches).Matches[0].Groups[1].Value
$specName = if ($Debug) { "SSHFerryDebug.spec" } else { "SSHFerry.spec" }
$appName = if ($Debug) { "SSHFerryDebug" } else { "SSHFerry" }
$packageSuffix = if ($Debug) { "windows-debug" } else { "windows" }
$releaseDir = Join-Path $root "release\$appName-$version-$packageSuffix"
$zipPath = Join-Path $root "release\$appName-$version-$packageSuffix.zip"
$shaPath = Join-Path $root "release\$appName-$version-$packageSuffix.sha256"
$portableDataDir = Join-Path $releaseDir "data"

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
Invoke-CheckedCommand -Command { & $venvPython -m PyInstaller --noconfirm --clean (Join-Path $root $specName) } -FailureMessage "PyInstaller build failed."
$warnFilePath = Join-Path $root "build\$appName\warn-$appName.txt"
Test-PyInstallerWarnings -WarnFilePath $warnFilePath

New-Item -ItemType Directory -Path $releaseDir | Out-Null
$distDirPath = Join-Path $root "dist\$appName"
$distExePath = Join-Path $root "dist\$appName.exe"
if (Test-Path $distDirPath -PathType Container) {
    Copy-Item -Recurse -Force "$distDirPath\*" $releaseDir
} elseif (Test-Path $distExePath -PathType Leaf) {
    Copy-Item -Force $distExePath $releaseDir
} else {
    throw "Build output not found for $appName. Expected $distDirPath or $distExePath."
}
if (Test-Path $portableDataDir) {
    Remove-Item -Recurse -Force $portableDataDir
}
New-Item -ItemType Directory -Path (Join-Path $portableDataDir "backend_runtime\auth") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $portableDataDir "workspace") -Force | Out-Null
"Portable runtime data directory for packaged builds." | Set-Content -Encoding UTF8 (Join-Path $portableDataDir "README.txt")

$readmeLines = @(
    "SSHFerry Windows package",
    "========================",
    "",
    "1. Run $appName.exe"
)
if ($Debug) {
    $readmeLines += "2. Debug build is folder-based; keep the whole folder together and do not copy only the .exe file"
    $readmeLines += "3. First launch may be slower due to initialization"
    $readmeLines += "4. Packaged builds store runtime data under:"
    $readmeLines += "   .\data\"
    $readmeLines += "5. Site data is stored under:"
    $readmeLines += "   .\data\sites.json"
    $readmeLines += "6. startup diagnostics log is stored under:"
    $readmeLines += "   .\data\startup.log"
    $readmeLines += "7. Inspect the console window for startup failures"
} else {
    $readmeLines += "2. Release build is a single-file executable; you can copy $appName.exe to the Desktop and launch it there"
    $readmeLines += "3. First launch may be slower because the packaged runtime is unpacked on startup"
    $readmeLines += "4. Runtime data is stored in a .\data\ folder next to the executable"
    $readmeLines += "5. Site data is stored under:"
    $readmeLines += "   .\data\sites.json"
    $readmeLines += "6. startup diagnostics log is stored under:"
    $readmeLines += "   .\data\startup.log"
    $readmeLines += "7. If the GUI build does not start, build again with -Debug and inspect console output"
}

$readmeLines -join "`r`n" | Set-Content -Encoding UTF8 (Join-Path $releaseDir "README.txt")

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
