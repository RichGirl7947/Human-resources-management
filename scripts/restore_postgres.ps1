param(
    [Parameter(Mandatory = $true)]
    [string]$BackupFile,
    [switch]$ConfirmRestore
)

$ErrorActionPreference = "Stop"
if (-not $ConfirmRestore) {
    throw "恢复会覆盖当前数据库，请明确添加 -ConfirmRestore"
}
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$resolvedBackup = (Resolve-Path -LiteralPath $BackupFile).Path
$backupRoot = [System.IO.Path]::GetFullPath((Join-Path $projectRoot "backups"))
if (-not $resolvedBackup.StartsWith($backupRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "仅允许恢复项目 backups 目录内的文件"
}
$fileName = Split-Path -Leaf $resolvedBackup

Push-Location $projectRoot
try {
    docker compose --env-file .env.production --profile tools run --rm db-tools `
        sh -c 'pg_restore --clean --if-exists --no-owner --no-acl --dbname="$PGDATABASE" "/backups/$1"' sh $fileName
    if ($LASTEXITCODE -ne 0) { throw "PostgreSQL 恢复失败" }
    Write-Host "数据库恢复完成"
} finally {
    Pop-Location
}
