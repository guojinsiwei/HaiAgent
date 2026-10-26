$ErrorActionPreference = 'Stop'
$keyPath = Join-Path $env:USERPROFILE 'Desktop\_terminalbench-20260923.pem'
if (-not (Test-Path -LiteralPath $keyPath)) { throw 'ECS SSH private key not found on Desktop.' }
$sshArgs = @('-F','NUL','-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','ConnectTimeout=12','-i',$keyPath,'ecs-user@114.215.186.90')
$control = '/home/ecs-user/terminalbench-setup-20260923-extended-v1/paired_control.py'
$python = '/home/ecs-user/terminalbench-runtime/venv/bin/python'
& ssh @sshArgs "sudo env HARBOR_TELEMETRY=0 PYTHONPATH=/home/ecs-user/terminalbench-setup-20260923-extended-v1 $python $control validate"
if ($LASTEXITCODE -ne 0) { throw 'Extended protocol is not ready. No key requested and no experiment started.' }
$secureKey = Read-Host 'DeepSeek API Key (hidden; sent only to your ECS over SSH)' -AsSecureString
$keyPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
try {
    $plainKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($keyPointer)
    $plainKey | & ssh @sshArgs "sudo env HARBOR_TELEMETRY=0 PYTHONPATH=/home/ecs-user/terminalbench-setup-20260923-extended-v1 $python $control start"
    if ($LASTEXITCODE -ne 0) { throw 'Launch was not confirmed. Check the extended cloud status before retrying.' }
} finally {
    $plainKey = $null
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($keyPointer)
    $secureKey.Dispose()
}
& ssh @sshArgs "sudo env HARBOR_TELEMETRY=0 PYTHONPATH=/home/ecs-user/terminalbench-setup-20260923-extended-v1 $python $control status"
