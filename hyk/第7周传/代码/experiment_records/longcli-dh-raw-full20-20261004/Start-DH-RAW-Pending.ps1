$ErrorActionPreference='Stop'
$Host.UI.RawUI.WindowTitle='DH / RAW - Start only the missing container'
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
$pendingWorkers=@()

function Invoke-PublicSSH([string[]]$Arguments,[string]$Stage) {
    $savedPreference=$ErrorActionPreference
    $ErrorActionPreference='Continue'
    try { $lines=@(& ssh @Arguments 2>&1); $exitCode=$LASTEXITCODE }
    finally { $ErrorActionPreference=$savedPreference }
    $lines | ForEach-Object { $_.ToString() } | Add-Content -LiteralPath (Join-Path $PSScriptRoot 'pending-launch.log') -Encoding UTF8
    if ($exitCode -ne 0) { throw "$Stage failed (exit $exitCode); see pending-launch.log" }
    return (($lines | ForEach-Object { $_.ToString() }) -join "`n")
}

Invoke-PublicSSH -Arguments @('-i',$sshKey,'-o','BatchMode=yes','-o','ConnectTimeout=15',$college,"cd $collegeRoot && $collegePython -B validate_college.py") -Stage 'Grader validation' | Write-Host
for ($worker=0;$worker -lt 2;$worker++) {
    $stateText=Invoke-PublicSSH -Arguments @('-i',$sshKey,'-p',([string]$ports[$worker]),'-o','BatchMode=yes','-o','ConnectTimeout=15','-o',$proxy,$cube,"$remotePython -B $campaignRoot/launch_tools/launch_pending.py --worker $worker --status-only") -Stage "Worker $worker status"
    $stateLine=($stateText -split "`n" | Where-Object { $_.Trim().StartsWith('{') } | Select-Object -Last 1)
    $state=$stateLine | ConvertFrom-Json
    Write-Host "Worker $worker : $($state.state)"
    if ($state.needs_attention) { throw 'Existing launch has no confirmed heartbeat; inspection required' }
    if ($state.pending) { $pendingWorkers += $worker }
}

# The relay is independent of whether both generation workers launch successfully.
$relayRecord=Join-Path $PSScriptRoot 'relay-process.json'
$relayLive=$false
if (Test-Path -LiteralPath $relayRecord) {
    $relayState=Get-Content -LiteralPath $relayRecord -Raw | ConvertFrom-Json
    $existingRelay=Get-Process -Id $relayState.pid -ErrorAction SilentlyContinue
    $relayLive=($null -ne $existingRelay -and $existingRelay.ProcessName -eq 'python')
}
if (-not $relayLive) {
    $relayProcess=Start-Process -FilePath $localPython -ArgumentList @('-B',('"'+(Join-Path $PSScriptRoot 'relay.py')+'"')) -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $PSScriptRoot 'relay.log') -RedirectStandardError (Join-Path $PSScriptRoot 'relay-stderr.log') -PassThru
    Start-Sleep -Seconds 2
    if ($relayProcess.HasExited) { throw 'Result relay failed; inspect relay-stderr.log' }
}
if ($pendingWorkers.Count -eq 0) { Write-Host 'No missing workers. Nothing restarted.'; return }
Write-Host "Only missing worker(s) $($pendingWorkers -join ',') will start; existing tasks keep running."
$secret=Read-Host 'DeepSeek API key (hidden; do not paste it into chat)' -AsSecureString
$pointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
try {
    $plain=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer).Trim()
    if (-not $plain -or $plain -match '\s') { throw 'Invalid key' }
    foreach ($worker in $pendingWorkers) {
        $savedPreference=$ErrorActionPreference
        $ErrorActionPreference='Continue'
        try {
            $lines=@($plain | & ssh -i $sshKey -p $ports[$worker] -o BatchMode=yes -o ConnectTimeout=15 -o $proxy $cube "$remotePython -B $campaignRoot/launch_tools/launch_pending.py --worker $worker" 2>&1)
            $exitCode=$LASTEXITCODE
        } finally { $ErrorActionPreference=$savedPreference }
        $lines | ForEach-Object { $_.ToString() } | Tee-Object -FilePath (Join-Path $PSScriptRoot "pending-worker-$worker.log") | Write-Host
        if ($exitCode -ne 0) { throw "Missing worker $worker did not start; inspect pending-worker-$worker.log before retry" }
    }
    @{missing_workers_started=$pendingWorkers;trials=40;concurrency=4;updated=(Get-Date).ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'pending-launch-status.json') -Encoding UTF8
    Write-Host 'Missing workers started. Keep this computer online for automatic scoring and return.'
} finally {
    $plain=$null
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    $secret.Dispose()
}
