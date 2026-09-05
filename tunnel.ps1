# 0.5.4.M.4 — give the local server a public HTTPS address, for Windows.
#
# Run start.ps1 in one PowerShell window, then this one in a second:
#   .\tunnel.ps1
#
# If Windows says "running scripts is disabled on this system", use:
#   powershell -ExecutionPolicy Bypass -File .\tunnel.ps1
#
# It fetches cloudflared the first time (about 20 MB, no account, no card),
# keeps it in .bin\ next to this file, and prints your https://... address.

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

$port = 8080

Write-Host ""
Write-Host "  0.5.4.M.4  --  opening a public address" -ForegroundColor Cyan
Write-Host ""

# --- 1. is the server actually up? ---------------------------------------
# Wait rather than fail: BOOT.bat starts both windows at once, and the core
# needs a minute the first time while it installs.
$up = $false
$waited = 0
while (-not $up -and $waited -lt 300) {
    try {
        $c = New-Object System.Net.Sockets.TcpClient
        $c.Connect("127.0.0.1", $port); $up = $c.Connected; $c.Close()
    } catch { }
    if (-not $up) {
        if ($waited -eq 0) { Write-Host "  waiting for the core to come up..." -ForegroundColor Yellow }
        Start-Sleep -Seconds 3; $waited += 3
    }
}
if (-not $up) {
    Fail @"
The core never came up on port $port (waited five minutes).

Look at the other window - the one running start.ps1 - and see what it says.
That is where the real error will be.
"@
}
Write-Host "  server: running on port $port" -ForegroundColor DarkGray

# --- 2. cloudflared ------------------------------------------------------
$exe = $null
if (Get-Command cloudflared -ErrorAction SilentlyContinue) {
    $exe = "cloudflared"
} else {
    $bin = Join-Path $root ".bin"
    $local = Join-Path $bin "cloudflared.exe"
    if (-not (Test-Path $local)) {
        New-Item -ItemType Directory -Force -Path $bin | Out-Null
        $arch = switch ($env:PROCESSOR_ARCHITECTURE) {
            "AMD64" { "amd64" }
            "ARM64" { "arm64" }
            default { "386" }
        }
        $url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-$arch.exe"
        Write-Host "  downloading cloudflared (once, ~20 MB)..." -ForegroundColor Yellow
        try {
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            Invoke-WebRequest -Uri $url -OutFile $local -UseBasicParsing
        } catch {
            Fail @"
Could not download cloudflared: $($_.Exception.Message)

Install it by hand instead - either
  winget install --id Cloudflare.cloudflared
or download $url
and save it as
  $local
then run this again.
"@
        }
    }
    if (-not (Test-Path $local)) { Fail "cloudflared did not download. Try: winget install --id Cloudflare.cloudflared" }
    $exe = $local
}
Write-Host "  cloudflared: $exe" -ForegroundColor DarkGray

# --- 3. run it -----------------------------------------------------------
Write-Host ""
Write-Host "  Watch for a line like  https://something.trycloudflare.com" -ForegroundColor Green
Write-Host "  Open that on your iPhone and paste your token. Ctrl+C to stop." -ForegroundColor DarkGray
Write-Host "  The address changes every time you restart this." -ForegroundColor DarkGray
Write-Host ""

& $exe tunnel --url "http://localhost:$port"
