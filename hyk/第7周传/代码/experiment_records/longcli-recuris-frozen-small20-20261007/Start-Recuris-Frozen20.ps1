param()
$ErrorActionPreference='Stop'
$Host.UI.RawUI.WindowTitle='Recuris-Frozen - LongCLI matched small budget'
$campaign='/mnt/sdb/home/lizh639/longcli-recuris-frozen-small20-20261007'
$remotePython='/mnt/sdb/home/lizh639/terminalbench-v14-setup/runtime/bin/python'
$sshKey='C:/Users/54177/.ssh/cubestudio_notebook'
$college='lizh639@172.16.108.236'
try {
    Write-Host 'Recuris-Frozen,20 tasks,ONE attempt each. NO official feedback,NO Meta/TTA.'
    Write-Host 'Same deepseek-flash/thinking OFF/temperature0/48,000 UTF8 bytes/4096 output tokens.'
    Write-Host '800 all-role logical calls,<=1600 wire attempts,600 commands,2CPU/8GiB.'
    Write-Host 'Two included graded canaries,then concurrency<=2. This window STARTS paid trials after hidden key input.'
    & ssh -i $sshKey -o BatchMode=yes -o ConnectTimeout=15 $college "cd $campaign && $remotePython -B -c 'from common import validate; validate(); print(123)'"
    if ($LASTEXITCODE -ne 0) { throw 'Sealed acceptance failed.Nothing launched.' }
    $secret=Read-Host 'Enter NEW DeepSeek API key (hidden;never paste into chat)' -AsSecureString
    $pointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
    try {
        $plain=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer).Trim()
        if (-not $plain -or $plain -match '\s') { throw 'Invalid key' }
        $plain | & ssh -i $sshKey -o BatchMode=yes -o ConnectTimeout=15 $college "$remotePython -B $campaign/launch.py"
        if ($LASTEXITCODE -ne 0) { throw 'Launch failed or uncertain.Check status before retrying.' }
        Write-Host 'Started.Server-side generation and official final grading continue independently.'
    } finally {
        $plain=$null
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
        $secret.Dispose()
    }
} catch { Write-Host $_.Exception.Message -ForegroundColor Red }
Read-Host 'Press Enter to close'
