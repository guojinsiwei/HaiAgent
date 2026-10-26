param()
$ErrorActionPreference='Stop'
$Host.UI.RawUI.WindowTitle='LATS + TACO - LongCLI small budget'
$campaign='/mnt/sdb/home/lizh639/longcli-lats-taco-small20-20261007'
$remotePython='/mnt/sdb/home/lizh639/terminalbench-v14-setup/runtime/bin/python'
$sshKey='C:/Users/54177/.ssh/cubestudio_notebook'
$college='lizh639@172.16.108.236'
try {
    Write-Host 'LATS-CLI + TACO-CLI, 20 tasks each. SGE cancelled.'
    Write-Host 'deepseek-flash / thinking OFF / temperature 0 / 48,000 UTF8 bytes / 4096 output tokens.'
    Write-Host 'Each task: 800 all-role logical calls, <=1600 wire attempts, 600 commands; 2CPU / 8GiB.'
    Write-Host 'Two included graded canaries per arm. TACO fixed sequential order. Concurrency <=2.'
    & ssh -i $sshKey -o BatchMode=yes -o ConnectTimeout=15 $college "cd $campaign && $remotePython -B -c 'from common import validate; validate(); print(123)'"
    if ($LASTEXITCODE -ne 0) { throw 'Sealed acceptance failed. Nothing launched.' }
    $secret=Read-Host 'Enter NEW DeepSeek API key (hidden; never paste into chat)' -AsSecureString
    $pointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
    try {
        $plain=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer).Trim()
        if (-not $plain -or $plain -match '\s') { throw 'Invalid key' }
        $plain | & ssh -i $sshKey -o BatchMode=yes -o ConnectTimeout=15 $college "$remotePython -B $campaign/launch.py"
        if ($LASTEXITCODE -ne 0) { throw 'Launch failed or uncertain. Check status before retrying.' }
        Write-Host 'Started. Server-side controller and official grading continue after this window closes.'
    } finally {
        $plain=$null
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
        $secret.Dispose()
    }
} catch { Write-Host $_.Exception.Message -ForegroundColor Red }
Read-Host 'Press Enter to close'
