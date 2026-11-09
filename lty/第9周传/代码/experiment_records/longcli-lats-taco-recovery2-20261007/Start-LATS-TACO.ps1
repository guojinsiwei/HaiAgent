param()
$ErrorActionPreference='Stop'
$Host.UI.RawUI.WindowTitle='LATS + TACO recovery - secure API key input'
$taskPython='C:/Users/54177/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
$taskSshKey='C:/Users/54177/.ssh/cubestudio_notebook'
$collegePython='/mnt/sdb/home/lizh639/terminalbench-v14-setup/runtime/bin/python'
$collegeRoot='/var/tmp/lizh639-longcli-lats-taco-recovery2-20261007'
$cubePython='/mnt/lizh639/longcli-retrac20-matched-20261006/test-env/bin/python'
$targets=@(
    @{HostName='lizh639@172.16.108.236';Python=$collegePython;Root="$collegeRoot/lats"},
    @{HostName='cubestudio_container';Python=$cubePython;Root='/mnt/lizh639/longcli-taco-recovery2-worker0-20261007'},
    @{HostName='cubestudio_container2';Python=$cubePython;Root='/mnt/lizh639/longcli-taco-recovery2-worker1-20261007'}
)
try {
    Write-Host 'ONLY LATS + TACO. DH is not started.'
    Write-Host 'LATS: 4/20 preserved, 16 new attempts on college, concurrency 6.'
    Write-Host 'TACO: 15/20 preserved, 5 new attempts on CubeStudio (3+2), arm cap 6.'
    Write-Host 'Same model/budgets. Cube uses native namespaces; official grading stays on college.'
    foreach ($target in $targets) {
        & ssh -i $taskSshKey -o BatchMode=yes -o ConnectTimeout=15 $target.HostName "$($target.Python) -B $($target.Root)/launch_one.py --check"
        if ($LASTEXITCODE -ne 0) { throw 'Readiness failed. No new tasks started. Inspect before retry.' }
    }
    & ssh -i $taskSshKey -o BatchMode=yes -o ConnectTimeout=15 'lizh639@172.16.108.236' "$collegePython -B $collegeRoot/taco/check_grader.py"
    if ($LASTEXITCODE -ne 0) { throw 'Grading readiness failed. No launch.' }
    $taskSecret=Read-Host 'Enter a fresh DeepSeek API key (hidden; never send in chat)' -AsSecureString
    $taskPointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($taskSecret)
    try {
        $taskPlain=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($taskPointer).Trim()
        if (-not $taskPlain -or $taskPlain -match '\s') { throw 'Invalid key.' }
        foreach ($target in $targets) {
            $taskPlain | & ssh -i $taskSshKey -o BatchMode=yes -o ConnectTimeout=15 $target.HostName "$($target.Python) -B $($target.Root)/launch_one.py --auth-only"
            if ($LASTEXITCODE -ne 0) { throw 'One host failed authentication/connectivity. No solver started.' }
        }
        & ssh -i $taskSshKey -o BatchMode=yes -o ConnectTimeout=15 'lizh639@172.16.108.236' "$collegePython -B $collegeRoot/taco/relay_receiver.py --start"
        if ($LASTEXITCODE -ne 0) { throw 'Grading receiver failed to start. No solver started.' }
        Start-Process -FilePath $taskPython -ArgumentList @('-B',('"'+(Join-Path $PSScriptRoot 'relay.py')+'"')) -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $PSScriptRoot 'relay.log') -RedirectStandardError (Join-Path $PSScriptRoot 'relay-stderr.log')
        foreach ($target in $targets) {
            $taskPlain | & ssh -i $taskSshKey -o BatchMode=yes -o ConnectTimeout=15 $target.HostName "$($target.Python) -B $($target.Root)/launch_one.py"
            if ($LASTEXITCODE -ne 0) { throw 'Partial launch possible. Inspect current status; do not blindly rerun.' }
        }
        Write-Host 'Started. Keep this PC online for TACO grading relay; solvers run remotely.' -ForegroundColor Green
    } finally {
        $taskPlain=$null
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($taskPointer)
        $taskSecret.Dispose()
    }
} catch { Write-Host $_.Exception.Message -ForegroundColor Red }
Read-Host 'Press Enter to close'
