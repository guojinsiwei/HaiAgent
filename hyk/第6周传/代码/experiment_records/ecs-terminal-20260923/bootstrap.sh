#!/usr/bin/env bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
export NEEDRESTART_MODE=a
cd "$(dirname "$0")"
test "$(id -u)" = 0
. /etc/os-release
test "$ID:$VERSION_ID:$(uname -m)" = 'ubuntu:22.04:x86_64'
exec 9>/var/lock/terminalbench-bootstrap.lock
flock -n 9 || { echo 'Another bootstrap is running'; exit 1; }
apt-get -o Acquire::Retries=2 -o Acquire::http::Timeout=30 update
apt-get -o DPkg::Lock::Timeout=120 install -y ca-certificates curl gnupg git tmux python3-venv python3-pip unzip jq
install -d -m 0755 /etc/apt/keyrings
curl --fail --silent --show-error --location --retry 2 --connect-timeout 10 --max-time 60 \
  https://mirrors.aliyun.com/docker-ce/linux/ubuntu/gpg -o docker.asc
fingerprint=$(gpg --batch --show-keys --with-colons docker.asc | awk -F: '$1=="fpr" {print $10; exit}')
test "$fingerprint" = '9DC858229FC7DD38854AE2D88D81803C0EBFCD88'
if test -e /etc/apt/sources.list.d/terminalbench-docker.sources; then
  cmp docker.sources /etc/apt/sources.list.d/terminalbench-docker.sources
fi
install -m 0644 docker.asc /etc/apt/keyrings/docker.asc
install -m 0644 docker.sources /etc/apt/sources.list.d/terminalbench-docker.sources
apt-get -o Acquire::Retries=2 -o Acquire::https::Timeout=30 update
apt-get -o DPkg::Lock::Timeout=120 install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker
docker version
docker compose version
docker info --format '{{json .SecurityOptions}}'
systemctl is-enabled docker
systemctl is-active docker
echo 'BOOTSTRAP_COMPLETE'
