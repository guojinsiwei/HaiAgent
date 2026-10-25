param(
    [ValidateSet(0, 1)]
    [int[]]$Worker = @(0, 1)
)
$ErrorActionPreference = 'Stop'
$aliases = @('cubestudio_container', 'cubestudio_container2')
$secret = Read-Host 'DeepSeek API Key (hidden; current BestFGS 50-task run)' -AsSecureString
$pointer = [IntPtr]::Zero
try {
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
    $apiKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer).Trim()
    if (-not $apiKey -or $apiKey -match '\s') { throw 'Invalid key format; nothing started.' }
    $payload = @{ key = $apiKey } | ConvertTo-Json -Compress
    foreach ($index in ($Worker | Select-Object -Unique)) {
        $remote = 'env PATH=/mnt/lizh639/envs/bestfgs/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin PYTHONDONTWRITEBYTECODE=1 /mnt/lizh639/envs/bestfgs/bin/python /mnt/lizh639/notebook-tools/remote_current50.py launch --index ' + $index + ' --credential-stdin'
        Write-Host ('Preflighting and launching worker {0}: {1}' -f $index, $aliases[$index])
        $payload | & ssh -o BatchMode=yes -o ConnectTimeout=15 $aliases[$index] $remote
        if ($LASTEXITCODE -ne 0) {
            throw ('Worker {0} did not confirm launch. Inspect status; never relaunch an already-started worker.' -f $index)
        }
    }
    Write-Host 'Requested workers launched in remote tmux. Closing this PC does not stop them while containers remain alive.'
} finally {
    if ($pointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
    $apiKey = $null
    $payload = $null
    if ($secret) { $secret.Dispose() }
}
