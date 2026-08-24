$secureKey = Read-Host '请输入 OpenAI API Key（输入内容不会显示）' -AsSecureString
$keyPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)

try {
    $plainKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($keyPointer)
    if ([string]::IsNullOrWhiteSpace($plainKey)) {
        throw 'API Key 不能为空。'
    }
    if (-not $plainKey.StartsWith('sk-')) {
        throw 'API Key 格式不正确，应以 sk- 开头。'
    }

    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', $plainKey, 'User')
    [Environment]::SetEnvironmentVariable('HR_LANGCHAIN_MODEL', 'openai:gpt-5-mini', 'User')
    Write-Host '配置已保存到当前 Windows 用户环境变量。请关闭并重新打开终端，然后重启项目。' -ForegroundColor Green
}
finally {
    if ($keyPointer -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($keyPointer)
    }
    $plainKey = $null
    $secureKey = $null
}
