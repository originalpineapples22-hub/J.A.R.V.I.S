# 0.5.4.M.4 — one-click launcher for Windows.
# Right-click this file -> "Run with PowerShell", or from a PowerShell window:
#   cd <this folder>
#   .\start.ps1
#
# If Windows says "running scripts is disabled on this system", use:
#   powershell -ExecutionPolicy Bypass -File .\start.ps1
#
# It checks the folder is the right one, sets up a private Python environment,
# installs what is missing and starts the server on http://localhost:8080

# This script checks every step itself and explains failures in plain words,
# so errors must not become terminating ones behind its back.
$ErrorActionPreference = "Continue"
if (Get-Variable PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $false
}
$root = $PSScriptRoot
if (-not $root) { $root = Split-Path -Parent $MyInvocation.MyCommand.Path }
Set-Location $root

function Fail($msg) {
    Write-Host ""
    Write-Host "  X  $msg" -ForegroundColor Red
    Write-Host ""
    Read-Host "Press Enter to close"
    exit 1
}

Write-Host ""
Write-Host "  0.5.4.M.4  --  starting up" -ForegroundColor Cyan
Write-Host "  folder: $root" -ForegroundColor DarkGray
Write-Host ""

# --- 1. is this the right code? -----------------------------------------
if (-not (Test-Path "$root\jarvis\server.py")) {
    Fail @"
This folder does not contain the current version of 0.5.4.M.4.

  Expected: $root\jarvis\server.py   (not found)

You are most likely in the older Streamlit build. Get the current one:

  iwr -useb https://raw.githubusercontent.com/originalpineapples22-hub/J.A.R.V.I.S/claude/jarvis-self-learning-pfsxu0/deploy/bootstrap.ps1 | iex

That one line clones into %USERPROFILE%\jarvis-v3 and starts it. Paste it as a
single line - PowerShell shows ">>" and waits when you paste several at once.

If this IS the right folder, you are behind - run:  git pull
"@
}

# --- 2. anything shadowing the package? ---------------------------------
if (Test-Path "$root\jarvis.py") {
    Fail @"
There is a file called jarvis.py sitting next to the jarvis\ folder.

Python loads that file instead of the package, so 'jarvis.server' cannot be
found. The old build belongs in legacy\ - move or delete this one:

  Move-Item "$root\jarvis.py" "$root\legacy\jarvis_old.py"
"@
}

# --- 3. a sane place to live --------------------------------------------
if ($root -like "$env:WINDIR*") {
    Fail @"
This copy is inside the Windows system folder ($root).

Windows blocks writes there, so memory and settings cannot be saved. Move it:

  iwr -useb https://raw.githubusercontent.com/originalpineapples22-hub/J.A.R.V.I.S/claude/jarvis-self-learning-pfsxu0/deploy/bootstrap.ps1 | iex

That one line clones into %USERPROFILE%\jarvis-v3 and starts it. Paste it as a
single line - PowerShell shows ">>" and waits when you paste several at once.

Nothing is lost - this copy has no memory in it yet. Delete it afterwards.
"@
}

# --- 4. Python -----------------------------------------------------------
function Test-Python($exe, $extra) {
    if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { return $false }
    $v = (& $exe @extra --version 2>&1) -join " "
    return ($v -match "Python 3\.(\d+)" -and [int]$Matches[1] -ge 10)
}
$pyExe = $null; $pyArgs = @()
if     (Test-Python "py" @("-3"))  { $pyExe = "py";      $pyArgs = @("-3") }
elseif (Test-Python "python" @())  { $pyExe = "python";  $pyArgs = @() }
elseif (Test-Python "python3" @()) { $pyExe = "python3"; $pyArgs = @() }
if (-not $pyExe) {
    Fail @"
Python 3.10 or newer was not found.

Install it from https://www.python.org/downloads/  --  and on the first screen
tick "Add python.exe to PATH", then run this launcher again.
"@
}
Write-Host "  python: $pyExe $pyArgs" -ForegroundColor DarkGray

# --- 5. private environment ---------------------------------------------
$venvPy = "$root\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    Write-Host "  creating a private Python environment (once, ~1 min)..." -ForegroundColor Yellow
    & $pyExe @pyArgs -m venv "$root\.venv"
    if (-not (Test-Path $venvPy)) { Fail "Could not create .venv - is Python installed correctly?" }
}

