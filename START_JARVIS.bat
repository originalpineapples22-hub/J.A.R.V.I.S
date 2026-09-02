@echo off
title J.A.R.V.I.S. LAUNCHER
cd /d "%~dp0"
echo Pulling latest J.A.R.V.I.S. build...
git pull
echo Starting voice bridge (keep this window open, it stays silent)...
start "J.A.R.V.I.S. VOICE BRIDGE" cmd /k python jarvis_voice.py
timeout /t 2 /nobreak >nul
echo Launching HUD...
streamlit run jarvis.py
