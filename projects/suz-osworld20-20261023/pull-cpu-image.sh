#!/usr/bin/env bash
set -euo pipefail
cd /data/share/lizh639/suz-osworld20-20261023
image=happysixd/osworld-docker:latest
if ! docker image inspect "$image" >/dev/null 2>&1; then
  mirror=docker.m.daocloud.io/happysixd/osworld-docker:latest
  timeout 1800 docker pull "$mirror"
  docker tag "$mirror" "$image"
fi
docker image inspect "$image" --format '{{.Id}} {{json .RepoDigests}}' > logs/vm-container-image.txt
date -u > logs/docker-image.ready
