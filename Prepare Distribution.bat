@echo off
rem Makes a clean copy of the app in the dist folder, without the API key, PDFs or results.
setlocal
title Waiver Contacts - Prepare distribution
cd /d "%~dp0"

set "PYCMD="
if exist "%~dp0.venv\Scripts\python.exe" set PYCMD="%~dp0.venv\Scripts\python.exe"
if not defined PYCMD set "PYCMD=py -3"
%PYCMD% "%~dp0tools\prepare_distribution.py"
echo.
pause
