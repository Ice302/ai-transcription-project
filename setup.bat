@echo off
setlocal EnableDelayedExpansion
TITLE TurboTranscribe Setup
cd /d "%~dp0"

:: Installs everything TurboTranscribe needs. Safe to run again at any time.
::   setup.bat          one-time setup (pauses at the end)
::   setup.bat /auto    used by start_app.bat when dependencies are missing or changed
:: Missing system tools (Python, Node.js, ffmpeg) are installed with winget, which
:: ships with Windows 10 (1809+) and 11 as "App Installer".
set "AUTO="
if /i "%~1"=="/auto" set "AUTO=1"

echo === TurboTranscribe setup ===
echo.
echo [1/4] System tools

:: --- Python 3.10-3.13 (only needed to create backend\venv) ----------------------
set "NEED_VENV="
if exist "backend\venv\Scripts\python.exe" (
    backend\venv\Scripts\python.exe -c "import sys" >nul 2>&1 || (
        echo       The Python environment is broken; recreating it.
        rmdir /s /q backend\venv
    )
)
if not exist "backend\venv\Scripts\python.exe" set "NEED_VENV=1"
if defined NEED_VENV (
    call :find_python
    if not defined PY (
        call :winget_install Python.Python.3.12 "Python 3.12" "https://www.python.org/downloads/" || goto fail
        call :refresh_path
        call :find_python
    )
    if not defined PY (
        echo [!] Python was installed but this window cannot see it yet. Close it and run setup.bat again.
        goto fail
    )
    echo       Python: !PY!
) else (
    echo       Python: backend\venv already exists
)

:: --- Node.js 20+ -------------------------------------------------------------
call :check_node
if errorlevel 2 (
    call :winget_install OpenJS.NodeJS.LTS "Node.js" "https://nodejs.org/" || goto fail
    call :refresh_path
    call :check_node
)
if errorlevel 1 (
    echo [!] Node.js 20 or newer is required: https://nodejs.org/  ^(found an older version or none^)
    goto fail
)

:: --- ffmpeg ----------------------------------------------------------------------
where ffmpeg >nul 2>&1 || (
    call :winget_install Gyan.FFmpeg "ffmpeg" "https://www.gyan.dev/ffmpeg/builds/" || goto fail
    call :refresh_path
)
where ffmpeg >nul 2>&1 || (
    echo [!] ffmpeg was installed but this window cannot see it yet. Close it and run setup.bat again.
    goto fail
)
echo       ffmpeg: found

:: --- Python packages -----------------------------------------------------------
echo [2/4] Python packages (about 1.2 GB the first time)
if defined NEED_VENV (
    !PY! -m venv backend\venv || goto fail
)
backend\venv\Scripts\python.exe -m pip install --upgrade pip >nul
backend\venv\Scripts\python.exe -m pip install -r backend\requirements.txt || goto fail
where nvidia-smi >nul 2>&1 && (
    echo       NVIDIA GPU detected: installing the CUDA libraries ^(about 2 GB the first time^)
    backend\venv\Scripts\python.exe -m pip install nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*" || goto fail
) || echo       No NVIDIA GPU detected: speech recognition will run on the CPU.
:: Remember what was installed, so start_app.bat can tell when an update changed it.
copy /y backend\requirements.txt backend\venv\requirements.installed >nul

:: --- Frontend packages -----------------------------------------------------------
echo [3/4] Frontend packages
pushd frontend
:: "npm install", not "npm ci": ci deletes node_modules first, which fails half-way while the
:: app is running and leaves it broken. npm exits with negative codes too, hence "neq 0".
call npm install --no-audit --no-fund
set "NPM_RESULT=!errorlevel!"
popd
if not "!NPM_RESULT!"=="0" goto fail
copy /y frontend\package-lock.json frontend\node_modules\.turbotranscribe-lock >nul

:: --- Settings ---------------------------------------------------------------------
echo [4/4] Settings
if not exist "backend\.env" (
    copy backend\.env.example backend\.env >nul
    echo       Created backend\.env - add your OPENROUTER_API_KEY there to enable the notes assistant.
) else (
    echo       backend\.env kept as it is
)

echo.
echo Setup complete. The speech model ^(up to 1.6 GB^) downloads automatically on the first start.
if not defined AUTO (
    echo Run start_app.bat to launch TurboTranscribe.
    pause
)
exit /b 0

:fail
echo.
echo Setup did not finish. Fix the problem above and run setup.bat again.
if not defined AUTO pause
exit /b 1

:: ------------------------------------------------------------------------------
:: find_python - sets PY to a Python 3.10-3.13 command (tested versions), or leaves it empty.
:find_python
set "PY="
for %%V in (3.13 3.12 3.11 3.10) do (
    if not defined PY (
        py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V"
    )
)
if not defined PY (
    python -c "import sys; sys.exit(0 if (3, 10) <= sys.version_info[:2] <= (3, 13) else 1)" >nul 2>&1 && set "PY=python"
)
exit /b 0

:: check_node - errorlevel 0 = Node.js 20+, 1 = too old, 2 = missing
:check_node
where node >nul 2>&1 || exit /b 2
node -e "process.exit(Number(process.versions.node.split('.')[0]) >= 20 ? 0 : 1)" || exit /b 1
for /f %%N in ('node --version') do echo       Node.js: %%N
exit /b 0

:: winget_install ID "Name" "manual download URL"
:winget_install
where winget >nul 2>&1 || (
    echo [!] %~2 is missing and winget is not available on this PC.
    echo     Install %~2 from %~3 and run setup.bat again.
    exit /b 1
)
echo       %~2 is missing: installing it with winget...
winget install -e --id %~1 --accept-source-agreements --accept-package-agreements || (
    echo [!] winget could not install %~2. Install it from %~3 and run setup.bat again.
    exit /b 1
)
exit /b 0

:: refresh_path - picks up PATH changes made by installers without opening a new window.
:refresh_path
for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')"`) do set "PATH=%%P;%PATH%"
exit /b 0
