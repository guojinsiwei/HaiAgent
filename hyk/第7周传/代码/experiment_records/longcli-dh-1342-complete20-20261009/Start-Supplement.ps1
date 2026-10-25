$ErrorActionPreference='Stop'
$Host.UI.RawUI.WindowTitle='DH 1342 historic large-budget - remaining 13 - secure input'
$dhCampaign='/mnt/sdb/home/lizh639/longcli-dh-1342-complete20-20261009'
$dhPython='/mnt/sdb/home/lizh639/terminalbench-v14-setup/runtime/bin/python'
$dhIdentity='C:/Users/54177/.ssh/cubestudio_notebook'
try {
    Write-Host 'Preserve original 7 scores. Run ONLY the remaining 13. Maximum concurrency: 6.'
    Write-Host 'Original DH subgoals + 1342. deepseek-flash, thinking off, temperature 0.'
    Write-Host 'Per task: 800 total API attempts / 600 tools / 32768 output / 1M context / 2h.'
    & ssh -i $dhIdentity -o BatchMode=yes -o ConnectTimeout=15 lizh639@172.16.108.236 "$dhPython -B $dhCampaign/launch.py --check"
    if ($LASTEXITCODE -ne 0) { throw 'Readiness failed; no API calls permitted.' }
    $dhSecret=Read-Host 'Enter DeepSeek API key (hidden; never paste in chat)' -AsSecureString
    $dhPointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($dhSecret)
    try {
        $dhPlain=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($dhPointer).Trim()
        if (-not $dhPlain -or $dhPlain -match '\s') { throw 'Invalid credential' }
        $dhPlain | & ssh -i $dhIdentity -o BatchMode=yes -o ConnectTimeout=15 lizh639@172.16.108.236 "$dhPython -B $dhCampaign/launch.py"
        if ($LASTEXITCODE -ne 0) { throw 'Launch uncertain. Inspect status before retrying.' }
        Write-Host 'Started. Official grading follows automatically.' -ForegroundColor Green
    } finally {
        $dhPlain=$null
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($dhPointer)
        $dhSecret.Dispose()
    }
} catch { Write-Host $_.Exception.Message -ForegroundColor Red }
Read-Host 'Press Enter to close'
