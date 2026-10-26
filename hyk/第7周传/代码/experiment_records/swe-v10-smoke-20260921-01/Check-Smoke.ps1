$ErrorActionPreference = 'Stop'
$aliases = @('cubestudio_container', 'cubestudio_container2')
for ($index = 0; $index -lt 2; $index++) {
    $remoteCommand = 'env PATH=/mnt/lizh639/envs/bestfgs/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin PYTHONDONTWRITEBYTECODE=1 /mnt/lizh639/envs/bestfgs/bin/python /mnt/lizh639/notebook-tools/remote_smoke.py status --index ' + $index
    & ssh -o BatchMode=yes -o ConnectTimeout=15 $aliases[$index] $remoteCommand
}
