# 0.5.4.M.4 — get it and run it, from anywhere. Windows.
#
#   iwr -useb https://raw.githubusercontent.com/originalpineapples22-hub/J.A.R.V.I.S/claude/jarvis-self-learning-pfsxu0/deploy/bootstrap.ps1 | iex
#
# Puts the code in %USERPROFILE%\jarvis-v3 (updating it if already there),
# then hands over to start.ps1. Never touches the folder you happen to be in.

$ErrorActionPreference = "Continue"
if (Get-Variable PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $false
}

$branch = "claude/jarvis-self-learning-pfsxu0"
$repo   = "https://github.com/originalpineapples22-hub/J.A.R.V.I.S.git"
$dest   = Join-Path $env:USERPROFILE "jarvis-v3"

function Fail($msg) {
    Write-Host ""
    Write-Host "  X  $msg" -ForegroundColor Red
    Write-Host ""
    exit 1
}

Write-Host ""
Write-Host "  0.5.4.M.4  --  setting up in $dest" -ForegroundColor Cyan
Write-Host ""

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Fail @"
Git is not installed.

Install it (one command, then reopen PowerShell):
  winget install --id Git.Git -e

Or download it from https://git-scm.com/download/win
"@
}

if (Test-Path (Join-Path $dest ".git")) {
    Write-Host "  already there - updating..." -ForegroundColor Yellow
    Set-Location $dest
    git fetch origin $branch
    if ($LASTEXITCODE -ne 0) { Fail "Could not reach GitHub. Check your internet connection." }
    git checkout $branch
    git pull origin $branch
    if ($LASTEXITCODE -ne 0) {
        Fail @"
Update failed - you probably have local edits in $dest.

Keep them:     cd $dest ; git stash ; git pull origin $branch
Or start over: Remove-Item -Recurse -Force '$dest'  then run this again.
"@
    }
} else {
    if (Test-Path $dest) {
        Fail @"
$dest already exists but is not a git checkout.

Rename or delete it, then run this again:
  Remove-Item -Recurse -Force '$dest'
"@
    }
    Write-Host "  downloading the code..." -ForegroundColor Yellow
    git clone -b $branch $repo $dest
    if ($LASTEXITCODE -ne 0) { Fail "Download failed. Check your internet connection and try again." }
    Set-Location $dest
}

$start = Join-Path $dest "start.ps1"
if (-not (Test-Path $start)) { Fail "start.ps1 is missing from $dest - the download did not finish." }

Write-Host ""
Write-Host "  handing over to start.ps1" -ForegroundColor Cyan
Write-Host "  (next time, just: cd $dest  then  .\start.ps1)" -ForegroundColor DarkGray
& $start
