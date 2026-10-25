$ErrorActionPreference = 'Stop'
$keyPath = Join-Path $env:USERPROFILE 'Desktop\_terminalbench-20260923.pem'
& ssh -F NUL -o BatchMode=yes -o IdentitiesOnly=yes -o ConnectTimeout=12 -i $keyPath ecs-user@114.215.186.90 'sudo env HARBOR_TELEMETRY=0 /home/ecs-user/terminalbench-runtime/venv/bin/python /home/ecs-user/terminalbench-setup-20260923/paired_control.py status'
if ($LASTEXITCODE -ne 0) { throw 'Could not read cloud status; do not assume stopped or launch again.' }
