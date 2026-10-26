$ErrorActionPreference='Stop'
$repairSshKey=Join-Path $env:USERPROFILE '.ssh\cubestudio_notebook'
$repairRemote='lizh639@172.16.108.236'
$repairDirectory='/var/tmp/lizh639-lhtb-contrastive12-engineering-v2-20261002-r1'
$repairPython='/mnt/sdb/home/lizh639/terminalbench-v14-setup/runtime/bin/python'
& ssh -i $repairSshKey -o BatchMode=yes -o ConnectTimeout=15 $repairRemote "cd $repairDirectory && $repairPython -B control.py validate"
if ($LASTEXITCODE -ne 0) { throw 'Preflight failed; no credential requested' }
Write-Host 'Engineering repair v2: two arms x the same 12 tasks = 24 NEW trials, four slots.'
Write-Host 'Old results remain unchanged. Same deepseek-flash and original task budgets.'
Write-Host 'Fresh DeepSeek key only; no GPT heartbeat/automation. Do not paste the key in chat.'
$repairSecret=Read-Host 'DeepSeek API key (hidden)' -AsSecureString
$repairPointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($repairSecret)
try {
    $repairPlain=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($repairPointer).Trim()
    if (-not $repairPlain -or $repairPlain -match '\s') { throw 'Invalid key' }
    $repairPlain | & ssh -i $repairSshKey -o BatchMode=yes -o ConnectTimeout=15 $repairRemote "cd $repairDirectory && $repairPython -B launch_supervised.py $repairDirectory college"
    if ($LASTEXITCODE -ne 0) { throw 'Launch unconfirmed; inspect state before retrying' }
} finally {
    $repairPlain=$null
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($repairPointer)
    $repairSecret.Dispose()
}
Write-Host 'Launch confirmed. Server workers continue when this window closes.'
