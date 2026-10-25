#!/usr/bin/env bash
set -euo pipefail
cd /home/ecs-user/terminalbench-setup-20260923
test "$(id -u)" = 0
test -z "$(docker ps -q)" || { echo 'Refusing to restart Docker while containers run'; exit 1; }
target=/etc/systemd/system/docker.service.d/terminalbench-download-proxy.conf
if test -e "$target"; then cmp terminalbench-download-proxy.conf "$target"; fi
install -d -m 0755 /etc/systemd/system/docker.service.d
install -m 0644 terminalbench-download-proxy.conf "$target"
systemctl daemon-reload
systemctl restart docker
systemctl is-active docker
docker pull alexgshaw/regex-log@sha256:90101b2e815323a8da20528a1439bebc407eb9761c9c68a3d557730856c878e9
# Docker's containerd image store reports manifest digest as Id; verify the
# distribution digest, not the legacy config-digest interpretation of Id.
docker image inspect --format '{{json .RepoDigests}}' alexgshaw/regex-log@sha256:90101b2e815323a8da20528a1439bebc407eb9761c9c68a3d557730856c878e9 | grep -F 'alexgshaw/regex-log@sha256:90101b2e815323a8da20528a1439bebc407eb9761c9c68a3d557730856c878e9'
docker tag alexgshaw/regex-log@sha256:90101b2e815323a8da20528a1439bebc407eb9761c9c68a3d557730856c878e9 alexgshaw/regex-log:20251031
docker run --rm --network=none --memory=512m --cpus=1 --cap-drop=ALL --security-opt=no-new-privileges --entrypoint /bin/sh alexgshaw/regex-log:20251031 -c 'printf "OFFICIAL_IMAGE_CONTAINER_OK\n"; uname -m; cat /etc/os-release | head -n 3'
echo 'OFFICIAL_IMAGE_VERIFIED_AND_STARTED'
