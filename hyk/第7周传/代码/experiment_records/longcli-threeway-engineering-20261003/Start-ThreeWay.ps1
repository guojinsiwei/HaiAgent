$ErrorActionPreference='Stop'
$longRoot='/mnt/lizh639/longcli-threeway-engineering-20261003'
$longPython='/mnt/lizh639/envs/swe-eval/bin/python'
$localPython='C:/Users/54177/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
$longHosts=@('cubestudio_container','cubestudio_container2')
& ssh -i 'C:/Users/54177/.ssh/cubestudio_notebook' -o BatchMode=yes -o ConnectTimeout=15 'lizh639@172.16.108.236' 'cd /var/tmp/lizh639-longcli-threeway-engineering-20261003 && /mnt/sdb/home/lizh639/terminalbench-v14-setup/runtime/bin/python -B validate_college.py'
if ($LASTEXITCODE -ne 0) { throw 'Independent grading acceptance gate failed; no credential requested' }
foreach ($longHost in $longHosts) {
    & ssh -o BatchMode=yes -o ConnectTimeout=15 $longHost "cd $longRoot && $longPython -B validate.py"
    if ($LASTEXITCODE -ne 0) { throw 'Source/acceptance gate failed; no credential requested' }
}
Write-Host 'LongCLI: frozen v6.1 / your orthogonal v8 / plain RAW, each original 10 tasks, 30 fresh trials.'
Write-Host 'Two workers; shared strict JSON wire; original budgets. No old results or credentials reused.'
$longSecret=Read-Host 'DeepSeek API key (hidden)' -AsSecureString
$longPointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($longSecret)
try {
    $longPlain=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($longPointer).Trim()
    if (-not $longPlain -or $longPlain -match '\s') { throw 'Invalid key' }
    for ($longWorker=0;$longWorker -lt 2;$longWorker++) {
        $longPlain | & ssh -o BatchMode=yes -o ConnectTimeout=15 $longHosts[$longWorker] "$longPython -B $longRoot/launch.py --worker $longWorker --check-only"
        if ($LASTEXITCODE -ne 0) { throw 'Authentication/network check failed; no new worker launched' }
    }
    for ($longWorker=0;$longWorker -lt 2;$longWorker++) {
        $longPlain | & ssh -o BatchMode=yes -o ConnectTimeout=15 $longHosts[$longWorker] "$longPython -B $longRoot/launch.py --worker $longWorker"
        if ($LASTEXITCODE -ne 0) { throw 'Launch incomplete: inspect both hosts before retrying' }
    }
    Start-Process -FilePath $localPython -ArgumentList @('-B',('"'+(Join-Path $PSScriptRoot 'relay_v2.py')+'"')) -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $PSScriptRoot 'relay.log') -RedirectStandardError (Join-Path $PSScriptRoot 'relay-stderr.log')
    Write-Host 'Workers launched. Keep this computer online for independent grading relay.'
} finally {
    $longPlain=$null
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($longPointer)
    $longSecret.Dispose()
}
