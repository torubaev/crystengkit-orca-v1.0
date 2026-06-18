@echo off
setlocal
cd /d "%~dp0"

set "INSTALL_PYTHON_IF_MISSING=0"
set "CHECKER_ARGS="
set "PYTHON_INSTALLED_EXE="

:parse_args
if "%~1"=="" goto after_parse
if /i "%~1"=="--install-python-if-missing" (
    set "INSTALL_PYTHON_IF_MISSING=1"
) else (
    set "CHECKER_ARGS=%CHECKER_ARGS% %~1"
)
shift
goto parse_args

:after_parse

where py.exe >nul 2>nul
if not errorlevel 1 (
    py.exe -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul
    if not errorlevel 1 (
        py.exe -3 "%~dp0install\install.py"%CHECKER_ARGS%
        exit /b %errorlevel%
    )
)

where python.exe >nul 2>nul
if not errorlevel 1 (
    python.exe -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul
    if not errorlevel 1 (
        python.exe "%~dp0install\install.py"%CHECKER_ARGS%
        exit /b %errorlevel%
    )
)

if "%INSTALL_PYTHON_IF_MISSING%"=="1" (
    call :install_python
    set "INSTALL_PYTHON_IF_MISSING=0"
    if not errorlevel 1 (
        if defined PYTHON_INSTALLED_EXE (
            "%PYTHON_INSTALLED_EXE%" "%~dp0install\install.py"%CHECKER_ARGS%
            exit /b %errorlevel%
        )
        goto after_parse
    )
)

echo Python 3.9 or newer was not found.
echo Please install Python from https://www.python.org/downloads/windows/
echo During installation, enable "Add python.exe to PATH" and Tcl/Tk support.
pause
exit /b 1

:install_python
echo Python 3.9 or newer was not found.
echo.
echo The installer will try to install Python 3.12 with winget.
echo This requires an internet connection and may show Microsoft Store / winget prompts.
echo.

where winget.exe >nul 2>nul
if errorlevel 1 (
    echo winget was not found on this computer.
    echo Opening the official Python download page instead.
    start "" "https://www.python.org/downloads/windows/"
    exit /b 1
)

winget.exe install --id Python.Python.3.12 -e --source winget --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
    echo Python installation with winget failed.
    echo Opening the official Python download page instead.
    start "" "https://www.python.org/downloads/windows/"
    exit /b 1
)

if exist "%LocalAppData%\Programs\Python\Python312\python.exe" (
    set "PYTHON_INSTALLED_EXE=%LocalAppData%\Programs\Python\Python312\python.exe"
)

echo.
echo Python installation finished. Continuing with the CrystEngKit checker...
exit /b 0
