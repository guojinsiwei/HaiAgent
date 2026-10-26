$ErrorActionPreference = 'Stop'
$experimentKey = Join-Path $env:USERPROFILE '.ssh\cubestudio_notebook'
$experimentRemote = 'lizh639@172.16.108.236'
$experimentDirectory = '/var/tmp/lizh639-lhtb-hai082-only-r1'
$experimentPython = '/mnt/sdb/home/lizh639/terminalbench-v14-setup/runtime/bin/python'
& ssh -i $experimentKey -o BatchMode=yes -o ConnectTimeout=15 $experimentRemote "cd $experimentDirectory && $experimentPython -B control.py validate && test ! -f health.json"
if ($LASTEXITCODE -ne 0) { throw 'Preflight failed or already launched. Nothing started; inspect status first.' }
$experimentSecret = Read-Host 'DeepSeek API Key (hidden; HAI 0.8.2 fixed 12 tasks)' -AsSecureString
$experimentPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($experimentSecret)
try {
    $experimentPlain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($experimentPointer).Trim()
    if (-not $experimentPlain -or $experimentPlain -match '\s') { throw 'Invalid key; nothing started.' }
    $experimentPlain | & ssh -i $experimentKey -o BatchMode=yes -o ConnectTimeout=15 $experimentRemote "cd $experimentDirectory && $experimentPython -B launch_supervised.py $experimentDirectory college"
    if ($LASTEXITCODE -ne 0) { throw 'Launch not confirmed; inspect before retrying.' }
} finally {
    $experimentPlain = $null
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($experimentPointer)
}
