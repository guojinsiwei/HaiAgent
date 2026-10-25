$ErrorActionPreference='Stop'
$Host.UI.RawUI.WindowTitle='DH / RAW - Full LongCLI (40 trials)'
$campaignRoot='/mnt/lizh639/longcli-dh-raw-full20-20261004'
$collegeRoot='/var/tmp/lizh639-longcli-dh-raw-full20-20261004'
$remotePython='/mnt/lizh639/envs/swe-eval/bin/python'
$collegePython='/mnt/sdb/home/lizh639/terminalbench-v14-setup/runtime/bin/python'
$localPython='C:/Users/54177/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
$sshKey='C:/Users/54177/.ssh/cubestudio_notebook'
$college='lizh639@172.16.108.236'
$cube='root@172.16.108.241'
$ports=@(31081,31121)
$proxy="ProxyCommand=ssh -i $sshKey -o BatchMode=yes -o ConnectTimeout=15 -W %h:%p $college"

& ssh -i $sshKey -o BatchMode=yes -o ConnectTimeout=15 $college "cd $collegeRoot && $collegePython -B validate_college.py"
if ($LASTEXITCODE -ne 0) { throw 'Independent grading validation failed' }
for ($worker=0;$worker -lt 2;$worker++) {
    & ssh -i $sshKey -p $ports[$worker] -o BatchMode=yes -o ConnectTimeout=15 -o $proxy $cube "cd $campaignRoot && $remotePython -B validate.py"
    if ($LASTEXITCODE -ne 0) { throw 'Solver acceptance failed' }
}
Write-Host 'DH versus RAW: 20 LongCLI tasks per arm, 40 fresh trials.'
Write-Host 'Two containers, 2 slots each. Per task: 800 logical requests / 600 tools.'
Write-Host 'DH=v9+recovery counter repair; predictions disabled.'
Write-Host 'Keep this computer online for automatic official grading and result return.'
$secret=Read-Host 'DeepSeek API key (hidden; do not paste it into chat)' -AsSecureString
$pointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
try {
    $plain=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer).Trim()
    if (-not $plain -or $plain -match '\s') { throw 'Invalid key' }
    for ($worker=0;$worker -lt 2;$worker++) {
        $plain | & ssh -i $sshKey -p $ports[$worker] -o BatchMode=yes -o ConnectTimeout=15 -o $proxy $cube "$remotePython -B $campaignRoot/launch.py --worker $worker --check-only"
        if ($LASTEXITCODE -ne 0) { throw 'Credential/model preflight failed; no worker launched' }
    }
    for ($worker=0;$worker -lt 2;$worker++) {
        $plain | & ssh -i $sshKey -p $ports[$worker] -o BatchMode=yes -o ConnectTimeout=15 -o $proxy $cube "$remotePython -B $campaignRoot/launch.py --worker $worker"
        if ($LASTEXITCODE -ne 0) { throw 'Partial launch; inspect public status before any retry' }
    }
    $relayProcess=Start-Process -FilePath $localPython -ArgumentList @('-B',('"'+(Join-Path $PSScriptRoot 'relay.py')+'"')) -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $PSScriptRoot 'relay.log') -RedirectStandardError (Join-Path $PSScriptRoot 'relay-stderr.log') -PassThru
    Start-Sleep -Seconds 2
    if ($relayProcess.HasExited) { throw 'Workers started but result relay exited; inspect relay-stderr.log' }
    @{workers_launched=2;tasks_per_arm=20;trials=40;concurrency=4;relay_pid=$relayProcess.Id;updated=(Get-Date).ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'local-launch-status.json') -Encoding UTF8
    Write-Host 'Both workers started. Automatic scoring and result return enabled.'
} finally {
    $plain=$null
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    $secret.Dispose()
}
