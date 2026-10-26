param()
$ErrorActionPreference='Stop'
$Host.UI.RawUI.WindowTitle='DH best + DSH large budget - LongCLI 20'
$campaign='/mnt/sdb/home/lizh639/longcli-dh-large20-20261007'
$remotePython='/mnt/sdb/home/lizh639/terminalbench-v14-setup/runtime/bin/python'
$sshKey='C:/Users/54177/.ssh/cubestudio_notebook'
$college='lizh639@172.16.108.236'
try {
    Write-Host 'Historical best DH, 20 fresh tasks; same large resource budget as DSH.'
    Write-Host 'deepseek-flash / thinking OFF / temperature 0 / 1M context / 32768 output tokens.'
    Write-Host 'Per task: 800 ACTUAL API attempts across all roles, 600 tools, 2h, 2CPU, 8GiB.'
    Write-Host 'One pilot included in the 20, then concurrency 4. Stop on engineering faults.'
    & ssh -i $sshKey -o BatchMode=yes -o ConnectTimeout=15 $college "cd $campaign && $remotePython -B -c 'from runner import validate_ready; validate_ready(); print(123)'"
    if ($LASTEXITCODE -ne 0) { throw 'Sealed acceptance failed. Nothing launched.' }
    $secret=Read-Host 'Enter NEW DeepSeek API key (hidden; never paste into chat)' -AsSecureString
    $pointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
    try {
        $plain=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer).Trim()
        if (-not $plain -or $plain -match '\s') { throw 'Invalid key' }
        $plain | & ssh -i $sshKey -o BatchMode=yes -o ConnectTimeout=15 $college "$remotePython -B $campaign/launch.py"
        if ($LASTEXITCODE -ne 0) { throw 'Launch failed or uncertain. Do not retry until status is checked.' }
        Write-Host 'Started. Server-side controller and official grading continue after this window closes.'
    } finally {
        $plain=$null
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
        $secret.Dispose()
    }
} catch { Write-Host $_.Exception.Message -ForegroundColor Red }
Read-Host 'Press Enter to close'
