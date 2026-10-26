$ErrorActionPreference='Stop'
$rawSshKey=Join-Path $env:USERPROFILE '.ssh\cubestudio_notebook'
$rawRemote='lizh639@172.16.108.236'
$rawDirectory='/var/tmp/lizh639-lhtb-raw12-engineering-v2-20261002-r1'
$rawPython='/mnt/sdb/home/lizh639/terminalbench-v14-setup/runtime/bin/python'
& ssh -i $rawSshKey -o BatchMode=yes -o ConnectTimeout=15 $rawRemote "cd $rawDirectory && $rawPython -B control.py validate"
if ($LASTEXITCODE -ne 0) { throw 'Preflight failed; no credential requested' }
Write-Host 'RAW: same 12 tasks, deepseek-flash, four slots, 600 tools / 800 actor decisions.'
Write-Host 'One actor only: no experience memory, adviser, semantic monitor or exploration gate.'
Write-Host 'Previous experiments continue unchanged. No GPT automation or credential reuse.'
$rawSecret=Read-Host 'DeepSeek API key (hidden)' -AsSecureString
$rawPointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($rawSecret)
try {
    $rawPlain=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($rawPointer).Trim()
    if (-not $rawPlain -or $rawPlain -match '\s') { throw 'Invalid key' }
    $rawPlain | & ssh -i $rawSshKey -o BatchMode=yes -o ConnectTimeout=15 $rawRemote "cd $rawDirectory && $rawPython -B launch_supervised.py $rawDirectory college"
    if ($LASTEXITCODE -ne 0) { throw 'Launch unconfirmed; inspect state before retrying' }
} finally {
    $rawPlain=$null
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($rawPointer)
    $rawSecret.Dispose()
}
Write-Host 'RAW launch confirmed. Server workers continue after this window closes.'
