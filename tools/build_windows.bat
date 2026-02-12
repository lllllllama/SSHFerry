@echo off
setlocal

set SCRIPT_DIR=%~dp0
powershell -ExecutionPolicy Bypass -File "%SCRIPT_DIR%build_windows.ps1" %*

if errorlevel 1 (
  echo Build failed.
  exit /b 1
)

echo Build finished.
exit /b 0
