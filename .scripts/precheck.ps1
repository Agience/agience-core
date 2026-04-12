[CmdletBinding()]
param(
  [switch]$DocsOnly,
  [switch]$BackendOnly,
  [switch]$ServersOnly,
  [switch]$FrontendOnly,
  [switch]$SkipDocs,
  [switch]$SkipLychee,
  [switch]$SkipBackend,
  [switch]$SkipServers,
  [switch]$SkipFrontend,
  [switch]$SkipInstall
)

$ErrorActionPreference = 'Stop'

function Write-Step([string]$Message) {
  Write-Host "\n==> $Message" -ForegroundColor Cyan
}

function Test-Command([string]$Name) {
  return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Invoke-Checked([string]$Name, [scriptblock]$Block) {
  $global:LASTEXITCODE = 0
  & $Block
  if ($global:LASTEXITCODE -ne 0) {
    throw "$Name failed with exit code $global:LASTEXITCODE"
  }
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

# If any *Only flag is set, treat others as skipped.
$anyOnly = $DocsOnly -or $BackendOnly -or $ServersOnly -or $FrontendOnly
if ($anyOnly) {
  if (-not $DocsOnly) { $SkipDocs = $true; $SkipLychee = $true }
  if (-not $BackendOnly) { $SkipBackend = $true }
  if (-not $ServersOnly) { $SkipServers = $true }
  if (-not $FrontendOnly) { $SkipFrontend = $true }
}

try {
  Set-Location $repoRoot

  if (-not $SkipDocs) {
    Write-Step 'Docs integrity (inventory + governance)'
    Invoke-Checked 'Docs integrity' { python .scripts\check_docs_integrity.py }

    if (-not $SkipLychee) {
      # CI uses lycheeverse/lychee-action in --offline mode. Locally, easiest is Docker.
      if (Test-Command 'docker') {
        Write-Step 'Docs link check (lychee --offline via Docker)'
        Invoke-Checked 'Lychee (docker)' {
          docker run --rm -v "${repoRoot}:/work" -w /work lycheeverse/lychee:latest `
            --offline --no-progress `
            --exclude-path '_archive/' `
            --exclude-path 'node_modules/' `
            --exclude-path '17-full-source-dump\.md' `
            'docs/**/*.md'
        }
      }
      elseif (Test-Command 'lychee') {
        Write-Step 'Docs link check (lychee --offline)'
        Invoke-Checked 'Lychee' { lychee --offline --no-progress --exclude-path '_archive/' --exclude-path 'node_modules/' --exclude-path '17-full-source-dump\.md' 'docs/**/*.md' }
      }
      else {
        Write-Host "Skipping lychee: install lychee or Docker to run docs link check." -ForegroundColor Yellow
        Write-Host "- Docker: https://docs.docker.com/get-docker/" -ForegroundColor Yellow
        Write-Host "- Lychee: https://github.com/lycheeverse/lychee" -ForegroundColor Yellow
      }
    }
  }

  if (-not $SkipBackend) {
    Write-Step 'Backend lint (ruff) + tests (pytest)'
    Push-Location (Join-Path $repoRoot 'backend')
    try {
      if (-not (Test-Command 'python')) {
        throw 'Python is required for backend checks.'
      }

      if (-not (Test-Command 'ruff')) {
        if ($SkipInstall) {
          throw 'ruff is not installed (run without -SkipInstall, or install ruff).' 
        }
        Write-Step 'Installing ruff (pip)'
        Invoke-Checked 'pip install ruff' { python -m pip install ruff }
      }

      Invoke-Checked 'ruff check' { ruff check . }

      if (-not $env:OPENAI_API_KEY) { $env:OPENAI_API_KEY = 'placeholder' }
      if (-not $env:JWT_SECRET_KEY) { $env:JWT_SECRET_KEY = 'placeholder' }

      Invoke-Checked 'pytest' { python -m pytest tests }
    }
    finally {
      Pop-Location
    }
  }

  if (-not $SkipServers) {
    Write-Step 'Servers lint (ruff) + tests (pytest)'
    $serversRoot = Join-Path $repoRoot 'servers'
    $serverDirs = Get-ChildItem -Directory $serversRoot | Where-Object { $_.Name -notmatch '^_' }
    foreach ($serverDir in $serverDirs) {
      Push-Location $serverDir.FullName
      try {
        Write-Host "  ruff check $($serverDir.Name)" -ForegroundColor DarkGray
        Invoke-Checked "ruff check ($($serverDir.Name))" { ruff check . }
        $testsDir = Join-Path $serverDir.FullName 'tests'
        if (Test-Path $testsDir) {
          Write-Host "  pytest $($serverDir.Name)" -ForegroundColor DarkGray
          if (-not $env:OPENAI_API_KEY) { $env:OPENAI_API_KEY = 'placeholder' }
          Invoke-Checked "pytest ($($serverDir.Name))" { python -m pytest tests }
        }
      }
      finally {
        Pop-Location
      }
    }
  }

  if (-not $SkipFrontend) {
    Write-Step 'Frontend lint (eslint) + build + tests (vitest)'
    Push-Location (Join-Path $repoRoot 'frontend')
    try {
      if (-not (Test-Command 'npm')) {
        throw 'Node/npm is required for frontend checks.'
      }

      $nodeModules = Join-Path $PWD 'node_modules'
      $hasNodeModules = Test-Path $nodeModules

      $eslintBin = Join-Path $nodeModules '.bin\eslint'
      $eslintBinCmd = Join-Path $nodeModules '.bin\eslint.cmd'
      $tscBin = Join-Path $nodeModules '.bin\tsc'
      $tscBinCmd = Join-Path $nodeModules '.bin\tsc.cmd'
      $vitestBin = Join-Path $nodeModules '.bin\vitest'
      $vitestBinCmd = Join-Path $nodeModules '.bin\vitest.cmd'
      $depsLookHealthy = (Test-Path $eslintBin) -or (Test-Path $eslintBinCmd)
      $depsLookHealthy = $depsLookHealthy -and ((Test-Path $tscBin) -or (Test-Path $tscBinCmd))
      $depsLookHealthy = $depsLookHealthy -and ((Test-Path $vitestBin) -or (Test-Path $vitestBinCmd))

      if (-not $SkipInstall) {
        # On Windows, npm ci can fail with EPERM if a native module file is locked.
        # Prefer skipping reinstall when node_modules already exists.
        if (-not $hasNodeModules) {
          if (Test-Path (Join-Path $PWD 'package-lock.json')) {
            Write-Step 'Installing frontend deps (npm ci)'
            Invoke-Checked 'npm ci' { npm ci }
          }
          else {
            Write-Step 'Installing frontend deps (npm install)'
            Invoke-Checked 'npm install' { npm install }
          }
        }
        elseif (-not $depsLookHealthy) {
          Write-Step 'Repairing frontend deps (npm install)'
          Invoke-Checked 'npm install' { npm install }
        }
        else {
          Write-Host 'Skipping npm install: node_modules already present and looks healthy.' -ForegroundColor DarkGray
        }
      }

      Invoke-Checked 'frontend lint' { npm run lint }
      Invoke-Checked 'frontend build' { npm run build }
      Invoke-Checked 'frontend test' { npm run test }
    }
    finally {
      Pop-Location
    }
  }

  Write-Step 'Precheck OK'
  exit 0
}
catch {
  Write-Host "\nPrecheck FAILED: $($_.Exception.Message)" -ForegroundColor Red
  exit 1
}
