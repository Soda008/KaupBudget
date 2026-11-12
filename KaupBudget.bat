@echo off
rem Starts KaupBudget. First run sets up Python packages (takes a minute).
setlocal
set "APPDIR=%~dp0"
set "VENV=%LOCALAPPDATA%\KaupBudget\venv"

if not exist "%VENV%\Scripts\python.exe" (
    echo Setting up KaupBudget for the first time...
    python -m venv "%VENV%" || (echo Python 3.11+ is required. & pause & exit /b 1)
    "%VENV%\Scripts\python.exe" -m pip install --upgrade pip
    "%VENV%\Scripts\python.exe" -m pip install -r "%APPDIR%requirements.txt" || (pause & exit /b 1)
)

start "" "%VENV%\Scripts\pythonw.exe" "%APPDIR%run.py" %*
endlocal
