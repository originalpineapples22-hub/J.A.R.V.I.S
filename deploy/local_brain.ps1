# 0.5.4.M.4 — install a brain that is yours. Windows.
#
#   .\deploy\local_brain.ps1
#
# Installs Ollama and pulls a model sized to this PC. After this the assistant
# thinks on your own hardware: no key, no quota, no account, works offline, and
# nobody can retire it. The cloud pool stays as backup for when the PC is off.

$ErrorActionPreference = "Continue"
if (Get-Variable PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $false
}

function Say($m, $c = "Gray") { Write-Host "  $m" -ForegroundColor $c }

Write-Host ""
Write-Host "  0.5.4.M.4  --  installing your own brain" -ForegroundColor Cyan
Write-Host ""

# --- what can this machine actually run? ---------------------------------
$ramGB = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)
$vram = 0
try {
    $gpu = Get-CimInstance Win32_VideoController | Sort-Object AdapterRAM -Descending | Select-Object -First 1
    if ($gpu -and $gpu.AdapterRAM -gt 0) { $vram = [math]::Round($gpu.AdapterRAM / 1GB) }
} catch { }
Say "memory: ${ramGB} GB RAM, ${vram} GB video memory"

# Sized so it answers at a usable speed rather than the largest that fits.
if     ($ramGB -ge 32) { $model = "qwen2.5-coder:14b"; $size = "9 GB" }
elseif ($ramGB -ge 16) { $model = "qwen2.5-coder:7b";  $size = "4.7 GB" }
elseif ($ramGB -ge 8)  { $model = "qwen2.5:3b";        $size = "1.9 GB" }
else                   { $model = "qwen2.5:1.5b";      $size = "1 GB" }
Say "chosen: $model  (about $size to download)" "Green"
Write-Host ""

# --- Ollama ---------------------------------------------------------------
if (Get-Command ollama -ErrorAction SilentlyContinue) {
    Say "ollama: already installed"
} else {
    Say "installing ollama..." "Yellow"
    winget install --id Ollama.Ollama -e --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Say "Could not install automatically." "Red"
        Say "Download it from https://ollama.com/download, then run this again."
        Read-Host "Press Enter to close"; exit 1
    }
    $env:Path = "$env:Path;$env:LOCALAPPDATA\Programs\Ollama"
}

if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Say "Ollama installed, but this window cannot see it yet." "Yellow"
    Say "Close PowerShell, open it again, and run this script once more."
    Read-Host "Press Enter to close"; exit 0
}

# --- the model ------------------------------------------------------------
Write-Host ""
Say "downloading $model - this is the only big download, and it is once." "Yellow"
ollama pull $model
if ($LASTEXITCODE -ne 0) { Say "Download failed - check your connection and run this again." "Red"; Read-Host "Press Enter"; exit 1 }

# --- prove it thinks ------------------------------------------------------
Write-Host ""
Say "testing..." "Yellow"
$reply = (ollama run $model "Reply with exactly: online" 2>&1) -join " "
Say "it said: $reply" "Green"

# --- point the assistant at it -------------------------------------------
$settings = Join-Path (Split-Path -Parent $PSScriptRoot) "data\settings.json"
$cfg = @{}
if (Test-Path $settings) {
    try { (Get-Content $settings -Raw | ConvertFrom-Json).PSObject.Properties | ForEach-Object { $cfg[$_.Name] = $_.Value } } catch { }
}
$cfg["use_ollama"] = $true
$cfg["prefer_local"] = $true
$cfg["ollama_model"] = $model
$cfg["ollama_url"] = "http://localhost:11434"
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $settings) | Out-Null
$cfg | ConvertTo-Json -Depth 6 | Set-Content $settings -Encoding UTF8

Write-Host ""
Write-Host "  ------------------------------------------------------------"
Write-Host "   Your brain is installed and set as first choice." -ForegroundColor Green
Write-Host "   $model, running on this PC. No key, no quota, works offline." -ForegroundColor Green
Write-Host "  ------------------------------------------------------------"
Say "Restart it with BOOT.bat, then ask: which brain are you using?"
Write-Host ""
