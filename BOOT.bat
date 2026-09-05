@echo off
REM 0.5.4.M.4 - double-click this to boot. Opens two windows:
REM   "core"   runs the assistant on this PC
REM   "tunnel" gives it a public https address for your phone
REM Closing either window takes it offline.
cd /d "%~dp0"
title 0.5.4.M.4 boot
echo.
echo   Booting 0.5.4.M.4 ...
echo.
echo   Two windows will open. Leave both open.
echo   The core window prints your access token.
echo.
start "0.5.4.M.4 core"   powershell -ExecutionPolicy Bypass -NoExit -File "%~dp0start.ps1"
start "0.5.4.M.4 tunnel" powershell -ExecutionPolicy Bypass -NoExit -File "%~dp0tunnel.ps1"
echo   Done - this window can be closed.
timeout /t 8 >nul
