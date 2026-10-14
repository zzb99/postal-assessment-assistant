param(
    [int]$Port = 8080,
    [switch]$Rebuild,
    [switch]$RepositoryImages
)

$ErrorActionPreference = "Stop"
$env:COMPOSE_BAKE = "false"
$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeEnv = Join-Path $PSScriptRoot ".env.runtime"
$linkBase = Join-Path $env:USERPROFILE ".codex\deployment-links"
$deploymentRoot = Join-Path $linkBase "postal-assessment"

if (-not (Test-Path -LiteralPath $deploymentRoot)) {
    New-Item -ItemType Directory -Force -Path $linkBase | Out-Null
    New-Item -ItemType Junction -Path $deploymentRoot -Target $projectRoot | Out-Null
}
$resolvedTarget = (Get-Item -LiteralPath $deploymentRoot).Target
if ($resolvedTarget -ne $projectRoot) {
    throw "Deployment junction points to an unexpected workspace: $resolvedTarget"
}

function New-RandomSecret([int]$Bytes = 32) {
    $buffer = New-Object byte[] $Bytes
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($buffer) } finally { $generator.Dispose() }
    return [Convert]::ToBase64String($buffer).Replace("+", "A").Replace("/", "B").TrimEnd("=")
}

if (-not (Test-Path -LiteralPath $runtimeEnv)) {
    $databasePassword = New-RandomSecret 24
    $jwtSecret = New-RandomSecret 48
    $adminPassword = "Adm!" + (New-RandomSecret 18)
    @(
        "ASSESSMENT_DB_PASSWORD=$databasePassword"
        "ASSESSMENT_JWT_SECRET=$jwtSecret"
        "ASSESSMENT_ADMIN_USERNAME=admin"
        "ASSESSMENT_ADMIN_PASSWORD=$adminPassword"
        "ASSESSMENT_ADMIN_DISPLAY_NAME=System Administrator"
        "ASSESSMENT_PORT=$Port"
    ) | Set-Content -LiteralPath $runtimeEnv -Encoding ASCII
    Write-Host "Generated local deployment credentials: $runtimeEnv"
}

$composeFiles = @("-f", "compose.yaml")
if ($RepositoryImages) {
    $composeFiles += @("-f", "compose.repository.yaml")
}
$arguments = @("compose", "--env-file", $runtimeEnv) + $composeFiles + @("up", "-d")
if ($Rebuild) { $arguments += "--build" }
if ($RepositoryImages) { $arguments += @("--pull", "never") }
Push-Location $deploymentRoot
try {
    if ($RepositoryImages) {
        & docker compose --env-file $runtimeEnv @composeFiles pull api web
        if ($LASTEXITCODE -ne 0) { throw "Unable to pull repository images." }
        & docker image inspect postgres:16-alpine *> $null
        if ($LASTEXITCODE -ne 0) {
            & docker pull postgres:16-alpine
            if ($LASTEXITCODE -ne 0) {
                & docker pull m.daocloud.io/docker.io/library/postgres:16-alpine
                if ($LASTEXITCODE -ne 0) { throw "Unable to pull the PostgreSQL image." }
                & docker tag m.daocloud.io/docker.io/library/postgres:16-alpine postgres:16-alpine
                if ($LASTEXITCODE -ne 0) { throw "Unable to tag the PostgreSQL mirror image." }
            }
        }
    }
    & docker @arguments
    if ($LASTEXITCODE -ne 0) { throw "Docker Compose deployment failed." }
    & docker compose --env-file $runtimeEnv @composeFiles ps
    if ($LASTEXITCODE -ne 0) { throw "Unable to read container status." }
} finally {
    Pop-Location
}

Write-Host "System URL: http://127.0.0.1:$Port"
Write-Host "Administrator username: admin; password is stored in $runtimeEnv"
