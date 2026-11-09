param()
$ErrorActionPreference='Stop'
$Host.UI.RawUI.WindowTitle='LATS six-task repair - secure API key input'
$taskRoot='/var/tmp/lizh639-lats-recovery3-six-20261008'
$taskPython='/mnt/sdb/home/lizh639/terminalbench-v14-setup/runtime/bin/python'
$taskSshKey='C:/Users/54177/.ssh/cubestudio_notebook'
$taskHost='lizh639@172.16.108.236'
try {
    Write-Host 'ONLY the six failed LATS tasks. 14 graded tasks preserved. TACO and DH unchanged.'
    Write-Host 'Concurrency 6. Original model, request/tool budgets, wall time and official grader.'
    Write-Host 'Timeout normalization + one-extra-JSON-brace repair; no search algorithm changes.'
    & ssh -i $taskSshKey -o BatchMode=yes -o ConnectTimeout=15 $taskHost "$taskPython -B $taskRoot/launch_one.py --check"
    if ($LASTEXITCODE -ne 0) { throw 'Readiness failed; no tasks started. Inspect before retrying.' }
    $taskSecret=Read-Host 'Enter DeepSeek API key (hidden; do not send it in chat)' -AsSecureString
    $taskPointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($taskSecret)
    try {
        $taskPlain=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($taskPointer).Trim()
        if (-not $taskPlain -or $taskPlain -match '\s') { throw 'Invalid credential.' }
        $taskPlain | & ssh -i $taskSshKey -o BatchMode=yes -o ConnectTimeout=15 $taskHost "$taskPython -B $taskRoot/launch_one.py"
        if ($LASTEXITCODE -ne 0) { throw 'Launch uncertain. Inspect server status before retrying.' }
        Write-Host 'Started. Solvers and official grading continue on the college server.' -ForegroundColor Green
    } finally {
        $taskPlain=$null
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($taskPointer)
        $taskSecret.Dispose()
    }
} catch { Write-Host $_.Exception.Message -ForegroundColor Red }
Read-Host 'Press Enter to close'
