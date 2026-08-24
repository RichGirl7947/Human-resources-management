$ErrorActionPreference = "Stop"

function New-RandomSecret([int]$Bytes = 48) {
    $buffer = New-Object byte[] $Bytes
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($buffer)
    return [Convert]::ToBase64String($buffer)
}

$jwtSecret = [Environment]::GetEnvironmentVariable("HR_JWT_SECRET", "User")
if (-not $jwtSecret) {
    [Environment]::SetEnvironmentVariable("HR_JWT_SECRET", (New-RandomSecret), "User")
}

$encryptionKey = [Environment]::GetEnvironmentVariable("HR_DATA_ENCRYPTION_KEY", "User")
if (-not $encryptionKey) {
    $keyBytes = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($keyBytes)
    $fernetKey = [Convert]::ToBase64String($keyBytes).Replace("+", "-").Replace("/", "_")
    [Environment]::SetEnvironmentVariable("HR_DATA_ENCRYPTION_KEY", $fernetKey, "User")
}

[Environment]::SetEnvironmentVariable("HR_AUTH_REQUIRED", "true", "User")
Write-Host "安全配置已保存到当前 Windows 用户环境变量。请重启服务使配置生效。"
