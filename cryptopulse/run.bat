@echo off
set PYTHONPATH=%~dp0..
python main.py %*
if %ERRORLEVEL% NEQ 0 (
    pause
)
