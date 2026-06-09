# ──────────────────────────────────────────────────────────────────────
# Agience — Unified Install Script (Windows)
#
# One shot: installs, downloads compose, pulls images, installs the
# `agience` CLI, starts the platform, and opens your browser.
#
# Modes:
#   home   — TLS via Caddy + custom domain (https://home.agience.ai).
#            Binds ports 80 + 443.
#   plain  — Bare HTTP at http://localhost:8080. No domain, no TLS.
#
# Channels:
#   stable — pulls released images (default)
#   edge   — pulls latest main-branch builds (VERSION=edge)
#
# Source: https://github.com/Agience/agience-core/blob/main/package/install/install.ps1
#
# Usage:
#   irm https://get.agience.ai/install.ps1 | iex
#   .\install.ps1 -Mode home -Channel stable
#   .\install.ps1 -Mode plain -Channel edge
#
# After install:
#   agience up      start
#   agience down    stop
# ──────────────────────────────────────────────────────────────────────
#Requires -Version 5.1
[CmdletBinding()]
param(
    [ValidateSet('home', 'plain')]
    [string]$Mode = 'home',

    [ValidateSet('stable', 'edge')]
    [string]$Channel = 'stable',

    [string]$DataPath = ''
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ── Mode-dependent configuration ─────────────────────────────────────

$RepoRaw    = 'https://raw.githubusercontent.com/Agience/agience-core/main/package/install'
$ComposeUrl = "$RepoRaw/$Mode/docker-compose.yml"
$InstallDir = if ($DataPath) { $DataPath } else { Join-Path $env:USERPROFILE '.agience' }
$BinDir     = Join-Path $env:USERPROFILE '.agience\bin'

if ($Mode -eq 'home') {
    $OpenUrl       = 'https://home.agience.ai'
    $RequiredPorts = @(80, 443)
    $BannerLabel   = 'Agience -- Install (home)'
    $BannerDomain  = 'home.agience.ai'
} else {
    $OpenUrl       = 'http://localhost:8080'
    $RequiredPorts = @(8080)
    $BannerLabel   = 'Agience -- Install (plain)'
    $BannerDomain  = 'http://localhost:8080'
}

if ($Channel -eq 'edge') {
    $BannerLabel = "$BannerLabel [edge]"
}

# ── Helpers ──────────────────────────────────────────────────────────

function Write-Info { Write-Host "  [info]   $args" -ForegroundColor Cyan }
function Write-Ok   { Write-Host "  [ok]     $args" -ForegroundColor Green }
function Write-Warn { Write-Host "  [warn]   $args" -ForegroundColor Yellow }
function Write-Fail { Write-Host "  [error]  $args" -ForegroundColor Red; exit 1 }

function Test-Command { param($Name); return [bool](Get-Command $Name -ErrorAction SilentlyContinue) }

function Add-ToUserPath {
    param([string]$Dir)
    $current = [Environment]::GetEnvironmentVariable('PATH', 'User')
    if ($current -notlike "*$Dir*") {
        [Environment]::SetEnvironmentVariable('PATH', "$current;$Dir", 'User')
        $env:PATH = "$env:PATH;$Dir"
        return $true
    }
    return $false
}

# ── Banner ───────────────────────────────────────────────────────────

Write-Host ''
Write-Host '  +--------------------------------------+' -ForegroundColor Magenta
Write-Host "  |  $BannerLabel" -ForegroundColor Magenta
Write-Host "  |  $BannerDomain" -ForegroundColor Magenta
Write-Host '  +--------------------------------------+' -ForegroundColor Magenta
Write-Host ''

# ── Step 1: Check Docker ─────────────────────────────────────────────

Write-Info "Checking for Docker (mode=$Mode channel=$Channel)..."

if (-not (Test-Command 'docker')) {
    Write-Fail @"
Docker Desktop is not installed or not on PATH.

  Install Docker Desktop for Windows:
  https://www.docker.com/products/docker-desktop/

  After installing, start Docker Desktop and run this script again.
"@
}

try {
    docker info 2>&1 | Out-Null
} catch {
    Write-Fail 'Docker is installed but not running. Start Docker Desktop and try again.'
}

if (-not (docker compose version 2>&1 | Select-String 'version')) {
    Write-Fail 'Docker Compose V2 not found. Update Docker Desktop to a recent version.'
}

Write-Ok 'Docker is installed and running'

# ── Step 2: Check Port Conflicts ─────────────────────────────────────

Write-Info ("Checking port conflicts on: " + ($RequiredPorts -join ', '))

$conflicts = @()
foreach ($port in $RequiredPorts) {
    $used = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($used) { $conflicts += $port }
}

if ($conflicts.Count -gt 0) {
    Write-Fail @"
Required port(s) already in use: $($conflicts -join ', ')

  Stop the service using these ports and re-run the installer.
  See what's using a port:    Get-NetTCPConnection -LocalPort <port> -State Listen | Select-Object -ExpandProperty OwningProcess | ForEach-Object { Get-Process -Id `$_ }

  Or install in plain mode (HTTP at localhost:8080) instead:
    .\install.ps1 -Mode plain
"@
}
Write-Ok ("Required ports ($($RequiredPorts -join ', ')) are available")

# ── Step 3: Create Install Directory ─────────────────────────────────

Write-Info "Install directory: $InstallDir"

$composeFile = Join-Path $InstallDir 'docker-compose.yml'
$isUpdate    = (Test-Path $composeFile)

New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
New-Item -ItemType Directory -Path $BinDir     -Force | Out-Null

if ($isUpdate) {
    Write-Warn 'Existing installation found -- updating and restarting'
} else {
    Write-Ok "Created $InstallDir"
}

# ── Step 4: Download Compose File ────────────────────────────────────

Write-Info "Downloading compose configuration ($Mode)..."

Invoke-WebRequest -Uri $ComposeUrl -OutFile $composeFile -UseBasicParsing

if ((Get-Item $composeFile).Length -eq 0) {
    Write-Fail 'Downloaded compose file is empty. Check your network and try again.'
}

Write-Ok 'Compose file downloaded'

# ── Step 4b: Set release channel ─────────────────────────────────────

$envFile = Join-Path $InstallDir '.env'
if ($Channel -eq 'edge') {
    $envLines = @()
    if (Test-Path $envFile) {
        $envLines = (Get-Content $envFile) | Where-Object { $_ -notmatch '^VERSION=' }
    }
    $envLines += 'VERSION=edge'
    Set-Content -Path $envFile -Value $envLines -Encoding ASCII
    Write-Ok 'Channel: edge'
} else {
    if (Test-Path $envFile) {
        $envLines = (Get-Content $envFile) | Where-Object { $_ -notmatch '^VERSION=' }
        if ($envLines.Count -gt 0) {
            Set-Content -Path $envFile -Value $envLines -Encoding ASCII
        } else {
            Remove-Item $envFile -Force
        }
    }
    Write-Ok 'Channel: stable'
}

# ── Step 5: Pull Images ──────────────────────────────────────────────

Write-Info 'Pulling container images (this may take a few minutes)...'
Write-Host ''

Push-Location $InstallDir
$pullOk = $false
foreach ($attempt in 1..3) {
    docker compose pull
    if ($LASTEXITCODE -eq 0) {
        $pullOk = $true
        break
    }
    if ($attempt -lt 3) {
        $delay = $attempt * 5
        Write-Warn "Image pull failed (attempt $attempt/3). Retrying in ${delay}s..."
        Start-Sleep -Seconds $delay
    }
}
Pop-Location

if (-not $pullOk) {
    Write-Fail @"
Failed to pull container images after 3 attempts.

  Common causes:
    - Network connectivity / Docker Hub unreachable.
    - Tag does not exist (check VERSION in $envFile or .env).
    - Behind a proxy: set HTTP_PROXY / HTTPS_PROXY before re-running.

  Try: docker compose pull
"@
}

Write-Host ''
Write-Ok 'All images pulled'

# ── Step 6: Install agience.bat ──────────────────────────────────────

Write-Info 'Installing agience command...'

$batPath = Join-Path $BinDir 'agience.bat'

$bat = @"
@echo off
setlocal enabledelayedexpansion
set AGIENCE_DIR=%USERPROFILE%\.agience
set OPEN_URL=$OpenUrl
if not exist "%AGIENCE_DIR%\docker-compose.yml" (
    echo Agience not found at %AGIENCE_DIR%. Re-run the installer.
    exit /b 1
)
cd /d "%AGIENCE_DIR%"

set CMD=%1
if "%CMD%"==""           goto do_help
if "%CMD%"=="-h"         goto do_help
if "%CMD%"=="--help"     goto do_help
if "%CMD%"=="help"       goto do_help
if "%CMD%"=="up"          goto do_up
if "%CMD%"=="down"        goto do_down
if "%CMD%"=="logs"        goto do_logs
if "%CMD%"=="update"      goto do_update
if "%CMD%"=="status"      goto do_status
if "%CMD%"=="open"        goto do_open
if "%CMD%"=="setup-token" goto do_setup_token
if "%CMD%"=="reset"       goto do_reset
if "%CMD%"=="version"     goto do_version
if "%CMD%"=="--version"   goto do_version
if "%CMD%"=="-v"          goto do_version
echo Unknown command: %CMD%
echo.
goto do_help

:require_docker
where docker >nul 2>&1
if errorlevel 1 (
    echo Docker is not installed. Install Docker Desktop and try again.
    exit /b 1
)
docker info >nul 2>&1
if errorlevel 1 (
    echo Docker is installed but not running. Start Docker Desktop and try again.
    exit /b 1
)
exit /b 0

:do_up
call :require_docker || exit /b 1
docker compose up -d
echo.
echo Agience is running. Open: %OPEN_URL%
goto done

:do_down
call :require_docker || exit /b 1
docker compose down
goto done

:do_logs
call :require_docker || exit /b 1
shift
docker compose logs -f %1 %2 %3 %4 %5
goto done

:do_update
call :require_docker || exit /b 1
docker compose pull
docker compose up -d
echo.
echo Updated. Open: %OPEN_URL%
goto done

:do_status
call :require_docker || exit /b 1
docker compose ps
goto done

:do_open
start "" %OPEN_URL%
goto done

:do_setup_token
set TOKEN_FILE=%AGIENCE_DIR%\.data\keys\setup.token
if exist "%TOKEN_FILE%" (
    type "%TOKEN_FILE%"
) else (
    echo No setup token at %TOKEN_FILE%. Setup may already be complete.
    exit /b 1
)
goto done

:do_reset
call :require_docker || exit /b 1
echo This will STOP Agience and DELETE all data at %AGIENCE_DIR%\.data\
echo A timestamped backup will be made at %AGIENCE_DIR%\.data.backup-^<ts^>
set /p CONFIRM=Type 'reset' to continue:
if not "!CONFIRM!"=="reset" (
    echo Cancelled.
    exit /b 1
)
docker compose down -v >nul 2>&1
if exist "%AGIENCE_DIR%\.data" (
    for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set DT=%%I
    set TS=!DT:~0,8!-!DT:~8,6!
    move "%AGIENCE_DIR%\.data" "%AGIENCE_DIR%\.data.backup-!TS!" >nul
    echo Backed up old data to %AGIENCE_DIR%\.data.backup-!TS!
)
echo Reset complete. Run 'agience up' to start fresh.
goto done

:do_version
if exist "%AGIENCE_DIR%\.env" (
    findstr /b "VERSION=" "%AGIENCE_DIR%\.env"
    if errorlevel 1 echo VERSION=stable ^(default^)
) else (
    echo VERSION=stable ^(default^)
)
goto done

:do_help
echo Usage: agience ^<command^>
echo.
echo Commands:
echo   up            Start Agience.
echo   down          Stop Agience.
echo   logs [svc]    Tail logs (optionally for one service).
echo   update        Pull latest images and restart.
echo   status        Show running containers.
echo   open          Open Agience in your browser.
echo   setup-token   Print the first-boot setup token (if not yet consumed).
echo   reset         Stop + back up data dir + start fresh.
echo   version       Show the configured channel/version.
echo.
echo URL: %OPEN_URL%
exit /b 1

:done
endlocal
"@

Set-Content -Path $batPath -Value $bat -Encoding ASCII

Write-Ok "agience.bat installed to $BinDir"

$pathUpdated = Add-ToUserPath $BinDir

# ── Step 7: Start ────────────────────────────────────────────────────

Write-Info 'Starting Agience...'

Push-Location $InstallDir
docker compose up -d
Pop-Location

Write-Ok 'Agience is running'

# ── Read setup token ─────────────────────────────────────────────────

$tokenFile = Join-Path $InstallDir '.data\keys\setup.token'
$SetupToken = if (Test-Path $tokenFile) { (Get-Content $tokenFile -Raw).Trim() } else { '' }

# ── Step 8: Open browser ─────────────────────────────────────────────

Start-Process $OpenUrl

# ── Done ─────────────────────────────────────────────────────────────

Write-Host ''
Write-Host '  +--------------------------------------+' -ForegroundColor Green
Write-Host '  |     Agience is running!              |' -ForegroundColor Green
Write-Host '  +--------------------------------------+' -ForegroundColor Green
Write-Host ''
Write-Host "  Open:     $OpenUrl" -ForegroundColor White
Write-Host "  Mode:     $Mode" -ForegroundColor Gray
Write-Host "  Channel:  $Channel" -ForegroundColor Gray
Write-Host "  Data:     $InstallDir\.data\" -ForegroundColor Gray
Write-Host ''
if ($SetupToken) {
    Write-Host "  Setup:    $SetupToken" -ForegroundColor Yellow
    Write-Host ''
}
Write-Host '  Commands:' -ForegroundColor White
Write-Host '    agience up           start'
Write-Host '    agience down         stop'
Write-Host '    agience logs [svc]   tail logs'
Write-Host '    agience update       pull latest images and restart'
Write-Host '    agience status       show running containers'
Write-Host '    agience open         open Agience in your browser'
Write-Host '    agience setup-token  print first-boot setup token'
Write-Host '    agience reset        back up data dir + start fresh'
Write-Host '    agience version      show configured channel/version'
Write-Host ''

if ($pathUpdated) {
    Write-Host "  Note: Open a new terminal for 'agience' to be on your PATH." -ForegroundColor Yellow
    Write-Host ''
}
