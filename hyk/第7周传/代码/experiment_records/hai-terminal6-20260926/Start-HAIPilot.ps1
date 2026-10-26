$ErrorActionPreference = 'Stop'
$haiSshKey = Join-Path $env:USERPROFILE '.ssh\cubestudio_notebook'
$haiRemote = 'lizh639@172.16.108.236'
$haiDirectory = '/mnt/sdb/home/lizh639/hai-terminal6-20260926'
# Readiness check contains no credentials and never starts a worker.
& ssh -i $haiSshKey -o BatchMode=yes -o ConnectTimeout=15 $haiRemote "test -f $haiDirectory/ready.json"
if ($LASTEXITCODE -ne 0) { throw 'Cloud offline preflight is not ready yet. No key requested and nothing started.' }
$haiSecret = Read-Host 'DeepSeek API Key (hidden, this 12-run pilot only)' -AsSecureString
$haiPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($haiSecret)
try {
    $haiPlain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($haiPointer).Trim()
    if (-not $haiPlain -or $haiPlain -match '\s') { throw 'Invalid key; nothing started.' }
    $haiPlain | & ssh -i $haiSshKey -o BatchMode=yes -o ConnectTimeout=15 $haiRemote "cd $haiDirectory && /mnt/sdb/home/lizh639/terminalbench-v14-setup/runtime/bin/python -B launch.py"
    if ($LASTEXITCODE -ne 0) { throw 'Launch was not confirmed. Inspect status before trying again.' }
} finally {
    $haiPlain = $null
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($haiPointer)
}
