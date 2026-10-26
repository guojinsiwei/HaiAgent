param(
    [ValidateSet(0, 1)]
    [int[]]$Worker = @(0, 1)
)
$ErrorActionPreference = 'Stop'
$aliases = @('cubestudio_container', 'cubestudio_container2')
$secret = Read-Host 'DeepSeek API Key (hidden; used only for this four-task run)' -AsSecureString
$pointer = [IntPtr]::Zero
try {
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
    $apiKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer).Trim()
    if (-not $apiKey -or $apiKey -match '\s') { throw 'Invalid key format; nothing started.' }
    $payload = @{ key = $apiKey } | ConvertTo-Json -Compress
    foreach ($index in ($Worker | Select-Object -Unique)) {
        $remoteCommand = 'env PATH=/mnt/lizh639/envs/bestfgs/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin PYTHONDONTWRITEBYTECODE=1 /mnt/lizh639/envs/bestfgs/bin/python /mnt/lizh639/notebook-tools/remote_smoke.py launch --index ' + $index + ' --credential-stdin'
        Write-Host ('Checking and launching worker {0}: {1}' -f $index, $aliases[$index])
        # Key goes through encrypted SSH stdin, never shell arguments or a file.
        $payload | & ssh -o BatchMode=yes -o ConnectTimeout=15 $aliases[$index] $remoteCommand
        if ($LASTEXITCODE -ne 0) {
            throw ('Worker {0} did not confirm launch. Do not rerun already launched workers; inspect status first.' -f $index)
        }
    }
    Write-Host 'Both requested launch operations completed. The remote workers continue after this computer disconnects, while the containers remain running.'
} finally {
    if ($pointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
    $apiKey = $null
    $payload = $null
    if ($secret) { $secret.Dispose() }
}
