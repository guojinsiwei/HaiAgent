#!/usr/bin/env bash
set -euo pipefail

BASE=/mnt/lizh639/bestfgs-runs/swepro-v2-pilot-20260924
mkdir -p "$BASE"
exec >>"$BASE/preparation.log" 2>&1

tasks=(
  instance_ansible__ansible-40ade1f84b8bb10a63576b0ac320c13f57c87d34-v6382ea168a93d80a64aab1fbd8c4f02dc5ada5bf
  instance_ansible__ansible-b748edea457a4576847a10275678127895d2f02f-v1055803c3a812189a1133297f7f5468579283f86
)

for id in "${tasks[@]}"; do
  task="$BASE/$id"
  image="ghcr.io/scaleapi/swe-bench_pro-v2:$id"
  mkdir -p "$task"
  if [[ -f "$task/READY" ]]; then
    echo "[$(date -Is)] already ready: $id"
    continue
  fi

  echo "[$(date -Is)] inspect: $image"
  skopeo inspect --format '{{.Digest}}' "docker://$image" | tee "$task/image-digest.txt"
  echo "[$(date -Is)] pull: $id"
  rm -rf "$task/bundle.partial"
  copied=0
  for attempt in 1 2 3 4 5; do
    echo "[$(date -Is)] copy attempt $attempt/5: $id"
    if skopeo copy --retry-times 3 "docker://$image" "oci:$task/oci.partial:task"; then
      copied=1
      break
    fi
    sleep $((attempt * 10))
  done
  [[ "$copied" == 1 ]] || { echo "image copy failed after five attempts: $id"; exit 1; }
  echo "[$(date -Is)] unpack: $id"
  umoci unpack --image "$task/oci.partial:task" "$task/bundle.partial"
  test -d "$task/bundle.partial/rootfs/app" || test -d "$task/bundle.partial/rootfs/testbed"
  cp /etc/resolv.conf "$task/bundle.partial/rootfs/etc/resolv.conf"
  mv "$task/oci.partial" "$task/oci"
  mv "$task/bundle.partial" "$task/bundle"

  root="$task/bundle/rootfs"
  if [[ -d "$root/app" ]]; then
    workspace=/app
  else
    workspace=/testbed
  fi
  chroot "$root" /bin/bash -lc "cd '$workspace' && git status --porcelain && git rev-parse HEAD && python3 --version" \
    >"$task/rootfs-probe.txt" 2>&1
  touch "$task/READY"
  echo "[$(date -Is)] ready: $id"
done

echo "[$(date -Is)] all selected environments ready"
