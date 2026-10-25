param()
$ErrorActionPreference='Stop'
$Host.UI.RawUI.WindowTitle='DH 13 vs 134 vs 1342 - secure API key input'
$routeCampaign='/var/tmp/longcli-dh-routing3x7-20261008'
$routePython='/mnt/sdb/home/lizh639/terminalbench-v14-setup/runtime/bin/python'
$routeSshKey='C:/Users/54177/.ssh/cubestudio_notebook'
$routeHost='lizh639@172.16.108.236'
try {
    Write-Host 'Three arms x same seven tasks = 21 trials. 6 total concurrent, 2 per arm.'
    Write-Host 'deepseek-flash, thinking off, temp 0; 800 total API attempts, 600 tools, 2h per task.'
    Write-Host 'All roles use the same total budget. Fresh Docker task and memory per trial.'
    & ssh -i $routeSshKey -o BatchMode=yes -o ConnectTimeout=15 $routeHost "$routePython -B $routeCampaign/launch.py --check"
    if ($LASTEXITCODE -ne 0) { throw 'Readiness failed; inspect before retrying.' }
    $routeSecret=Read-Host 'Enter DeepSeek API key (hidden; do not send in chat)' -AsSecureString
    $routePointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($routeSecret)
    try {
        $routePlain=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($routePointer).Trim()
        if (-not $routePlain -or $routePlain -match '\s') { throw 'Invalid credential.' }
        $routePlain | & ssh -i $routeSshKey -o BatchMode=yes -o ConnectTimeout=15 $routeHost "$routePython -B $routeCampaign/launch.py"
        if ($LASTEXITCODE -ne 0) { throw 'Launch uncertain; inspect status before retrying.' }
        Write-Host 'Started on college compute node. Official grading follows automatically.' -ForegroundColor Green
    } finally {
        $routePlain=$null
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($routePointer)
        $routeSecret.Dispose()
    }
} catch { Write-Host $_.Exception.Message -ForegroundColor Red }
Read-Host 'Press Enter to close'
