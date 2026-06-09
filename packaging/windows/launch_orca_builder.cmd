@echo off
setlocal
cd /d "%~dp0"

where pyw.exe >nul 2>nul
if %errorlevel%==0 (
    start "" pyw.exe -3 "%~dp0tools\Orca_input\orca_input.py"
    exit /b 0
)

where pythonw.exe >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw.exe "%~dp0tools\Orca_input\orca_input.py"
    exit /b 0
)

where py.exe >nul 2>nul
if %errorlevel%==0 (
    py.exe -3 "%~dp0tools\Orca_input\orca_input.py"
    exit /b %errorlevel%
)

where python.exe >nul 2>nul
if %errorlevel%==0 (
    python.exe "%~dp0tools\Orca_input\orca_input.py"
    exit /b %errorlevel%
)

echo Python 3.9 or newer was not found.
echo Please install Python from https://www.python.org/downloads/windows/
echo During installation, enable "Add python.exe to PATH" and Tcl/Tk support.
pause
exit /b 1
