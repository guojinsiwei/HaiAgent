param()
$ErrorActionPreference='Stop'
$Host.UI.RawUI.WindowTitle='TACO clean LongCLI 20 - secure key input'
$campaign='/mnt/sdb/home/lizh639/longcli-taco-clean20-20261007'
$remotePython='/mnt/sdb/home/lizh639/terminalbench-v14-setup/runtime/bin/python'
$sshKey='C:/Users/54177/.ssh/cubestudio_notebook'
$college='lizh639@172.16.108.236'
try {
    Write-Host 'Fresh TACO 20-task run. Each task has a separate rule cache; old results are not reused.'
    & ssh -i $sshKey -o BatchMode=yes -o ConnectTimeout=15 $college "$remotePython -B $campaign/launch_taco_clean.py --check"
    if ($LASTEXITCODE -ne 0) { throw 'Readiness check failed. No launch.' }
    $secret=Read-Host 'Enter DeepSeek API key (hidden; do not paste into chat)' -AsSecureString
    $pointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
    try {
        $plain=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer).Trim()
        if (-not $plain -or $plain -match '\s') { throw 'Invalid key' }
        $plain | & ssh -i $sshKey -o BatchMode=yes -o ConnectTimeout=15 $college "$remotePython -B $campaign/launch_taco_clean.py"
        if ($LASTEXITCODE -ne 0) { throw 'Launch uncertain; inspect remote status before retrying.' }
        Write-Host 'TACO clean 20 started.' -ForegroundColor Green
    } finally {
        $plain=$null
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
        $secret.Dispose()
    }
} catch { Write-Host $_.Exception.Message -ForegroundColor Red }
Read-Host 'Press Enter to close'
