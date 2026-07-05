@echo off
cd /d "%~dp0.."
set PYTHONPATH=%~dp0..\..
python scripts/update_data.py %*
if %ERRORLEVEL% NEQ 0 (
    pause
)
