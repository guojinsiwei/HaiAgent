$ErrorActionPreference = 'Stop'
& ssh -o BatchMode=yes -o ConnectTimeout=15 cubestudio_container `
  'env PATH=/mnt/lizh639/envs/bestfgs/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin PYTHONDONTWRITEBYTECODE=1 /mnt/lizh639/envs/bestfgs/bin/python /mnt/lizh639/notebook-tools/remote_current50.py status'
