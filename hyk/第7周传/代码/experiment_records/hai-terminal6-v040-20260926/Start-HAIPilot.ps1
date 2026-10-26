$ErrorActionPreference = 'Stop'
$haiSshKey = Join-Path $env:USERPROFILE '.ssh\cubestudio_notebook'
$haiRemote = 'lizh639@172.16.108.236'
$haiDirectory = '/mnt/sdb/home/lizh639/hai-terminal6-v040-20260926'
# Wait without credentials while official fixture dependencies download.
$haiReady = $false
for ($haiPoll = 0; $haiPoll -lt 30; $haiPoll++) {
    & ssh -i $haiSshKey -o BatchMode=yes -o ConnectTimeout=15 $haiRemote "test -f $haiDirectory/ready.json"
    if ($LASTEXITCODE -eq 0) { $haiReady = $true; break }
    if ($LASTEXITCODE -eq 255) { throw 'SSH connection failed; nothing started.' }
    Write-Host 'Waiting for cloud offline preflight (no model calls)...'
    Start-Sleep -Seconds 30
}
if (-not $haiReady) { throw 'Preflight did not finish within 15 minutes. Nothing started; inspect status.' }
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