# --- 6. dependencies ------------------------------------------------------
$stamp = "$root\.venv\.installed"
$reqHash = (Get-FileHash "$root\requirements.txt").Hash
$done = if (Test-Path $stamp) { (Get-Content $stamp -Raw) } else { "" }
if ("$done".Trim() -ne $reqHash) {
    Write-Host "  installing dependencies (once, 2-5 min)..." -ForegroundColor Yellow
    & $venvPy -m pip install --upgrade pip --quiet
    & $venvPy -m pip install -r "$root\requirements.txt"
    if ($LASTEXITCODE -ne 0) { Fail "Dependency install failed - scroll up for the reason." }
    # extras are best-effort: a missing one only turns off its own feature
    & $venvPy -m pip install -r "$root\requirements-optional.txt" 2>$null | Out-Null
    Set-Content $stamp $reqHash
}

# --- 7. settings ----------------------------------------------------------
if (-not (Test-Path "$root\.env") -and (Test-Path "$root\.env.example")) {
    Copy-Item "$root\.env.example" "$root\.env"
    Write-Host ""
    Write-Host "  Created .env - add a free brain key to it when you have one." -ForegroundColor Yellow
    Write-Host "  (Notepad: notepad $root\.env)" -ForegroundColor DarkGray
}

# --- 8. can it actually import? ------------------------------------------
$importOut = (& $venvPy -c "import jarvis.server" 2>&1 | Out-String)
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host $importOut -ForegroundColor DarkGray
    Fail "0.5.4.M.4 could not load. The real reason is the last line above."
}

# --- 8b. is an older copy still holding the port? -------------------------
# A server left running from an earlier attempt keeps serving its old files,
# so a fresh start silently changes nothing and the fix looks like it failed.
$busy = $null
try { $busy = Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1 } catch { }
if ($busy) {
    $owner = $null
    try { $owner = Get-CimInstance Win32_Process -Filter "ProcessId = $($busy.OwningProcess)" -ErrorAction SilentlyContinue } catch { }
    $cmd = if ($owner) { "$($owner.CommandLine)" } else { "" }
    if ($cmd -match "jarvis\.server") {
        Write-Host "  an older 0.5.4.M.4 was still running - stopping it" -ForegroundColor Yellow
        Stop-Process -Id $busy.OwningProcess -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
    } else {
        $who = if ($owner) { "$($owner.Name) (PID $($busy.OwningProcess))" } else { "PID $($busy.OwningProcess)" }
        Fail @"
Port 8080 is already taken by $who, which is not 0.5.4.M.4.

Close that program, or stop it with:
  Stop-Process -Id $($busy.OwningProcess) -Force
"@
    }
}

# --- 9. your key ----------------------------------------------------------
$envFile = Join-Path $root ".env"
if (Test-Path $envFile) {
    $envText = Get-Content $envFile -Raw
    if ($envText -match "(?m)^JARVIS_TOKEN=choose-a-long-secret") {
        ($envText -replace "(?m)^JARVIS_TOKEN=choose-a-long-secret.*$",
            "# JARVIS_TOKEN was the example placeholder - removed, a strong one is generated") |
            Set-Content $envFile
        Write-Host "  removed the placeholder token from .env - using a generated one" -ForegroundColor Yellow
    }
}
$token = & $venvPy -m jarvis.showtoken
Write-Host ""
Write-Host "  ------------------------------------------------------------"
Write-Host "   Open:  http://localhost:8080" -ForegroundColor Green
Write-Host "   Token: $token" -ForegroundColor Green
Write-Host "  ------------------------------------------------------------"
Write-Host "   Stop it with Ctrl+C." -ForegroundColor DarkGray
Write-Host "   If Windows asks about the firewall, click Allow." -ForegroundColor DarkGray
Write-Host ""

$envArgs = @()
if (Test-Path "$root\.env") { $envArgs = @("--env-file", "$root\.env") }
& $venvPy -m uvicorn jarvis.server:app --host 0.0.0.0 --port 8080 @envArgs
