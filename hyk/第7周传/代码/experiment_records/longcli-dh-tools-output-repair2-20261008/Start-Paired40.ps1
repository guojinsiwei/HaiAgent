$ErrorActionPreference='Stop'
$Host.UI.RawUI.WindowTitle='DH paired40 REPAIR1 - fresh20 + fresh20 - secure API input - NO EMAIL'
$pairedCampaign='/mnt/sdb/home/lizh639/longcli-dh-tools-ablation40-repair1-20261008'
$pairedPython='/mnt/sdb/home/lizh639/terminalbench-v14-setup/runtime/bin/python'
$pairedSshKey='C:/Users/54177/.ssh/cubestudio_notebook'
$pairedHost='lizh639@172.16.108.236'
try {
    Write-Host 'FRESH 20 + 20 tasks. Both arms: subgoals + local correction, reconnaissance, critic and rollback.'
    Write-Host 'Only difference: inspect_code / edit_code / verify_goal available vs unavailable.'
    Write-Host 'SMALL budget: 800 API / 600 tools / 2h; 4096 output / 48000 input bytes per task.'
    Write-Host 'Same college Docker: 2 CPUs / 8GiB; total12 concurrent, max6 per arm. NO EMAIL.'
    & ssh -n -i $pairedSshKey -o BatchMode=yes -o ConnectTimeout=15 $pairedHost "$pairedPython -B $pairedCampaign/launch.py --check"
    if ($LASTEXITCODE -ne 0) { throw 'Readiness failed. Do not start or re-enter credentials.' }
    $pairedSecret=Read-Host 'NEW DeepSeek API key (hidden; do not send in chat)' -AsSecureString
    $pairedPointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($pairedSecret)
    try {
        $pairedPlain=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($pairedPointer).Trim()
        if (-not $pairedPlain -or $pairedPlain -match '\s') { throw 'Credential empty or contains whitespace.' }
        $pairedPlain | & ssh -i $pairedSshKey -o BatchMode=yes -o ConnectTimeout=15 $pairedHost "$pairedPython -B $pairedCampaign/launch.py"
        if ($LASTEXITCODE -ne 0) { throw 'Launch uncertain; inspect public status before retrying.' }
        Write-Host 'Fresh40 started. Each arm first runs one pilot, then expands automatically.' -ForegroundColor Green
    } finally {
        $pairedPlain=$null
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pairedPointer)
        $pairedSecret.Dispose()
    }
} catch { Write-Host $_.Exception.Message -ForegroundColor Red }
Read-Host 'Press Enter to close'
