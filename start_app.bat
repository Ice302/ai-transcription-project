@echo off
setlocal EnableDelayedExpansion
TITLE TurboTranscribe Server Manager
COLOR 0B
cd /d "%~dp0"

:: Preferred ports. If another program already uses one, the next free port is picked.
set BACKEND_PORT=8000
set FRONTEND_PORT=5173

echo ===================================================
echo      Starting TurboTranscribe...
echo ===================================================
echo.

:: First start, or an update changed backend\requirements.txt / frontend\package-lock.json:
:: install what is missing before starting.
set "NEED_SETUP="
if not exist "backend\venv\Scripts\python.exe" set "NEED_SETUP=1"
if not exist "frontend\node_modules" set "NEED_SETUP=1"
if not defined NEED_SETUP (
    fc /b "backend\requirements.txt" "backend\venv\requirements.installed" >nul 2>&1 || set "NEED_SETUP=1"
    fc /b "frontend\package-lock.json" "frontend\node_modules\.turbotranscribe-lock" >nul 2>&1 || set "NEED_SETUP=1"
)
if defined NEED_SETUP (
    echo Installing or updating dependencies first. This takes a few minutes the first time...
    echo.
    call setup.bat /auto || ( pause & exit /b 1 )
    call :refresh_path
    echo.
)

call :free_port BACKEND_PORT || (pause & exit /b 1)
call :free_port FRONTEND_PORT || (pause & exit /b 1)

:: The frontend dev server proxies /api to this address (see frontend\vite.config.js).
set "BACKEND_URL=http://127.0.0.1:%BACKEND_PORT%"

echo [1/2] Launching Python backend on port %BACKEND_PORT%...
start "TurboTranscribe Backend" /MIN cmd /c "cd /d backend && venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port %BACKEND_PORT%"

echo [2/2] Launching React frontend on port %FRONTEND_PORT%...
start "TurboTranscribe Frontend" /MIN cmd /c "cd /d frontend && npm run dev -- --port %FRONTEND_PORT% --strictPort"

echo.
echo Waiting for the backend to answer...
for /L %%i in (1,1,40) do (
    curl -s -o nul "http://127.0.0.1:%BACKEND_PORT%/api/health" && goto ready
    timeout /t 1 > nul
)
echo [!] The backend did not answer yet; check the "TurboTranscribe Backend" window.
:ready
echo The speech model keeps loading in the background; the status pill turns green when ready.
start http://localhost:%FRONTEND_PORT%

echo.
echo ===================================================
echo   App: http://localhost:%FRONTEND_PORT%
echo   DO NOT CLOSE THIS WINDOW MANUALLY!
echo   PRESS ANY KEY HERE TO SAFELY SHUT DOWN EVERYTHING
echo ===================================================
pause > nul

echo.
echo Shutting down servers...
:: Only stop the two windows started above (and their child processes), never
:: whatever else happens to be listening on these ports.
taskkill /FI "WINDOWTITLE eq TurboTranscribe Backend*" /T /F > nul 2>&1
taskkill /FI "WINDOWTITLE eq TurboTranscribe Frontend*" /T /F > nul 2>&1

echo Shutdown complete. Goodbye!
timeout /t 2 > nul
exit /b 0

:: --------------------------------------------------------------------------
:: free_port VARNAME - bumps the port in VARNAME until nothing is listening on it.
:free_port
set /a _port=!%1!
set /a _last=_port+20
:free_port_try
netstat -ano | findstr /R /C:":!_port! .*LISTENING" > nul
if errorlevel 1 (
    if not "!_port!"=="!%1!" echo     Port !%1! is busy; using !_port! instead.
    set "%1=!_port!"
    exit /b 0
)
set /a _port+=1
if !_port! LEQ !_last! goto free_port_try
echo [!] No free port found near !%1!. Close some programs and try again.
exit /b 1

:: refresh_path - sees tools that setup.bat just installed (Node.js, ffmpeg) without a new window.
:refresh_path
for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')"`) do set "PATH=%%P;%PATH%"
exit /b 0
