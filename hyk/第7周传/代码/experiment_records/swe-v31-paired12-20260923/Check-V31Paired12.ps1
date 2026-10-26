$ErrorActionPreference = 'Continue'
$aliases = @('cubestudio_container', 'cubestudio_container2')
foreach ($index in 0, 1) {
    Write-Host "Worker $index on $($aliases[$index])"
    & ssh -o BatchMode=yes -o ConnectTimeout=15 $aliases[$index] "/mnt/lizh639/envs/bestfgs/bin/python /mnt/lizh639/swe-v31-paired12-setup-20260923/remote_v31.py status --index $index"
}
