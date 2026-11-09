$ErrorActionPreference='Stop'
$sshKey='C:/Users/54177/.ssh/cubestudio_notebook'
$campaign='/var/tmp/lizh639-longcli-retrac-recovery2-20261007'
$remotePython="$campaign/runtime/bin/python"
$Host.UI.RawUI.WindowTitle='Re-TRAC repaired: 18 unfinished tasks'
Write-Host 'Only the 18 unfinished Re-TRAC tasks. Previous Hog/Util results are retained.'
Write-Host 'Same model, same algorithm and budgets. Two canaries, then four workers.'
& ssh -i $sshKey -o BatchMode=yes -o ConnectTimeout=15 lizh639@172.16.108.236 "$remotePython -B $campaign/check_ready.py"
if ($LASTEXITCODE -ne 0) { throw 'Acceptance check failed. Not started.' }
& ssh -i $sshKey -o BatchMode=yes -o ConnectTimeout=15 lizh639@172.16.108.236 "test ! -e $campaign/launch.claim"
if ($LASTEXITCODE -ne 0) { throw 'Launch claim exists or connection is uncertain. Inspect before retrying.' }
$secret=Read-Host 'Enter NEW API key locally (hidden; do not paste into chat)' -AsSecureString
$pointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
try {
    $plain=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer).Trim()
    if (-not $plain -or $plain -match '\s') { throw 'Invalid key' }
    $plain | & ssh -i $sshKey -o BatchMode=yes -o ConnectTimeout=15 lizh639@172.16.108.236 "$remotePython -B $campaign/launch.py --check-only"
    if ($LASTEXITCODE -ne 0) { throw 'Preflight failed. No experiment started.' }
    $plain | & ssh -i $sshKey -o BatchMode=yes -o ConnectTimeout=15 lizh639@172.16.108.236 "$remotePython -B $campaign/launch.py"
    if ($LASTEXITCODE -ne 0) { throw 'Launch uncertain. Inspect public health before retrying.' }
    Write-Host 'Launch submitted. Engineering fail-fast and model-free official scoring enabled.'
} finally {
    $plain=$null
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    $secret.Dispose()
}
Read-Host 'Press Enter to close'
