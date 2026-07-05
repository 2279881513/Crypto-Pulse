@echo off
set PYTHONPATH=%~dp0..
echo [CryptoPulse] Starting web server...
echo [CryptoPulse] Open http://127.0.0.1:8080
echo.
python run_web.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [CryptoPulse] Failed to start!
    echo   Try: pip install flask pandas numpy loguru aiohttp websocket-client
    echo.
    pause
)
