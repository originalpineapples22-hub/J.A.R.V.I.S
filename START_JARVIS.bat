@echo off
title J.A.R.V.I.S. LAUNCHER
cd /d "%~dp0"
echo.
echo  ============================================
echo    J.A.R.V.I.S.  -  STARTING ALL SERVICES
echo  ============================================
echo.

if not exist ".git" (
    echo.
    echo  ERROR: This launcher is not inside the cloned J.A.R.V.I.S repository.
    echo  Folder: %CD%
    echo.
    echo  Run the START_JARVIS.bat that lives INSIDE the folder you cloned from GitHub,
    echo  or clone it fresh in cmd:
    echo    git clone -b claude/jarvis-self-learning-pfsxu0 https://github.com/originalpineapples22-hub/J.A.R.V.I.S.git
    echo.
    pause
    exit /b 1
)

echo [1/5] Pulling latest build...
git pull

echo [2/5] Checking Python packages (installs only when requirements change)...
fc /b requirements.txt .jarvis_installed >nul 2>&1
if errorlevel 1 (
    pip install -r requirements.txt
    copy /y requirements.txt .jarvis_installed >nul
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

echo [4/5] Starting ear + bridge (Whisper loads on first run, ~1 min)...
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
