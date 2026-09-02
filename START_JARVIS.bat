@echo off
title J.A.R.V.I.S. LAUNCHER
cd /d "%~dp0"
echo.
echo  ============================================
echo    J.A.R.V.I.S.  -  STARTING ALL SERVICES
echo  ============================================
echo.

echo [1/5] Pulling latest build...
git pull

echo [2/5] Checking Python packages (first run only)...
if not exist ".jarvis_installed" (
    pip install -r requirements.txt
    echo installed > .jarvis_installed
)

echo [3/5] Starting AI node...
findstr /C:"\"provider\": \"cloud\"" jarvis_settings.json >nul 2>&1
if not errorlevel 1 (
    echo       Cloud brain configured - skipping Ollama to save CPU/RAM.
) else (
    curl -s http://localhost:11434/api/tags >nul 2>&1
    if errorlevel 1 (
        start "J.A.R.V.I.S. AI NODE" /min cmd /k ollama serve
        echo       Waiting for Ollama to come online...
        timeout /t 5 /nobreak >nul
    ) else (
        echo       Ollama already online.
    )
)

echo [4/5] Starting voice bridge...
start "J.A.R.V.I.S. VOICE BRIDGE" /min cmd /k python jarvis_voice.py

echo [5/5] Launching HUD...
start "J.A.R.V.I.S. HUD" /min cmd /k python -m streamlit run jarvis.py --server.headless true
timeout /t 6 /nobreak >nul
start "" http://localhost:8501

echo.
echo  All systems online, sir. The service windows are minimised in your taskbar.
echo  Run STOP_JARVIS.bat to shut everything down.
timeout /t 4 >nul
exit
