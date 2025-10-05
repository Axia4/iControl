@echo off
echo Starting iControl Suite with iSync Integration
echo.

echo Starting iSync Server (Port 5342)...
start "iSync Server" cmd /k "cd /d "%~dp0iSync" && python main.py"

timeout /t 3 /nobreak >nul

echo Starting iControl Main Application (Port 5343)...
start "iControl Main" cmd /k "cd /d "%~dp0iControl" && python main.py"

echo.
echo Both applications should be starting...
echo.
echo iSync Dashboard: http://localhost:5342
echo iControl Dashboard: http://localhost:5343
echo iControl iSync Integration: http://localhost:5343/isync
echo.
echo Press any key to exit...
pause >nul
