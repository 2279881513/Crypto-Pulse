@echo off
cd /d "%~dp0.."
set PYTHONPATH=%CD%
python scripts/download_historical.py %*
if %ERRORLEVEL% NEQ 0 (
    pause
)
