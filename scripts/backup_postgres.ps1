param(
    [string]$OutputDirectory = "backups"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$backupRoot = [System.IO.Path]::GetFullPath((Join-Path $projectRoot $OutputDirectory))
if (-not $backupRoot.StartsWith($projectRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "备份目录必须位于项目目录内"
}
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null
$fileName = "hr_agent_{0}.dump" -f (Get-Date -Format "yyyyMMdd_HHmmss")
$containerPath = "/backups/$fileName"

Push-Location $projectRoot
try {
    docker compose --env-file .env.production --profile tools run --rm db-tools `
        pg_dump --format=custom --no-owner --no-acl --file=$containerPath
    if ($LASTEXITCODE -ne 0) { throw "PostgreSQL 备份失败" }
    Write-Host "备份已创建：$(Join-Path $backupRoot $fileName)"
} finally {
    Pop-Location
}
