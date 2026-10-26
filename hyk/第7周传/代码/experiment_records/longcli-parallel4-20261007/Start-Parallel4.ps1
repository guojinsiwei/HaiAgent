param()
$ErrorActionPreference='Stop'
$campaign='/mnt/sdb/home/lizh639/longcli-parallel4-20261007'
$remotePython='/mnt/sdb/home/lizh639/terminalbench-v14-setup/runtime/bin/python'
$sshKey='C:/Users/54177/.ssh/cubestudio_notebook'
$college='lizh639@172.16.108.236'
$Host.UI.RawUI.WindowTitle='LATS and TACO concurrency 4 - secure key input'
try {
    & ssh -i $sshKey -o BatchMode=yes -o ConnectTimeout=15 $college "$remotePython -B $campaign/launch_parallel.py --check"
    if ($LASTEXITCODE -ne 0) { throw 'Readiness check failed.' }
    $secret=Read-Host 'Enter DeepSeek API key (hidden). LATS and TACO will each run 4 tasks' -AsSecureString
    $pointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
    try {
        $plain=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer).Trim()
        if (-not $plain -or $plain -match '\s') { throw 'Invalid key' }
        $plain | & ssh -i $sshKey -o BatchMode=yes -o ConnectTimeout=15 $college "$remotePython -B $campaign/launch_parallel.py"
        if ($LASTEXITCODE -ne 0) { throw 'Handover uncertain; inspect status before retrying.' }
        Write-Host 'Both experiments now use 4 concurrent task slots.' -ForegroundColor Green
    } finally {
        $plain=$null
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
        $secret.Dispose()
    }
} catch { Write-Host $_.Exception.Message -ForegroundColor Red }
Read-Host 'Press Enter to close'
