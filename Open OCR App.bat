@echo off
rem Opens the Waiver Contacts desktop app. Run Setup.bat once first.
setlocal
title Waiver Contacts
cd /d "%~dp0"

if not exist "%~dp0.venv\Scripts\pythonw.exe" goto needsetup
echo   Opening Waiver Contacts...
"%~dp0.venv\Scripts\python.exe" "%~dp0tools\setup_env.py" --check
if errorlevel 1 goto needsetup
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0gui.py"
exit /b 0

:needsetup
echo.
echo   The app is not set up on this computer yet, or setup did not finish.
echo   Double-click "Setup.bat" in this folder first, then try again.
echo.
pause
exit /b 1
