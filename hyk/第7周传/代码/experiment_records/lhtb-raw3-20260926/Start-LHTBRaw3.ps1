$ErrorActionPreference = 'Stop'
$lhtbRemote = 'lizh639@172.16.108.236'
$lhtbKey = Join-Path $env:USERPROFILE '.ssh\cubestudio_notebook'
$lhtbDir = '/mnt/sdb/home/lizh639/lhtb-raw3-20260926'
& ssh -i $lhtbKey -o BatchMode=yes -o ConnectTimeout=15 $lhtbRemote "test -f $lhtbDir/ready.json"
if ($LASTEXITCODE -ne 0) { throw 'Cloud preflight is not ready, or SSH failed. No model calls started.' }
$lhtbSecret = Read-Host 'DeepSeek API Key (hidden, Raw 3 tasks only)' -AsSecureString
$lhtbPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($lhtbSecret)
try {
    $lhtbPlain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($lhtbPointer).Trim()
    if (-not $lhtbPlain -or $lhtbPlain -match '\s') { throw 'Invalid key; nothing started.' }
    $lhtbPlain | & ssh -i $lhtbKey -o BatchMode=yes -o ConnectTimeout=15 $lhtbRemote "cd $lhtbDir && /mnt/sdb/home/lizh639/terminalbench-v14-setup/runtime/bin/python -B launch.py"
    if ($LASTEXITCODE -ne 0) { throw 'Launch not confirmed. Inspect status before retrying.' }
} finally {
    $lhtbPlain = $null
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($lhtbPointer)
}
