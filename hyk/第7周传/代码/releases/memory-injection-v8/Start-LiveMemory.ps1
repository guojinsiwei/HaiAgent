param([string]$Model='deepseek-flash')
$ErrorActionPreference='Stop'
if ($Model -notmatch '^[A-Za-z0-9._/-]+$') { throw 'Invalid model name' }
$microRemote='lizh639@172.16.108.236'
$microRemoteDirectory='/var/tmp/lizh639-memory-live-bMpgaM'
$microPython='/mnt/sdb/home/lizh639/terminalbench-v14-setup/runtime/bin/python'
$microSshKey=Join-Path $env:USERPROFILE '.ssh\cubestudio_notebook'
$microLocalResults=Join-Path $PSScriptRoot 'evidence\live-memory-bMpgaM'
if (Test-Path -LiteralPath $microLocalResults) { throw 'Local results already exist; do not overwrite/restart' }
& ssh -i $microSshKey -o BatchMode=yes -o ConnectTimeout=15 $microRemote "$microPython -B $microRemoteDirectory/microtests/preflight_live.py"
if ($LASTEXITCODE -ne 0) { throw 'Preflight failed; no key was requested' }
Write-Host 'Three paired toy cases. Two initial failures per run are scripted; subsequent actions use the real model.'
Write-Host 'The key goes through encrypted SSH stdin, not command arguments, files or logs.'
$microSecret=Read-Host 'DeepSeek API key (hidden)' -AsSecureString
$microPointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($microSecret)
try {
    $microPlain=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($microPointer).Trim()
    if (-not $microPlain -or $microPlain -match '\s') { throw 'Invalid key' }
    $microPlain | & ssh -i $microSshKey -o BatchMode=yes -o ConnectTimeout=15 $microRemote "$microPython -B $microRemoteDirectory/microtests/run_live_memory.py --key-stdin --model $Model"
    $microExit=$LASTEXITCODE
} finally {
    $microPlain=$null
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($microPointer)
    $microSecret.Dispose()
}
& scp -r -i $microSshKey -o BatchMode=yes "${microRemote}:$microRemoteDirectory/evidence/live-memory" $microLocalResults
if ($LASTEXITCODE -ne 0) { throw 'Could not retrieve results; server evidence is preserved' }
if ($microExit -ne 0) { throw "Worker stopped (exit $microExit); inspect retrieved redacted logs, do not restart blindly" }
Write-Host "Completed. Evidence: $microLocalResults"
