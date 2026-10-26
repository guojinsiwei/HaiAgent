#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
PYTHON="${CUBE_PYTHON:-/mnt/lizh639/envs/bestfgs/bin/python}"
if [[ -z "${DEEPSEEK_API_KEY:-}" ]]; then
    read -rsp 'DeepSeek API Key (hidden): ' DEEPSEEK_API_KEY
    printf '\n'
fi
if [[ -z "$DEEPSEEK_API_KEY" ]]; then
    printf 'No key supplied; nothing started.\n' >&2
    exit 2
fi
export DEEPSEEK_API_KEY
export PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
export PATH="$(dirname "$PYTHON"):$PATH"
OUTPUT="${1:-/mnt/lizh639/bestfgs-runs/terminal-cube-pilot-$(date -u +%Y%m%dT%H%M%S)-$$}"
exec "$PYTHON" run_terminal_bench_cube.py run --output-root "$OUTPUT"
