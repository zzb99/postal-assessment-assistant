$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$privateConfig = Join-Path $projectRoot '.tmp/local-preview/deepseek.env'
if (Test-Path -LiteralPath $privateConfig) {
    foreach ($line in [IO.File]::ReadAllLines($privateConfig)) {
        if ($line -match '^(DEEPSEEK_API_KEY|DEEPSEEK_MODEL)=(.*)$') {
            [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2].Trim(), 'Process')
        }
    }
}
$env:DATABASE_URL = 'sqlite:///' + ($projectRoot.Replace('\', '/') + '/.tmp/local-preview/assessment.db')
$env:DOCUMENT_ROOT = Join-Path $projectRoot '.tmp/local-preview/documents'
$env:LIBREOFFICE_BINARY = Join-Path $projectRoot '.tmp/libreoffice-runtime/program/soffice.com'
if (-not $env:JWT_SECRET) {
    $jwtBytes = New-Object byte[] 48
    $randomSource = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $randomSource.GetBytes($jwtBytes) } finally { $randomSource.Dispose() }
    $env:JWT_SECRET = [Convert]::ToBase64String($jwtBytes)
}
& (Join-Path $projectRoot 'backend/.venv/Scripts/python.exe') -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --workers 1
exit $LASTEXITCODE
