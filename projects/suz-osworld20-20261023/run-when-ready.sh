#!/usr/bin/env bash
set -euo pipefail
umask 077
cd /data/share/lizh639/suz-osworld20-20261023
export CUDA_VISIBLE_DEVICES=''
export NVIDIA_VISIBLE_DEVICES=void
export PYTHONPATH="$PWD/OSWorld:$PWD/SUZ"
export PATH="$PWD/.venv/bin:$PATH"
export TMPDIR="$PWD/tmp"
export SDL_VIDEODRIVER=dummy
export PYGAME_HIDE_SUPPORT_PROMPT=1
# Ordinary fixed experiment process; no Codex/GPT calls or recurring automation.
for iteration in $(seq 1 120); do
  if test -f logs/bootstrap.ready && test -f logs/vm.ready && test -f logs/docker-image.ready; then break; fi
  sleep 30
done
test -f logs/bootstrap.ready && test -f logs/vm.ready && test -f logs/docker-image.ready
cd SUZ
node scripts/preflight.mjs
node --test tests/*.test.mjs
python -m unittest discover -s tests -p 'test_*.py' -q
cd ..
if ! test -f logs/gui.ready; then python preflight-gui.py; fi
if ! test -f logs/protocol.ready; then python protocol-smoke.py; fi
python launch_queue.py
