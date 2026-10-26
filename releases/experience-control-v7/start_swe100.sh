#!/usr/bin/env bash
# One foreground tmux session owns the entire batch, including environment preparation.
set -euo pipefail
cd "$(dirname "$0")"
stage="${1:-prepare}"
shift || true
case "$stage" in prepare|run|status|export) ;; *) echo 'Usage: bash start_swe100.sh prepare|run|status|export [batch options]'; exit 2;; esac
agent_python="${BESTFGS_PYTHON:-/mnt/lizh639/envs/bestfgs/bin/python}"
batch_root="${BESTFGS_BATCH_ROOT:-/mnt/lizh639/bestfgs-runs/swe100-v1}"
tmux_bin="$(dirname "$agent_python")/tmux"
if [[ -z "${TMUX:-}" && ( "$stage" == prepare || "$stage" == run ) ]]; then
    if "$tmux_bin" has-session -t bestfgs-swe100 2>/dev/null; then
        echo 'An existing bestfgs-swe100 session is present. Attach to inspect it:'
        echo "$tmux_bin attach -t bestfgs-swe100"
        exit 2
    fi
    printf -v command '%q ' bash "$PWD/start_swe100.sh" "$stage" "$@"
    exec "$tmux_bin" new-session -s bestfgs-swe100 "$command; code=\$?; echo Batch_exit_code=\$code; exec bash"
fi
if [[ "$stage" == run && -z "${DEEPSEEK_API_KEY:-}" ]]; then
    read -rsp 'DeepSeek API Key (hidden): ' DEEPSEEK_API_KEY
    echo
    export DEEPSEEK_API_KEY
fi
export PYTHONUNBUFFERED=1
exec "$agent_python" swe_batch.py "$stage" --root "$batch_root" "$@"
