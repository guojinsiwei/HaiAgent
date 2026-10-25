$ErrorActionPreference = 'Stop'
$taskKeyPath = 'C:\Users\54177\Desktop\_terminalbench-20260923.pem'
if (-not (Test-Path -LiteralPath $taskKeyPath -PathType Leaf)) {
    throw 'ECS key file is missing. Do not paste its contents into chat.'
}
& ssh -F NUL -o BatchMode=yes -o IdentitiesOnly=yes -o ConnectTimeout=15 -i $taskKeyPath ecs-user@114.215.186.90 'hostname; uptime; free -h; df -h /; sudo systemctl is-active docker; /home/ecs-user/terminalbench-runtime/venv/bin/python --version; /home/ecs-user/terminalbench-runtime/venv/bin/harbor --version; sudo docker ps --format "{{.Names}} {{.Status}}"; cat /home/ecs-user/terminalbench-setup-20260923/environment-validation.json; curl -I -x http://127.0.0.1:28761 --connect-timeout 8 --max-time 15 -sS https://registry-1.docker.io/v2/'
if ($LASTEXITCODE -ne 0) { throw 'Status check failed; do not start duplicate installation or experiment processes.' }
