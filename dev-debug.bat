@echo off
title SuperWriter Dev

echo [SuperWriter] Starting development mode...
echo.

:: Build server TypeScript first
echo [1/3] Building server...
call pnpm build:server
if errorlevel 1 (
    echo [ERROR] Server build failed.
    pause
    exit /b 1
)

:: Start frontend (Vite) in new window
echo [2/3] Starting frontend dev server...
start "SuperWriter Frontend" cmd /k "cd /d %~dp0 && pnpm dev:web"

:: Wait for frontend to be ready
echo [3/3] Starting Electron...
timeout /t 3 /nobreak >nul

:: Start Electron (loads frontend from localhost:5173 in dev mode)
start "SuperWriter" cmd /k "cd /d %~dp0apps\server && set NODE_ENV=development&& set DEBUG=1&& npx electron ."
