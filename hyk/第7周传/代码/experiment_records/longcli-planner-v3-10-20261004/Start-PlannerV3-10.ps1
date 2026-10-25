$ErrorActionPreference='Stop'
$campaignRoot='/mnt/lizh639/longcli-planner-v3-10-20261004'
$collegeRoot='/var/tmp/lizh639-longcli-planner-v3-10-20261004'
$remotePython='/mnt/lizh639/envs/swe-eval/bin/python'
$collegePython='/mnt/sdb/home/lizh639/terminalbench-v14-setup/runtime/bin/python'
$localPython='C:/Users/54177/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
$sshKey='C:/Users/54177/.ssh/cubestudio_notebook'
$college='lizh639@172.16.108.236'
$cube='root@172.16.108.241'
$ports=@(31081,31121)
$proxy="ProxyCommand=ssh -i $sshKey -o BatchMode=yes -o ConnectTimeout=15 -W %h:%p $college"

& ssh -i $sshKey -o BatchMode=yes -o ConnectTimeout=15 $college "cd $collegeRoot && $collegePython -B validate_college.py"
if ($LASTEXITCODE -ne 0) { throw 'Independent grader validation failed; no key requested' }
for ($worker=0;$worker -lt 2;$worker++) {
    & ssh -i $sshKey -p $ports[$worker] -o BatchMode=yes -o ConnectTimeout=15 -o $proxy $cube "cd $campaignRoot && $remotePython -B validate.py"
    if ($LASTEXITCODE -ne 0) { throw 'Solver validation failed; no key requested' }
}
Write-Host 'BestFGS Planner/Solver graph v3: 10 fresh LongCLI tasks, one arm.'
Write-Host 'Two containers; 2 slots each; four roles share 800 requests / 600 tools per task.'
Write-Host 'Official grading is independent. Keep this computer online for the result relay.'
$secret=Read-Host 'DeepSeek API key (hidden; do not paste it into chat)' -AsSecureString
$pointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
try {
    $plain=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer).Trim()
    if (-not $plain -or $plain -match '\s') { throw 'Invalid key' }
    for ($worker=0;$worker -lt 2;$worker++) {
        $plain | & ssh -i $sshKey -p $ports[$worker] -o BatchMode=yes -o ConnectTimeout=15 -o $proxy $cube "$remotePython -B $campaignRoot/launch.py --worker $worker --check-only"
        if ($LASTEXITCODE -ne 0) { throw 'Credential/network preflight failed; no worker launched' }
    }
    for ($worker=0;$worker -lt 2;$worker++) {
        $plain | & ssh -i $sshKey -p $ports[$worker] -o BatchMode=yes -o ConnectTimeout=15 -o $proxy $cube "$remotePython -B $campaignRoot/launch.py --worker $worker"
        if ($LASTEXITCODE -ne 0) { throw 'Launch incomplete; inspect both workers before any retry' }
    }
    $relayProcess=Start-Process -FilePath $localPython -ArgumentList @('-B',('"'+(Join-Path $PSScriptRoot 'relay.py')+'"')) -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $PSScriptRoot 'relay.log') -RedirectStandardError (Join-Path $PSScriptRoot 'relay-stderr.log') -PassThru
    Start-Sleep -Seconds 2
    if ($relayProcess.HasExited) { throw 'Workers started but relay exited; inspect relay-stderr.log' }
    @{workers_launched=2;tasks=10;concurrency=4;relay_pid=$relayProcess.Id;updated=(Get-Date).ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'local-launch-status.json') -Encoding UTF8
    Write-Host 'Both workers launched. Automatic scoring and return relay started.'
} finally {
    $plain=$null
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    $secret.Dispose()
}
