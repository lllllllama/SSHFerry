@echo off
setlocal

set "ROOT_DIR=%~dp0"
set "PYTHON_EXE="

if exist "%ROOT_DIR%.venv_compat\Scripts\python.exe" (
    set "PYTHON_EXE=%ROOT_DIR%.venv_compat\Scripts\python.exe"
) else if exist "%ROOT_DIR%.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%ROOT_DIR%.venv\Scripts\python.exe"
)

if defined PYTHON_EXE (
    echo Running SSHFerry with %PYTHON_EXE%
    "%PYTHON_EXE%" -m src.app.main
    exit /b %errorlevel%
)

REM Fallback to a conda environment when local virtualenvs are unavailable.
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
    echo Error: could not find a usable Python environment.
    echo Expected one of:
    echo   %ROOT_DIR%.venv_compat\Scripts\python.exe
    echo   %ROOT_DIR%.venv\Scripts\python.exe
    echo   a conda installation with environment "sshferry"
    pause
    exit /b 1
)

echo Activating conda environment: sshferry
call conda activate sshferry
if errorlevel 1 (
    echo Error: failed to activate conda environment "sshferry".
    pause
    exit /b 1
)

python -m src.app.main
exit /b %errorlevel%
