$ErrorActionPreference = 'Stop'
$longcliDir = '/mnt/lizh639/longcli-raw3-20260927-r3'
& ssh -o BatchMode=yes -o ConnectTimeout=15 cubestudio_container "test -f $longcliDir/ready.json"
if ($LASTEXITCODE -ne 0) { throw 'Repair preflight is not ready.' }
$longcliSecret = Read-Host 'DeepSeek API Key (hidden; resume existing 569 turns, then Ants and Cats)' -AsSecureString
$longcliPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($longcliSecret)
try {
    $longcliPlain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($longcliPointer).Trim()
    if (-not $longcliPlain -or $longcliPlain -match '\s') { throw 'Invalid key; nothing started.' }
    $longcliPlain | & ssh -o BatchMode=yes -o ConnectTimeout=15 cubestudio_container "cd $longcliDir && /mnt/lizh639/envs/swe-eval/bin/python -B launch.py"
    if ($LASTEXITCODE -ne 0) { throw 'Resume not confirmed. Inspect status before retrying.' }
} finally {
    $longcliPlain = $null
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($longcliPointer)
}
