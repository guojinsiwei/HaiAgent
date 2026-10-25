param()
$ErrorActionPreference='Stop'
$campaign='/mnt/lizh639/longcli-dsh20-matched-repair2-20261005'
$remotePython='/mnt/lizh639/envs/swe-eval/bin/python'
$localPython='C:/Users/54177/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
$sshKey='C:/Users/54177/.ssh/cubestudio_notebook'
$proxy="ProxyCommand=ssh -i $sshKey -o BatchMode=yes -o ConnectTimeout=15 -W %h:%p lizh639@172.16.108.236"
Write-Host 'DSH ONLY: 20 NEW LongCLI tasks; historical DH/RAW are NOT rerun.'
Write-Host 'Original Cube workers, 4 parallel tasks. Per task 800 logical requests / 600 tools.'
Write-Host '4096 output tokens, 48000 UTF-8 input bytes INCLUDING native tool schemas.'
Write-Host 'AP26/AP35: 3h. Other tasks: 2h. Every task has a fresh rootfs and DSH HOME.'
& ssh -i $sshKey -o BatchMode=yes lizh639@172.16.108.236 '/mnt/sdb/home/lizh639/terminalbench-v14-setup/runtime/bin/python -B /var/tmp/lizh639-longcli-dsh20-matched-repair2-20261005/check_grading.py'
if ($LASTEXITCODE -ne 0) { throw 'Official grading acceptance failed. No paid trial started.' }
foreach ($worker in 0,1) {
    $port= @(31081,31121)[$worker]
    & ssh -i $sshKey -p $port -o BatchMode=yes -o $proxy root@172.16.108.241 "$remotePython -B $campaign/check_ready.py --worker $worker"
    if ($LASTEXITCODE -ne 0) { throw 'Keyless acceptance failed. No paid trial started.' }
}
$secret=Read-Host 'DeepSeek API key (hidden; never paste into chat)' -AsSecureString
$pointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
try {
    $plain=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer).Trim()
    if (-not $plain -or $plain -match '\s') { throw 'Invalid key' }
    foreach ($worker in 0,1) {
        $port= @(31081,31121)[$worker]
        $plain | & ssh -i $sshKey -p $port -o BatchMode=yes -o $proxy root@172.16.108.241 "$remotePython -B $campaign/launch.py --worker $worker --check-only"
        if ($LASTEXITCODE -ne 0) { throw 'Credential/model check failed. No paid worker was launched.' }
    }
    foreach ($worker in 0,1) {
        $port= @(31081,31121)[$worker]
        $plain | & ssh -i $sshKey -p $port -o BatchMode=yes -o $proxy root@172.16.108.241 "$remotePython -B $campaign/launch.py --worker $worker"
        if ($LASTEXITCODE -ne 0) { throw "Worker $worker launch failed or uncertain. Do not relaunch; inspect public status." }
    }
    $relay=Start-Process -FilePath $localPython -ArgumentList @('-B',('"'+(Join-Path $PSScriptRoot 'relay.py')+'"')) -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $PSScriptRoot 'relay.log') -RedirectStandardError (Join-Path $PSScriptRoot 'relay-stderr.log') -PassThru
    Write-Host "Workers started. Model-free result relay PID: $($relay.Id). Keep this computer online for automatic grading/return."
} finally {
    $plain=$null
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    $secret.Dispose()
}
