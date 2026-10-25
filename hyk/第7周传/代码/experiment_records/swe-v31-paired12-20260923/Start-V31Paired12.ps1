param(
    [ValidateSet(0, 1)]
    [int[]]$Worker = @(0, 1)
)
$ErrorActionPreference = 'Stop'
$aliases = @('cubestudio_container', 'cubestudio_container2')
$defaultBaseUrl = 'https://ws-h0e5tm7nwwej9gk9.cn-beijing.maas.aliyuncs.com/compatible-mode/v1'
$baseUrl = Read-Host "Alibaba Model Studio Base URL [$defaultBaseUrl]"
if (-not $baseUrl) { $baseUrl = $defaultBaseUrl }
if ($baseUrl -match 'YOUR_WORKSPACE_ID') { throw 'Replace YOUR_WORKSPACE_ID with the Base URL shown by Model Studio.' }
$secret = Read-Host 'Alibaba Model Studio API Key (hidden)' -AsSecureString
$pointer = [IntPtr]::Zero
try {
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
    $rawKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    $matches = [regex]::Matches($rawKey, 'sk-[A-Za-z0-9._-]+')
    if ($matches.Count -ne 1) { throw 'Could not find exactly one API key; nothing started. Use the copy button beside the key and try again.' }
    $apiKey = $matches[0].Value
    $payload = @{ key = $apiKey; base_url = $baseUrl } | ConvertTo-Json -Compress
    foreach ($index in ($Worker | Select-Object -Unique)) {
        $remote = "/mnt/lizh639/envs/bestfgs/bin/python /mnt/lizh639/swe-v31-paired12-setup-20260923/remote_v31.py launch --index $index"
        $payload | & ssh -o BatchMode=yes -o ConnectTimeout=15 $aliases[$index] $remote
        if ($LASTEXITCODE -ne 0) { throw "Worker $index did not launch. Do not rerun worker 0; inspect status first." }
    }
    Write-Host 'Requested workers launched. The experiment continues while the CubeStudio containers remain running.'
} finally {
    if ($pointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
    $apiKey = $null
    $rawKey = $null
    $matches = $null
    $payload = $null
    if ($secret) { $secret.Dispose() }
}
