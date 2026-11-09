$ErrorActionPreference='Stop'
$sshKey='C:/Users/54177/.ssh/cubestudio_notebook'
$campaign='/var/tmp/lizh639-longcli-retrac-recovery3-20261007'
$remotePython="$campaign/runtime/bin/python"
$Host.UI.RawUI.WindowTitle='Re-TRAC repaired: remaining 16 tasks'
Write-Host 'Retain Hog, Util, Scheme and Ants deliveries. Only 16 unfinished tasks.'
Write-Host 'Bounded memory serialization; same 8 rounds, model, request/tool/time budgets.'
Write-Host 'Canaries: CMU p1 and Cats. Four-worker admission only after both pass.'
& ssh -i $sshKey -o BatchMode=yes -o ConnectTimeout=15 lizh639@172.16.108.236 "$remotePython -B $campaign/check_ready.py"
if ($LASTEXITCODE -ne 0) { throw 'Acceptance failed. Not started.' }
& ssh -i $sshKey -o BatchMode=yes -o ConnectTimeout=15 lizh639@172.16.108.236 "test ! -e $campaign/launch.claim"
if ($LASTEXITCODE -ne 0) { throw 'Existing launch or uncertain connection: inspect before retrying.' }
$secret=Read-Host 'Enter API key locally (hidden; do not paste into chat)' -AsSecureString
$pointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
try {
    $plain=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer).Trim()
    if (-not $plain -or $plain -match '\s') { throw 'Invalid key' }
    $plain | & ssh -i $sshKey -o BatchMode=yes -o ConnectTimeout=15 lizh639@172.16.108.236 "$remotePython -B $campaign/launch.py --check-only"
    if ($LASTEXITCODE -ne 0) { throw 'Preflight failed. No experiment started.' }
    $plain | & ssh -i $sshKey -o BatchMode=yes -o ConnectTimeout=15 lizh639@172.16.108.236 "$remotePython -B $campaign/launch.py"
    if ($LASTEXITCODE -ne 0) { throw 'Launch uncertain. Inspect public health before retrying.' }
    Write-Host 'Submitted. Automatic engineering fail-fast and official grading enabled.'
} finally {
    $plain=$null
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    $secret.Dispose()
}
Read-Host 'Press Enter to close'
