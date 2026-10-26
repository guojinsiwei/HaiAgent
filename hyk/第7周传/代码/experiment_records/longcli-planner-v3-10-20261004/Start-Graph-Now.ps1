$ErrorActionPreference='Stop'
$Host.UI.RawUI.WindowTitle='Graph Search 10 tasks - ENTER DEEPSEEK KEY HERE'
Write-Host 'This window starts the graph-search experiment (not DH / RAW).' -ForegroundColor Cyan
Write-Host 'Enter the DeepSeek key at the hidden prompt below. Do not send it in chat.'
try {
    & (Join-Path $PSScriptRoot 'Start-PlannerV3-10.ps1')
} catch {
    Write-Host ('Launch did not complete: '+$_.Exception.Message) -ForegroundColor Red
    @{state='needs_attention';message=$_.Exception.Message;updated=(Get-Date).ToString('o')} |
        ConvertTo-Json | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'interactive-launch-error.json') -Encoding UTF8
}
