$ErrorActionPreference = 'Stop'
$runRoot = '/mnt/lizh639/longcli-v6-raw-paired10-20261001'
$runPython = '/mnt/lizh639/envs/swe-eval/bin/python'
$localPython = 'C:/Users/54177/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
$hosts = @('cubestudio_container', 'cubestudio_container2')
$secureKey = Read-Host 'DeepSeek API key (hidden; never saved locally)' -AsSecureString
$pointer = [IntPtr]::Zero
try {
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
    $trialKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    # Check BOTH hosts first. /models checks authentication, with no generation charge.
    for ($worker = 0; $worker -lt 2; $worker++) {
        $trialKey | & ssh -o BatchMode=yes $hosts[$worker] "$runPython -B $runRoot/launch.py --worker $worker --check-only"
        if ($LASTEXITCODE -ne 0) { throw 'Preflight failed; no worker launched.' }
    }
    for ($worker = 0; $worker -lt 2; $worker++) {
        $trialKey | & ssh -o BatchMode=yes $hosts[$worker] "$runPython -B $runRoot/launch.py --worker $worker"
        if ($LASTEXITCODE -ne 0) { throw "Worker $worker launch failed. Inspect status before retrying; the other worker may already be running." }
    }
    Start-Process -FilePath $localPython -ArgumentList @('-B', ('"' + (Join-Path $PSScriptRoot 'relay.py') + '"')) -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $PSScriptRoot 'relay.log') -RedirectStandardError (Join-Path $PSScriptRoot 'relay-stderr.log')
    Write-Host 'Both workers started: 10 v6 + 10 RAW. Keep this computer online for artifact relay/grading.'
} finally {
    $trialKey = $null
    if ($pointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
    $secureKey.Dispose()
}
