@echo off
REM Activate sshferry conda environment and run application

REM Initialize conda for this shell session
REM Try common conda installation paths
if exist "D:\Anaconda3\Scripts\activate.bat" (
    call "D:\Anaconda3\Scripts\activate.bat" "D:\Anaconda3"
) else if exist "%USERPROFILE%\anaconda3\Scripts\activate.bat" (
    call "%USERPROFILE%\anaconda3\Scripts\activate.bat" "%USERPROFILE%\anaconda3"
) else if exist "%USERPROFILE%\miniconda3\Scripts\activate.bat" (
    call "%USERPROFILE%\miniconda3\Scripts\activate.bat" "%USERPROFILE%\miniconda3"
) else if exist "C:\ProgramData\anaconda3\Scripts\activate.bat" (
    call "C:\ProgramData\anaconda3\Scripts\activate.bat" "C:\ProgramData\anaconda3"
) else if exist "C:\ProgramData\miniconda3\Scripts\activate.bat" (
    call "C:\ProgramData\miniconda3\Scripts\activate.bat" "C:\ProgramData\miniconda3"
) else (
    echo Error: Could not find conda installation
    echo Please ensure Anaconda or Miniconda is installed
    pause
    exit /b 1
)

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
