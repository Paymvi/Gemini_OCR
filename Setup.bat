@echo off
rem First-time setup for the Waiver Contacts app. Safe to run again at any time.
setlocal
title Waiver Contacts - Setup
cd /d "%~dp0"

echo.
echo   ============================================================
echo    Waiver Contacts - setup
echo   ============================================================
echo.

set "PYCMD="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1
if not errorlevel 1 set "PYCMD=py -3"
if defined PYCMD goto havepython
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1
if not errorlevel 1 set "PYCMD=python"
if defined PYCMD goto havepython
goto nopython

:havepython
%PYCMD% "%~dp0tools\setup_env.py"
if errorlevel 1 goto failed
echo.
pause
exit /b 0

:failed
echo.
echo   Setup did NOT finish. Read the PROBLEM line above, fix it, and
echo   double-click Setup.bat again. Running it again is always safe.
echo.
pause
exit /b 1

:nopython
echo   Python 3.9 or newer was not found on this computer.
echo   (An older Python may be installed; it is too old for this app.)
echo.
echo   To install it:
echo     1. Open https://www.python.org/downloads/windows/
echo     2. Download the latest "Windows installer (64-bit)".
echo     3. Run it. On the first screen, tick "Add python.exe to PATH",
echo        then click "Install Now".
echo     4. When it finishes, double-click Setup.bat again.
echo.
pause
exit /b 1
