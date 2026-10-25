#!/usr/bin/env bash
set -euo pipefail
test "$(id -u)" = 0
cd /home/ecs-user/terminalbench-setup-20260923
export DEBIAN_FRONTEND=noninteractive
apt-get -o DPkg::Lock::Timeout=180 install -y busybox-static
install -m 0755 /bin/busybox busybox
docker build --network=none -f Dockerfile.smoke -t terminalbench-runtime-smoke:20260923 .
docker run --rm --network=none --memory=128m --cpus=0.5 --cap-drop=ALL --security-opt=no-new-privileges terminalbench-runtime-smoke:20260923 sh -c 'echo isolated > /marker; test -f /marker; echo CONTAINER_WRITE_OK'
docker run --rm --network=none --memory=128m --cpus=0.5 --cap-drop=ALL --security-opt=no-new-privileges terminalbench-runtime-smoke:20260923 sh -c 'test ! -e /marker; echo FRESH_CONTAINER_OK'
echo 'CONTAINER_SMOKE_COMPLETE'
