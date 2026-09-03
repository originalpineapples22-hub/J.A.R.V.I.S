@echo off
title J.A.R.V.I.S. SHUTDOWN
echo Shutting down J.A.R.V.I.S. services...
taskkill /FI "WINDOWTITLE eq J.A.R.V.I.S. VOICE BRIDGE*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq J.A.R.V.I.S. HUD*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq J.A.R.V.I.S. AI NODE*" /T /F >nul 2>&1
echo All J.A.R.V.I.S. services stopped. (Ollama desktop app, if installed, keeps running.)
timeout /t 3 >nul
