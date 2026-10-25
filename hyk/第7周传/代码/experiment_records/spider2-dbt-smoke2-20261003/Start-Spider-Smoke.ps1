$ErrorActionPreference='Stop'
$campaignRoot='/mnt/lizh639/spider2-dbt-smoke2-20261003'
$collegeRoot='/var/tmp/lizh639-spider2-dbt-smoke2-20261003'
$remotePython='/mnt/lizh639/envs/swe-eval/bin/python'
$collegePython="$collegeRoot/runtime/bin/python"
$localPython='C:/Users/54177/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
$sshKey='C:/Users/54177/.ssh/cubestudio_notebook'
$college='lizh639@172.16.108.236'
$cube='root@172.16.108.241'
$ports=@(31081)
$proxy="ProxyCommand=ssh -i $sshKey -o BatchMode=yes -o ConnectTimeout=15 -W %h:%p $college"

& ssh -i $sshKey -o BatchMode=yes -o ConnectTimeout=15 $college "cd $collegeRoot && $collegePython -B validate_college.py"
if ($LASTEXITCODE -ne 0) { throw 'Independent grader validation failed; no credential requested' }
for ($worker=0;$worker -lt 1;$worker++) {
    & ssh -i $sshKey -p $ports[$worker] -o BatchMode=yes -o ConnectTimeout=15 -o $proxy $cube "cd $campaignRoot && $remotePython -B validate.py"
    if ($LASTEXITCODE -ne 0) { throw 'Solver validation failed; no credential requested' }
}
Write-Host 'Spider2-DBT: asset001 and asana001, repaired orthogonal v8, prediction OFF.'
Write-Host 'Two sequential trials, 200 tools / 400 turns / 1 hour each, CPUs 8-9.'
$secret=Read-Host 'DeepSeek API key (hidden)' -AsSecureString
$pointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
try {
    $plain=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer).Trim()
    if (-not $plain -or $plain -match '\s') { throw 'Invalid key' }
    for ($worker=0;$worker -lt 1;$worker++) {
        $plain | & ssh -i $sshKey -p $ports[$worker] -o BatchMode=yes -o ConnectTimeout=15 -o $proxy $cube "$remotePython -B $campaignRoot/launch.py --worker $worker --check-only"
        if ($LASTEXITCODE -ne 0) { throw 'Credential/network check failed; no worker launched' }
    }
    for ($worker=0;$worker -lt 1;$worker++) {
        $plain | & ssh -i $sshKey -p $ports[$worker] -o BatchMode=yes -o ConnectTimeout=15 -o $proxy $cube "$remotePython -B $campaignRoot/launch.py --worker $worker"
        if ($LASTEXITCODE -ne 0) { throw 'Launch incomplete; inspect worker state before retrying' }
    }
    Start-Process -FilePath $localPython -ArgumentList @('-B',('"'+(Join-Path $PSScriptRoot 'relay.py')+'"')) -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $PSScriptRoot 'relay.log') -RedirectStandardError (Join-Path $PSScriptRoot 'relay-stderr.log')
    Write-Host 'Spider worker launched. Local Python relay will collect and officially grade both databases.'
} finally {
    $plain=$null
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    $secret.Dispose()
}
