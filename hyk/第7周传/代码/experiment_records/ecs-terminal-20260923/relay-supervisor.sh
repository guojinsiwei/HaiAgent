#!/usr/bin/env bash
set -euo pipefail
cd /mnt/lizh639/terminal-ecs-relay-20260923
umask 077
exec 9>relay.lock
flock -n 9 || exit 1
python3 -u download-relay.py >>relay.log 2>&1 &
relay_pid=$!
ssh_pid=''
cleanup() {
  kill "$relay_pid" 2>/dev/null || true
  if test -n "$ssh_pid"; then kill "$ssh_pid" 2>/dev/null || true; fi
}
trap cleanup EXIT INT TERM
for attempt in $(seq 1 20); do
  kill -0 "$relay_pid" || exit 1
  printf '%s tunnel attempt %s\n' "$(date -Is)" "$attempt" >>supervisor.log
  ssh -F /dev/null -N -T -o BatchMode=yes -o IdentitiesOnly=yes \
    -o StrictHostKeyChecking=yes -o UserKnownHostsFile=ecs_known_hosts \
    -o ExitOnForwardFailure=yes -o ConnectTimeout=15 \
    -o ServerAliveInterval=15 -o ServerAliveCountMax=3 \
    -i relay_ed25519 -R 127.0.0.1:28761:127.0.0.1:28761 \
    ecs-user@114.215.186.90 >>supervisor.log 2>&1 &
  ssh_pid=$!
  wait "$ssh_pid" || true
  ssh_pid=''
  sleep 30
done
echo 'STOPPED: bounded reconnect limit reached' >>supervisor.log
exit 1
