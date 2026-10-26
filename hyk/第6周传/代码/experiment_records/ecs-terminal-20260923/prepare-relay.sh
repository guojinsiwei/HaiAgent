#!/usr/bin/env bash
set -euo pipefail
umask 077
mkdir -p /mnt/lizh639/terminal-ecs-relay-20260923
chmod 700 /mnt/lizh639/terminal-ecs-relay-20260923
cd /mnt/lizh639/terminal-ecs-relay-20260923
if test ! -e relay_ed25519; then
  ssh-keygen -q -t ed25519 -N '' -C terminalbench-download-relay-20260923 -f relay_ed25519
fi
chmod 600 relay_ed25519
cat relay_ed25519.pub
