@echo off
set PYTHONPATH=C:\Users\xm227\Desktop\lianghua\kan\cryptopulse
echo ====== Refresh last 7 days K-line data ======
echo.
python "%~dp0refresh_7days.py"
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo FAILED! Check log above
    pause
) else (
    echo Done!
    timeout /t 3
)
