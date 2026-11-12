@echo off
setlocal
cd /d "%~dp0"
if exist "C:\Python313\pythonw.exe" (
  start "" "C:\Python313\pythonw.exe" crystal_habit_gui.py
  exit /b 0
)
if exist "%LocalAppData%\Programs\Python\Python312\pythonw.exe" (
  start "" "%LocalAppData%\Programs\Python\Python312\pythonw.exe" crystal_habit_gui.py
  exit /b 0
)
python crystal_habit_gui.py
if errorlevel 1 pause
