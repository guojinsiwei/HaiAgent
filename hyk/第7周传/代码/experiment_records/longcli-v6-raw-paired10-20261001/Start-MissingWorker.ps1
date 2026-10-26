$ErrorActionPreference = 'Stop'
$runRoot = '/mnt/lizh639/longcli-v6-raw-paired10-20261001'
$runPython = '/mnt/lizh639/envs/swe-eval/bin/python'
$targetHost = 'cubestudio_container2'
& ssh -o BatchMode=yes $targetHost "test ! -f $runRoot/health-1.json"
if ($LASTEXITCODE -ne 0) { throw 'Worker 1 already claimed or host unavailable. Inspect status; do not relaunch.' }
$secureKey = Read-Host 'DeepSeek API key (hidden; start missing worker 1 only)' -AsSecureString
$pointer = [IntPtr]::Zero
try {
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
    $trialKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    $trialKey | & ssh -o BatchMode=yes $targetHost "$runPython -B $runRoot/launch.py --worker 1"
    if ($LASTEXITCODE -ne 0) { throw 'Worker 1 launch unconfirmed. Inspect health-1.json before retrying.' }
    Write-Host 'Missing worker started. Worker 0 was not restarted; relay is managed separately.'
} finally {
    $trialKey = $null
    if ($pointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
    $secureKey.Dispose()
}
