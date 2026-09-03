@echo off
title J.A.R.V.I.S. AUTOSTART INSTALLER
cd /d "%~dp0"
echo Installing J.A.R.V.I.S. to start automatically when Windows boots...
powershell -NoProfile -Command ^
  "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Startup')+'\J.A.R.V.I.S.lnk');" ^
  "$s.TargetPath='%~dp0START_JARVIS.bat';" ^
  "$s.WorkingDirectory='%~dp0';" ^
  "$s.Description='Start J.A.R.V.I.S. on login';" ^
  "$s.Save()"
if errorlevel 1 (
    echo Failed to create the startup shortcut.
) else (
    echo Done. J.A.R.V.I.S. will now launch every time you log in to Windows.
    echo To undo: delete "J.A.R.V.I.S" from  shell:startup
)
timeout /t 5 >nul
