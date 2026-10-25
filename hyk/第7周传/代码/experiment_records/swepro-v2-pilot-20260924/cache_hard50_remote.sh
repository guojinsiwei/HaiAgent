#!/usr/bin/env bash
set -euo pipefail

BASE=/mnt/lizh639/bestfgs-runs/swepro-v2-hard50-v13-20260924
CONTROL="$BASE/control"
mkdir -p "$BASE/oci" "$BASE/image-digests" "$BASE/cache-ready"
exec >>"$BASE/image-cache.log" 2>&1

selection_sha=$(sha256sum "$CONTROL/hard50_ids.txt" | awk '{print $1}')
[[ "$selection_sha" == 381f9e131112c2779c61ad24afc678755b3c0147ef050ca4c328d301defeb7fd ]] || {
  echo "selection hash mismatch: $selection_sha"
  exit 1
}
[[ $(grep -cve '^$' "$CONTROL/hard50_ids.txt") == 50 ]] || {
  echo "selection must contain exactly 50 tasks"
  exit 1
}

while IFS= read -r id; do
  [[ -n "$id" ]] || continue
  if [[ -f "$BASE/cache-ready/$id" ]]; then
    echo "[$(date -Is)] cached: $id"
    continue
  fi
  image="ghcr.io/scaleapi/swe-bench_pro-v2:$id"
  # OCI reference names reject the underscores used by SWE-bench instance IDs.
  # Keep the human-readable ID in our control files and use a deterministic,
  # collision-resistant local tag only inside the OCI layout.
  local_tag="task-$(printf '%s' "$id" | sha256sum | cut -c1-32)"
  inspected=0
  for attempt in 1 2 3 4 5 6 7 8; do
    echo "[$(date -Is)] inspect $attempt/8: $image"
    if skopeo inspect --retry-times 3 --format '{{.Digest}}' "docker://$image" \
        >"$BASE/image-digests/$id.txt.tmp"; then
      mv "$BASE/image-digests/$id.txt.tmp" "$BASE/image-digests/$id.txt"
      inspected=1
      break
    fi
    rm -f "$BASE/image-digests/$id.txt.tmp"
    sleep $((attempt * 20))
  done
  [[ "$inspected" == 1 ]] || { echo "image inspect failed after eight attempts: $id"; exit 1; }
  copied=0
  for attempt in 1 2 3 4 5; do
    echo "[$(date -Is)] copy $attempt/5: $id"
    if skopeo copy --retry-times 3 "docker://$image" "oci:$BASE/oci:$local_tag"; then
      copied=1
      break
    fi
    sleep $((attempt * 15))
  done
  [[ "$copied" == 1 ]] || { echo "image copy failed after five attempts: $id"; exit 1; }
  touch "$BASE/cache-ready/$id"
done <"$CONTROL/hard50_ids.txt"

[[ $(find "$BASE/cache-ready" -maxdepth 1 -type f | wc -l) == 50 ]] || {
  echo "cache completion count mismatch"
  exit 1
}
touch "$BASE/IMAGE_CACHE_READY"
echo "[$(date -Is)] all 50 official images cached"
