param()
$ErrorActionPreference='Stop'
$Host.UI.RawUI.WindowTitle='DH cow format repair - secure key input'
$campaign='/mnt/sdb/home/lizh639/longcli-dh-cow-format-repair-20261007'
$remotePython='/mnt/sdb/home/lizh639/terminalbench-v14-setup/runtime/bin/python'
$sshKey='C:/Users/54177/.ssh/cubestudio_notebook'
$college='lizh639@172.16.108.236'
try {
    Write-Host 'One fresh cow attempt. Earlier result remains unchanged.'
    Write-Host 'Same 800 API / 600 tool / 7200-second limits. This can incur API cost.'
    & ssh -i $sshKey -o BatchMode=yes -o ConnectTimeout=15 $college "$remotePython -B $campaign/launch_cow.py --check"
    if ($LASTEXITCODE -ne 0) { throw 'Readiness check failed. No launch.' }
    $secret=Read-Host 'Enter a NEW DeepSeek API key (hidden; do not paste into chat)' -AsSecureString
    $pointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
    try {
        $plain=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer).Trim()
        if (-not $plain -or $plain -match '\s') { throw 'Invalid key' }
        $plain | & ssh -i $sshKey -o BatchMode=yes -o ConnectTimeout=15 $college "$remotePython -B $campaign/launch_cow.py"
        if ($LASTEXITCODE -ne 0) { throw 'Launch uncertain; inspect status before retrying.' }
        Write-Host 'Started isolated cow run.' -ForegroundColor Green
    } finally {
        $plain=$null
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
        $secret.Dispose()
    }
} catch { Write-Host $_.Exception.Message -ForegroundColor Red }
