@echo off
setlocal

cd /d "%~dp0"

set "SUPERWRITER_URL=http://127.0.0.1:18080/"
start "Superwriter" "%SUPERWRITER_URL%"

where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    py -3 "%~dp0superwriter_local_server.py" %*
    set "EXIT_CODE=%ERRORLEVEL%"
    goto after_run
)

where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    python "%~dp0superwriter_local_server.py" %*
    set "EXIT_CODE=%ERRORLEVEL%"
    goto after_run
)

echo [Superwriter] Python 3 not found.
echo Please install Python 3 and ensure "py" or "python" is available in PATH.
set "EXIT_CODE=9009"
goto fail

:after_run
if not "%EXIT_CODE%"=="0" goto fail
exit /b 0

:fail
echo.
echo [Superwriter] Start failed with exit code %EXIT_CODE%.
pause
exit /b %EXIT_CODE%

