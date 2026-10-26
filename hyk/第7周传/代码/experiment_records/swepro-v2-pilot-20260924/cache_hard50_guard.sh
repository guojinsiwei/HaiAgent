#!/usr/bin/env bash
set -euo pipefail

index=${1:?worker index required}
[[ "$index" == 0 || "$index" == 1 ]] || { echo "index must be 0 or 1"; exit 2; }
base=/mnt/lizh639/bestfgs-runs/swepro-v2-hard50-v13-20260924
python=/mnt/lizh639/envs/bestfgs/bin/python
worker="$base/control/cache_hard50.py"
exec 9>"$base/image-cache-guard-$index.lock"
flock -n 9 || { echo "guard $index is already active"; exit 3; }

for restart in $(seq 0 20); do
  [[ -f "$base/IMAGE_CACHE_WORKER_${index}_READY" ]] && {
    echo "[$(date -Is)] worker $index cache complete"
    exit 0
  }
  pattern="^$python $worker --index $index$"
  while pgrep -f "$pattern" >/dev/null; do
    echo "[$(date -Is)] worker $index alive; guard heartbeat"
    sleep 60
  done
  [[ -f "$base/IMAGE_CACHE_WORKER_${index}_READY" ]] && exit 0
  if (( restart == 20 )); then
    echo "[$(date -Is)] worker $index exhausted 20 process-level recoveries"
    exit 4
  fi
  delay=$(( restart == 0 ? 5 : restart * 60 ))
  (( delay > 600 )) && delay=600
  echo "[$(date -Is)] worker $index absent; recovery $((restart + 1))/20 after ${delay}s"
  sleep "$delay"
  "$python" "$worker" --index "$index" >>"$base/image-cache-$index.log" 2>&1 || true
done
