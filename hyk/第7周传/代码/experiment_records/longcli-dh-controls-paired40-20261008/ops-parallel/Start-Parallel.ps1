$ErrorActionPreference='Stop'
$Host.UI.RawUI.WindowTitle='DH PARALLEL 6+6 - preserve running tasks - secure key input'
$parallelRoot='/mnt/sdb/home/lizh639/longcli-dh-controls-paired40-20261008/ops-parallel'
$parallelPython='/mnt/sdb/home/lizh639/terminalbench-v14-setup/runtime/bin/python'
$parallelHost='lizh639@172.16.108.236'
$parallelKey='C:/Users/54177/.ssh/cubestudio_notebook'
try {
    Write-Host 'Remove first-task completion gate; max6 tools + max6 no-tools.'
    Write-Host 'Keep running trials and grader. No task restart, no algorithm or budget change.'
    & ssh -n -i $parallelKey -o BatchMode=yes -o ConnectTimeout=15 $parallelHost "$parallelPython -B $parallelRoot/launch_parallel.py --check"
    if($LASTEXITCODE -ne 0){throw 'Readiness failed; existing tasks remain running.'}
    $parallelSecret=Read-Host 'DeepSeek key (hidden; never send in chat)' -AsSecureString
    $parallelPointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($parallelSecret)
    try {
        $parallelPlain=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($parallelPointer).Trim()
        if(-not $parallelPlain -or $parallelPlain -match '\s'){throw 'Invalid empty or whitespace credential.'}
        $parallelPlain | & ssh -i $parallelKey -o BatchMode=yes -o ConnectTimeout=15 $parallelHost "$parallelPython -B $parallelRoot/launch_parallel.py"
        if($LASTEXITCODE -ne 0){throw 'Handoff launch failed; inspect public status before retrying.'}
        Write-Host 'Parallel handoff started; waiting tasks will fill existing free slots.' -ForegroundColor Green
    } finally {
        $parallelPlain=$null
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($parallelPointer)
        $parallelSecret.Dispose()
    }
} catch {Write-Host $_.Exception.Message -ForegroundColor Red}
Read-Host 'Press Enter to close'
