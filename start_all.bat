@echo off
setlocal
if /i "%~1"=="--server" goto server
where wt.exe >nul 2>&1
if errorlevel 1 (
    echo Windows Terminal is required for three tabs. Please install it first.
    goto failed
)
if not exist "%~dp0backend\venv\Scripts\python.exe" (
    echo Missing backend\venv. Follow the installation steps in run.md.
    goto failed
)
where npm.cmd >nul 2>&1
if errorlevel 1 (
    echo Install Node.js and npm first.
    goto failed
)
if not exist "%~dp0frontend\node_modules\vite\bin\vite.js" (
    echo Run npm install in the frontend folder first.
    goto failed
)
rem PostgreSQL must already be running. Stop the stack before starting again.
wt.exe -w new new-tab --title "Credit Dossier - MCP" --suppressApplicationTitle -d "%~dp0mcp" cmd.exe /d /k call "%~f0" --server mcp ; new-tab --title "Credit Dossier - Backend" --suppressApplicationTitle -d "%~dp0backend" cmd.exe /d /k call "%~f0" --server backend ; new-tab --title "Credit Dossier - Frontend" --suppressApplicationTitle -d "%~dp0frontend" cmd.exe /d /k call "%~f0" --server frontend
if errorlevel 1 goto failed
exit /b 0

:server
if /i "%~2"=="mcp" (
    cd /d "%~dp0mcp"
    "%~dp0backend\venv\Scripts\python.exe" server.py
    exit /b
)
if /i "%~2"=="backend" (
    cd /d "%~dp0backend"
    "%~dp0backend\venv\Scripts\python.exe" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
    exit /b
)
if /i "%~2"=="frontend" (
    cd /d "%~dp0frontend"
    call npm.cmd run dev -- --port 8080 --strictPort
    exit /b
)
echo Unknown server: %~2
exit /b 1

:failed
pause
exit /b 1
