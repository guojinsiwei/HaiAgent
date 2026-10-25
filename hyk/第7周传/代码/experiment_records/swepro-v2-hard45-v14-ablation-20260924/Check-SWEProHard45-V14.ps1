$ErrorActionPreference = 'Stop'
$python = '/mnt/lizh639/envs/bestfgs/bin/python'
$control = '/mnt/lizh639/bestfgs-runs/swepro-v2-hard45-v14-ablation-20260924/control/paired_hard45_v14_control.py'
foreach ($hostAlias in @('cubestudio_container', 'cubestudio_container2')) {
    Write-Host "=== $hostAlias ==="
    & ssh $hostAlias "$python $control status"
}
