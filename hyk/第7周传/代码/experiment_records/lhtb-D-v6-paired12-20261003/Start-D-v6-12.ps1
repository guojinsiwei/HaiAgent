$ErrorActionPreference='Stop'
$dvSshKey=Join-Path $env:USERPROFILE '.ssh\cubestudio_notebook'
$dvRemote='lizh639@172.16.108.236'
$dvDirectory='/var/tmp/lizh639-lhtb-D-v6-paired12-20261003-r1'
$dvPython='/mnt/sdb/home/lizh639/terminalbench-v14-setup/runtime/bin/python'
& ssh -i $dvSshKey -o BatchMode=yes -o ConnectTimeout=15 $dvRemote "cd $dvDirectory && $dvPython -B control.py validate"
if ($LASTEXITCODE -ne 0) { throw 'Preflight failed; no credential requested' }
Write-Host 'D + v6(engineering-fixed v6.1): 12 tasks each, 24 new trials, 4 slots.'
Write-Host 'deepseek-flash / thinking off / temperature0 / 600 tools / 800 actor turns.'
Write-Host 'A12 continues. No RAW or v8 reruns, no automatic task retries or key reuse.'
$dvSecret=Read-Host 'DeepSeek API key (hidden)' -AsSecureString
$dvPointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($dvSecret)
try {
    $dvPlain=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($dvPointer).Trim()
    if (-not $dvPlain -or $dvPlain -match '\s') { throw 'Invalid key' }
    $dvPlain | & ssh -i $dvSshKey -o BatchMode=yes -o ConnectTimeout=15 $dvRemote "cd $dvDirectory && $dvPython -B launch_supervised.py $dvDirectory college"
    if ($LASTEXITCODE -ne 0) { throw 'Launch unconfirmed; inspect state before retrying' }
} finally {
    $dvPlain=$null
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($dvPointer)
    $dvSecret.Dispose()
}
Write-Host 'Launch confirmed. Both arms continue on the server after this window closes.'
