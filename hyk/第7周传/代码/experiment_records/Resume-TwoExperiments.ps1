$ErrorActionPreference = 'Stop'
$experimentTargets = @(
    @{ Name = 'College LHTB'; HostName = 'lizh639@172.16.108.236'; Identity = "$env:USERPROFILE\.ssh\cubestudio_notebook"; Directory = '/mnt/sdb/home/lizh639/lhtb-triple12-v161-20260927-r3'; Python = '/mnt/sdb/home/lizh639/terminalbench-v14-setup/runtime/bin/python' },
    @{ Name = 'Cube LongCLI Raw3'; HostName = 'cubestudio_container'; Identity = $null; Directory = '/mnt/lizh639/longcli-raw3-20260927-r3'; Python = '/mnt/lizh639/envs/swe-eval/bin/python' }
)
$experimentPending = @()
foreach ($experimentTarget in $experimentTargets) {
    $experimentSshArgs = @('-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15')
    if ($experimentTarget.Identity) { $experimentSshArgs += @('-i', $experimentTarget.Identity) }
    $experimentSshArgs += $experimentTarget.HostName
    $experimentTarget.SshArgs = $experimentSshArgs
    $experimentSnapshot = & ssh @experimentSshArgs "cd $($experimentTarget.Directory) && if test -f health.json; then cat health.json; else test -f ready.json && echo not_started; fi"
    if ($LASTEXITCODE -ne 0) { throw "$($experimentTarget.Name): connection/readiness failed; nothing newly started." }
    $experimentText = ($experimentSnapshot -join "`n").Trim()
    if ($experimentText -eq 'not_started') {
        $experimentPending += $experimentTarget
    } else {
        $experimentHealth = $experimentText | ConvertFrom-Json
        if ($experimentHealth.state -notin @('running', 'waiting_for_disk', 'completed')) {
            throw "$($experimentTarget.Name): existing state $($experimentHealth.state); inspect, do not restart blindly."
        }
        Write-Host "$($experimentTarget.Name): already $($experimentHealth.state); skipping duplicate launch."
    }
}
if ($experimentPending.Count -eq 0) { Write-Host 'Both experiments already started; no API key needed.'; return }
$experimentSecret = Read-Host 'DeepSeek API Key (hidden; college first, then Cube; entered once)' -AsSecureString
$experimentPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($experimentSecret)
try {
    $experimentPlain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($experimentPointer).Trim()
    if (-not $experimentPlain -or $experimentPlain -match '\s') { throw 'Invalid key; nothing newly started.' }
    foreach ($experimentTarget in $experimentPending) {
        Write-Host "Launching $($experimentTarget.Name)"
        $experimentSshArgs = $experimentTarget.SshArgs
        $experimentReply = $experimentPlain | & ssh @experimentSshArgs "cd $($experimentTarget.Directory) && $($experimentTarget.Python) -B launch.py"
        $experimentExit = $LASTEXITCODE
        $experimentReply | Write-Host
        if ($experimentExit -ne 0) { throw "$($experimentTarget.Name): launch not confirmed; inspect status." }
        $experimentLaunch = ($experimentReply -join "`n") | ConvertFrom-Json
        if ($experimentLaunch.launched -ne $true) { throw "$($experimentTarget.Name): heartbeat not running; inspect status." }
    }
} finally {
    $experimentPlain = $null
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($experimentPointer)
    $experimentSecret.Dispose()
}
