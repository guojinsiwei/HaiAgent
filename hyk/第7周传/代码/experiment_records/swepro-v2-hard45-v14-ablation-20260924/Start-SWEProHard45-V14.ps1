$ErrorActionPreference = 'Stop'
$root = '/mnt/lizh639/bestfgs-runs/swepro-v2-hard45-v14-ablation-20260924'
$python = '/mnt/lizh639/envs/bestfgs/bin/python'
$control = "$root/control/paired_hard45_v14_control.py"

foreach ($hostAlias in @('cubestudio_container', 'cubestudio_container2')) {
    & ssh $hostAlias "$python $control validate"
    if ($LASTEXITCODE -ne 0) { throw "v14 ablation is not ready on $hostAlias; no key requested." }
}

$secureKey = Read-Host 'DeepSeek API Key (hidden; kept only in the two cloud guard processes)' -AsSecureString
$keyPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
try {
    $plainKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($keyPointer)
    $payload = @{ key = $plainKey } | ConvertTo-Json -Compress
    $payload | & ssh cubestudio_container "$python $control launch --index 0"
    if ($LASTEXITCODE -ne 0) { throw 'Worker 0 did not confirm launch. Inspect status; do not rerun blindly.' }
    $payload | & ssh cubestudio_container2 "$python $control launch --index 1"
    if ($LASTEXITCODE -ne 0) { throw 'Worker 1 did not confirm launch. Inspect status; do not rerun blindly.' }
} finally {
    $plainKey = $null
    $payload = $null
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($keyPointer)
    $secureKey.Dispose()
}

foreach ($hostAlias in @('cubestudio_container', 'cubestudio_container2')) {
    & ssh $hostAlias "$python $control status"
}
