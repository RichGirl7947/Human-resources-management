$secureKey = Read-Host '请输入全新的百炼 API Key（输入内容不会显示）' -AsSecureString
$keyPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)

try {
    $plainKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($keyPointer)
    if ([string]::IsNullOrWhiteSpace($plainKey)) {
        throw 'API Key 不能为空。'
    }
    if (-not $plainKey.StartsWith('sk-')) {
        throw '百炼 API Key 格式不正确，应以 sk- 开头。'
    }

    [Environment]::SetEnvironmentVariable('DASHSCOPE_API_KEY', $plainKey.Trim(), 'User')
    [Environment]::SetEnvironmentVariable('HR_LLM_PROVIDER', 'bailian', 'User')
    [Environment]::SetEnvironmentVariable('HR_LANGCHAIN_MODEL', 'qwen-flash', 'User')
    [Environment]::SetEnvironmentVariable(
        'HR_LANGCHAIN_BASE_URL',
        'https://dashscope.aliyuncs.com/compatible-mode/v1',
        'User'
    )
    Write-Host '百炼配置已保存到当前 Windows 用户环境变量。' -ForegroundColor Green
    Write-Host '请关闭此窗口；服务重启后生效。' -ForegroundColor Green
}
finally {
    if ($keyPointer -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($keyPointer)
    }
    $plainKey = $null
    $secureKey = $null
}
