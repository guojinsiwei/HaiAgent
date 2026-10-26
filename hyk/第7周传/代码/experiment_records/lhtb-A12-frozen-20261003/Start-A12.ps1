$ErrorActionPreference='Stop'
$a12SshKey=Join-Path $env:USERPROFILE '.ssh\cubestudio_notebook'
$a12Remote='lizh639@172.16.108.236'
$a12Directory='/var/tmp/lizh639-lhtb-A12-frozen-20261003-r1'
$a12Python='/mnt/sdb/home/lizh639/terminalbench-v14-setup/runtime/bin/python'
& ssh -i $a12SshKey -o BatchMode=yes -o ConnectTimeout=15 $a12Remote "cd $a12Directory && $a12Python -B control.py validate"
if ($LASTEXITCODE -ne 0) { throw 'Preflight failed; no credential requested' }
Write-Host 'Frozen A: original 12 tasks, 4 slots, deepseek-flash, thinking off, temperature 0.'
Write-Host 'No memory, recovery or route search. Monitor and adviser remain enabled.'
Write-Host '600 tools / 800 actor turns / 12 monitor / 6 adviser. No automatic task replay.'
$a12Secret=Read-Host 'DeepSeek API key (hidden)' -AsSecureString
$a12Pointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($a12Secret)
try {
    $a12Plain=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($a12Pointer).Trim()
    if (-not $a12Plain -or $a12Plain -match '\s') { throw 'Invalid key' }
    $a12Plain | & ssh -i $a12SshKey -o BatchMode=yes -o ConnectTimeout=15 $a12Remote "cd $a12Directory && $a12Python -B launch_supervised.py $a12Directory college"
    if ($LASTEXITCODE -ne 0) { throw 'Launch unconfirmed; inspect state before retrying' }
} finally {
    $a12Plain=$null
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($a12Pointer)
    $a12Secret.Dispose()
}
Write-Host 'Launch confirmed. Server workers continue after this window closes.'
