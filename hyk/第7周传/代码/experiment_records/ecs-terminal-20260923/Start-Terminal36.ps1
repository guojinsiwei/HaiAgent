$ErrorActionPreference = 'Stop'
$keyPath = Join-Path $env:USERPROFILE 'Desktop\_terminalbench-20260923.pem'
if (-not (Test-Path -LiteralPath $keyPath)) { throw 'ECS SSH private key not found on Desktop.' }
$sshArgs = @('-F','NUL','-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','ConnectTimeout=12','-i',$keyPath,'ecs-user@114.215.186.90')
& ssh @sshArgs 'sudo env HARBOR_TELEMETRY=0 /home/ecs-user/terminalbench-runtime/venv/bin/python /home/ecs-user/terminalbench-setup-20260923/paired_control.py validate'
if ($LASTEXITCODE -ne 0) { throw 'Cloud preparation/protocol is not ready. No key requested and no experiment started.' }
$secureKey = Read-Host 'DeepSeek API Key (hidden; sent only to your ECS over SSH)' -AsSecureString
$keyPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
try {
    $plainKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($keyPointer)
    $plainKey | & ssh @sshArgs 'sudo env HARBOR_TELEMETRY=0 /home/ecs-user/terminalbench-runtime/venv/bin/python /home/ecs-user/terminalbench-setup-20260923/paired_control.py start'
    if ($LASTEXITCODE -ne 0) { throw 'Launch was not confirmed. Check cloud status before retrying.' }
} finally {
    $plainKey = $null
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($keyPointer)
    $secureKey.Dispose()
}
& ssh @sshArgs 'sudo env HARBOR_TELEMETRY=0 /home/ecs-user/terminalbench-runtime/venv/bin/python /home/ecs-user/terminalbench-setup-20260923/paired_control.py status'
