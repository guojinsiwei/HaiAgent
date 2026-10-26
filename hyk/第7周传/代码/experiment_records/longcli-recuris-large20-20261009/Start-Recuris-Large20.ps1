param()
$ErrorActionPreference='Stop'
$Host.UI.RawUI.WindowTitle='Recuris LARGE 20 - secure API key input'
$largeCampaign='/mnt/sdb/home/lizh639/longcli-recuris-large20-20261009'
$largePython='/mnt/sdb/home/lizh639/terminalbench-v14-setup/runtime/bin/python'
$largeKey='C:/Users/54177/.ssh/cubestudio_notebook'
$largeHost='lizh639@172.16.108.236'
try {
    Write-Host 'Recuris-Frozen: 20 fresh tasks, up to 6 concurrent after first included delivery canary.'
    Write-Host 'Fresh container and task-local working memory; no Meta/TTA or cross-task learning.'
    Write-Host 'DH 1342 LARGE profile: 1M context allowance, output 32768, actual API attempts 800, tools 600, 2h.'
    & ssh -i $largeKey -o BatchMode=yes -o ConnectTimeout=15 $largeHost "$largePython -B $largeCampaign/launch.py --check"
    if ($LASTEXITCODE -ne 0) { throw 'Readiness failed; do not input key.' }
    $largeSecret=Read-Host 'Enter DeepSeek API key (hidden, do not send in chat)' -AsSecureString
    $largePointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($largeSecret)
    try {
        $largePlain=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($largePointer).Trim()
        if (-not $largePlain -or $largePlain -match '\s') { throw 'Invalid credential.' }
        $largePlain | & ssh -i $largeKey -o BatchMode=yes -o ConnectTimeout=15 $largeHost "$largePython -B $largeCampaign/launch.py"
        if ($LASTEXITCODE -ne 0) { throw 'Launch uncertain; inspect status before retrying.' }
        Write-Host 'Started; keep original records. Official grading follows automatically.' -ForegroundColor Green
    } finally {
        $largePlain=$null
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($largePointer)
        $largeSecret.Dispose()
    }
} catch { Write-Host $_.Exception.Message -ForegroundColor Red }
Read-Host 'Press Enter to close'
