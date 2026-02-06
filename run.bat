@echo off
REM Activate sshferry conda environment and run application

echo Activating sshferry conda environment...
call conda activate sshferry

if errorlevel 1 (
    echo Error: Failed to activate sshferry environment
    echo Please run: conda create -n sshferry python=3.11 -y
    pause
    exit /b 1
)

echo Running SSHFerry...
python -m src.app.main
