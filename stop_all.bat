@echo off
setlocal
set "CREDIT_DOSSIER_START_SCRIPT=%~dp0start_all.bat"
rem Stop server children of CMD shells marked by this repository's start script.
rem Keep the terminal shells alive so Windows Terminal does not report a crash.
rem Force-stopping interrupts pending requests. PostgreSQL is left running.
powershell.exe -NoLogo -NoProfile -Command "$ErrorActionPreference = 'Stop'; try { $servers = @(Get-CimInstance Win32_Process -Filter \"Name = 'cmd.exe'\" | Where-Object { $_.CommandLine -and $_.CommandLine.IndexOf($env:CREDIT_DOSSIER_START_SCRIPT, [StringComparison]::OrdinalIgnoreCase) -ge 0 -and $_.CommandLine -match '--server (mcp|backend|frontend)(\s|$)' }); if ($servers.Count -eq 0) { Write-Host 'No servers started by start_all.bat are running.' }; $failed = $false; foreach ($server in $servers) { $children = @(Get-CimInstance Win32_Process -Filter ('ParentProcessId = ' + $server.ProcessId)); foreach ($child in $children) { Write-Host ('Stopping server process tree ' + $child.ProcessId); taskkill.exe /PID $child.ProcessId /T /F; if ($LASTEXITCODE -ne 0 -and (Get-Process -Id $child.ProcessId -ErrorAction SilentlyContinue)) { $failed = $true } } }; if ($failed) { exit 1 } } catch { Write-Host $_.Exception.Message; exit 1 }"
if errorlevel 1 (
    echo Some servers could not be stopped. Review the message above.
    pause
    exit /b 1
)
exit /b 0
