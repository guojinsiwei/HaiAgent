param()
$ErrorActionPreference='Stop'
$Host.UI.RawUI.WindowTitle='Re-TRAC LongCLI recovery: nine unfinished tasks'
$reTracCampaign='/mnt/sdb/home/lizh639/longcli-retrac-recovery4-20261007'
$reTracPython="$reTracCampaign/runtime/bin/python"
$reTracKeyPath='C:/Users/54177/.ssh/cubestudio_notebook'
$reTracHost='lizh639@172.16.108.236'
try {
    Write-Host 'Re-TRAC: nine unfinished LongCLI tasks, four parallel after keyless checks.'
    Write-Host 'Previously completed eleven artifacts are retained; missing P0 score has been graded.'
    Write-Host 'DeepSeek Flash, thinking off, temperature 0. Per task: 800 requests, 600 tools, 2 hours.'
    Write-Host 'Task files and logs on /mnt/sdb, fresh Docker container and home per task.'
    & ssh -i $reTracKeyPath -o BatchMode=yes -o ConnectTimeout=15 $reTracHost "$reTracPython -B $reTracCampaign/check_ready.py"
    if ($LASTEXITCODE -ne 0) { throw 'Sealed no-API acceptance failed; no paid task started.' }
    $reTracSecret=Read-Host 'Enter NEW DeepSeek API key (hidden; do not paste into chat)' -AsSecureString
    $reTracPointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($reTracSecret)
    try {
        $reTracPlain=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($reTracPointer).Trim()
        if (-not $reTracPlain -or $reTracPlain -match '\s') { throw 'Invalid key' }
        $reTracPlain | & ssh -i $reTracKeyPath -o BatchMode=yes -o ConnectTimeout=15 $reTracHost "$reTracPython -B $reTracCampaign/launch.py --check-only"
        if ($LASTEXITCODE -ne 0) { throw 'Model credential preflight failed; no paid task started.' }
        $reTracPlain | & ssh -i $reTracKeyPath -o BatchMode=yes -o ConnectTimeout=15 $reTracHost "$reTracPython -B $reTracCampaign/launch.py"
        if ($LASTEXITCODE -ne 0) { throw 'Launch failed or uncertain. Inspect server status before retrying.' }
        Write-Host 'Server-side experiment and automatic official scoring started.'
    } finally {
        $reTracPlain=$null
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($reTracPointer)
        $reTracSecret.Dispose()
    }
} catch { Write-Host $_.Exception.Message -ForegroundColor Red }
Read-Host 'Press Enter to close'
