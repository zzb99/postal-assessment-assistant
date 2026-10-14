# Isolated loopback acceptance database. Never opens the previous preview or production data.
param([string]$LibreOfficeBinary = $env:LIBREOFFICE_BINARY)
$ErrorActionPreference = 'Stop'
$acceptanceRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $acceptanceRoot
New-Item -ItemType Directory -Path '.tmp/acceptance/documents' -Force | Out-Null
$env:DATABASE_URL = 'sqlite:///' + ($acceptanceRoot.Replace('\','/') + '/.tmp/acceptance/database.sqlite')
$env:DOCUMENT_ROOT = Join-Path $acceptanceRoot '.tmp/acceptance/documents'
$env:LIBREOFFICE_BINARY = if ($LibreOfficeBinary) { $LibreOfficeBinary } else { 'soffice' }
$env:JWT_SECRET = 'synthetic-acceptance-only-loopback-secret-20261014-not-production'
$env:BOOTSTRAP_ADMIN_USERNAME = 'qa-admin'
$env:BOOTSTRAP_ADMIN_PASSWORD = 'SyntheticAcceptanceOnly2026!'
$env:BOOTSTRAP_ADMIN_DISPLAY_NAME = '本机验收管理员'
$env:DEEPSEEK_API_KEY = ''
$env:PYTHONIOENCODING = 'utf-8'
& ./.venv/Scripts/python.exe -m backend.app.bootstrap
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& ./.venv/Scripts/python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 18020 --workers 1
