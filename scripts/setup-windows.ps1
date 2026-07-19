$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw 'Python was not found in PATH.'
}

if (-not (Test-Path '.venv')) {
    python -m venv .venv
}

$Python = Join-Path $Root '.venv\Scripts\python.exe'
& $Python -m pip install --upgrade pip
& $Python -m pip install -e '.[dev]'
& $Python -m pytest

Write-Host ''
Write-Host 'OrbisStudio is ready.' -ForegroundColor Green
Write-Host "Activate with: $Root\.venv\Scripts\Activate.ps1"
Write-Host 'Run help with: orbis --help'
