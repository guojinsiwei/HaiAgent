param([ValidateSet('pilot','screen')][string]$Stage = 'pilot')
$ErrorActionPreference = 'Stop'
$experimentKey = Join-Path $env:USERPROFILE '.ssh\cubestudio_notebook'
$experimentRemote = 'lizh639@172.16.108.236'
$experimentDirectory = '/var/tmp/lizh639-lhtb-mechanism-large-20261001'
$experimentPython = '/mnt/sdb/home/lizh639/terminalbench-v14-setup/runtime/bin/python'
& ssh -i $experimentKey -o BatchMode=yes -o ConnectTimeout=15 $experimentRemote "cd $experimentDirectory && $experimentPython -B control.py validate"
if ($LASTEXITCODE -ne 0) { throw 'Preflight failed; inspect before starting' }
if ($Stage -eq 'screen') {
    & ssh -i $experimentKey -o BatchMode=yes $experimentRemote "cd $experimentDirectory && $experimentPython -B promote_screen.py"
    if ($LASTEXITCODE -ne 0) { throw 'Pilot promotion refused; inspect status' }
}
$experimentSecret = Read-Host "DeepSeek API Key (hidden; stage=$Stage)" -AsSecureString
$experimentPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($experimentSecret)
try {
    $experimentPlain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($experimentPointer).Trim()
    if (-not $experimentPlain -or $experimentPlain -match '\s') { throw 'Invalid key' }
    $experimentPlain | & ssh -i $experimentKey -o BatchMode=yes $experimentRemote "cd $experimentDirectory && $experimentPython -B launch_supervised.py $experimentDirectory college"
    if ($LASTEXITCODE -ne 0) { throw 'Launch not confirmed; inspect before retry' }
} finally {
    $experimentPlain = $null
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($experimentPointer)
    $experimentSecret.Dispose()
}
