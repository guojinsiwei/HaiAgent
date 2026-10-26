param()
$ErrorActionPreference='Stop'
$Host.UI.RawUI.WindowTitle='Resume five LongCLI experiments - secure key input'
$campaign='/mnt/sdb/home/lizh639/longcli-resume-five-20261007'
$remotePython='/mnt/sdb/home/lizh639/terminalbench-v14-setup/runtime/bin/python'
$sshKey='C:/Users/54177/.ssh/cubestudio_notebook'
$college='lizh639@172.16.108.236'
try {
    Write-Host 'Resume ReTRAC, DH-large, Recuris, TACO, LATS. Completed results are preserved.'
    Write-Host '23 completed; 77 unfinished tasks restarted in separate directories.'
    Write-Host 'Same per-arm model/resource budgets. No intermediate official feedback.'
    & ssh -i $sshKey -o BatchMode=yes -o ConnectTimeout=15 $college "$remotePython -B $campaign/launch_all.py --check"
    if ($LASTEXITCODE -ne 0) { throw 'Readiness check failed. No launch.' }
    $secret=Read-Host 'Enter DeepSeek API key (hidden; do not paste into chat)' -AsSecureString
    $pointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
    try {
        $plain=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer).Trim()
        if (-not $plain -or $plain -match '\s') { throw 'Invalid key' }
        $plain | & ssh -i $sshKey -o BatchMode=yes -o ConnectTimeout=15 $college "$remotePython -B $campaign/launch_all.py"
        if ($LASTEXITCODE -ne 0) { throw 'Launch uncertain; inspect status before retrying.' }
        Write-Host 'Started. All five controllers and graders continue on the server.' -ForegroundColor Green
    } finally {
        $plain=$null
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
        $secret.Dispose()
    }
} catch { Write-Host $_.Exception.Message -ForegroundColor Red }
Read-Host 'Press Enter to close'
