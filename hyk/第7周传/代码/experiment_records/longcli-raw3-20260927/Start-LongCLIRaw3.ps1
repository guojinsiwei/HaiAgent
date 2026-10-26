$ErrorActionPreference = 'Stop'
$longcliDir = '/mnt/lizh639/longcli-raw3-20260927'
& ssh -o BatchMode=yes -o ConnectTimeout=15 cubestudio_container "test -f $longcliDir/ready.json"
if ($LASTEXITCODE -ne 0) { throw 'Cloud preparation is not ready; no model calls started.' }
$longcliSecret = Read-Host 'DeepSeek API Key (hidden; LongCLI Raw 3 tasks only)' -AsSecureString
$longcliPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($longcliSecret)
try {
    $longcliPlain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($longcliPointer).Trim()
    if (-not $longcliPlain -or $longcliPlain -match '\s') { throw 'Invalid key; nothing started.' }
    $longcliPlain | & ssh -o BatchMode=yes -o ConnectTimeout=15 cubestudio_container "cd $longcliDir && /mnt/lizh639/envs/swe-eval/bin/python -B launch.py"
    if ($LASTEXITCODE -ne 0) { throw 'Launch not confirmed. Do not blindly rerun; inspect status first.' }
} finally {
    $longcliPlain = $null
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($longcliPointer)
}
