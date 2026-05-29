@echo off
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0"

set "CHECKER=install.py"

if not exist "%CHECKER%" (
    echo ERROR: %CHECKER% was not found in this folder.
    echo Put this BAT file in the same folder as %CHECKER%.
    pause
    exit /b 1
)

echo Checking for Python...
echo.

where py >nul 2>nul
if not errorlevel 1 (
    py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul
    if not errorlevel 1 (
        echo Python found through Windows Python Launcher.
        py -3 -c "import tkinter" >nul 2>nul
        if errorlevel 1 call :tkinter_warning
        echo Running %CHECKER%...
        echo.
        py -3 "%CHECKER%"
        set "CHECKER_EXIT=!ERRORLEVEL!"
        goto :end
    )
)

where python >nul 2>nul
if not errorlevel 1 (
    python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul
    if not errorlevel 1 (
        echo Python found.
        python -c "import tkinter" >nul 2>nul
        if errorlevel 1 call :tkinter_warning
        echo Running %CHECKER%...
        echo.
        python "%CHECKER%"
        set "CHECKER_EXIT=!ERRORLEVEL!"
        goto :end
    )
)

where python3 >nul 2>nul
if not errorlevel 1 (
    python3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul
    if not errorlevel 1 (
        echo Python found.
        python3 -c "import tkinter" >nul 2>nul
        if errorlevel 1 call :tkinter_warning
        echo Running %CHECKER%...
        echo.
        python3 "%CHECKER%"
        set "CHECKER_EXIT=!ERRORLEVEL!"
        goto :end
    )
)

echo Python 3.9 or newer was not found on this computer.
echo.
echo Please install Python 3.9 or newer.
echo During installation on Windows, enable:
echo   Add python.exe to PATH
echo.
echo Opening the official Python download page...
start "" "https://www.python.org/downloads/windows/"
echo.
echo After installing Python, run this file again.
pause
exit /b 1

:tkinter_warning
echo.
echo WARNING: Python Tkinter support was not detected.
echo The graphical CrystEngKit tools need Tkinter.
echo Reinstall Python from python.org with Tcl/Tk support enabled if the checker reports a Tkinter problem.
echo.
exit /b 0

:end
echo.
if not "%CHECKER_EXIT%"=="0" (
    echo Finished with errors. Exit code: %CHECKER_EXIT%
) else (
    echo Finished.
)
pause
exit /b %CHECKER_EXIT%
