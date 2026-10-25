$ErrorActionPreference='Stop'
$lhtbContrastSshKey=Join-Path $env:USERPROFILE '.ssh\cubestudio_notebook'
$lhtbContrastRemote='lizh639@172.16.108.236'
$lhtbContrastDirectory='/var/tmp/lizh639-lhtb-contrastive12-v8-20261002'
$lhtbContrastPython='/mnt/sdb/home/lizh639/terminalbench-v14-setup/runtime/bin/python'
& ssh -i $lhtbContrastSshKey -o BatchMode=yes -o ConnectTimeout=15 $lhtbContrastRemote "cd $lhtbContrastDirectory && $lhtbContrastPython -B control.py validate"
if ($LASTEXITCODE -ne 0) { throw 'Preflight failed; no credential requested' }
Write-Host 'LHTB original RAW 12 tasks. Two exploration arms, 24 fresh official trials, four parallel slots.'
Write-Host 'The previous micro-pilot entry is superseded. No extra RAW rerun is included.'
Write-Host 'Same deepseek-flash, 600 tools/task, 800 logical model calls/task and original wall limits.'
Write-Host 'Key stays in protected stdin/anonymous pipes/process memory, never files or command arguments.'
$lhtbContrastSecret=Read-Host 'DeepSeek API key (hidden)' -AsSecureString
$lhtbContrastPointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($lhtbContrastSecret)
try {
    $lhtbContrastPlain=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($lhtbContrastPointer).Trim()
    if (-not $lhtbContrastPlain -or $lhtbContrastPlain -match '\s') { throw 'Invalid key' }
    $lhtbContrastPlain | & ssh -i $lhtbContrastSshKey -o BatchMode=yes -o ConnectTimeout=15 $lhtbContrastRemote "cd $lhtbContrastDirectory && $lhtbContrastPython -B launch_supervised.py $lhtbContrastDirectory college"
    if ($LASTEXITCODE -ne 0) { throw 'Launch unconfirmed; inspect state before retrying' }
} finally {
    $lhtbContrastPlain=$null
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($lhtbContrastPointer)
    $lhtbContrastSecret.Dispose()
}
Write-Host 'Supervisor launched. It continues after this window closes; check campaign health for progress.'
