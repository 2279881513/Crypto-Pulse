@echo off
set PYTHONPATH=%~dp0..
python -m pytest tests/ -v %*
if %ERRORLEVEL% NEQ 0 (
    pause
)
