#!/usr/bin/env bash
# Run only when explicitly invoked by the experiment owner.
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo 'Usage: bash run_longcli.sh /absolute/path/to/longcli-bench TASK_ID|--all [tb run options...]' >&2
  exit 2
fi
: "${DEEPSEEK_API_KEY:?Set DEEPSEEK_API_KEY in the current environment}"
: "${DEEPSEEK_MODEL:?Set DEEPSEEK_MODEL to a model ID supported by your provider}"
benchmark_root=$(cd -- "$1" && pwd)
task_id=$2
shift 2
if [[ ! -d "$benchmark_root/tasks_long_cli" ]]; then
  echo "Missing LongCLI-Bench dataset: $benchmark_root/tasks_long_cli" >&2
  exit 2
fi
command -v tb >/dev/null || { echo 'Activate the Python environment containing LongCLI-Bench and retrac.' >&2; exit 2; }
python -c 'from retrac.longcli import RetracAgent; assert RetracAgent.name() == "retrac"'
args=(
  run
  --agent-import-path retrac.longcli:RetracAgent
  --model "$DEEPSEEK_MODEL"
  --dataset-path "$benchmark_root/tasks_long_cli"
  --n-attempts 1
  --give-test-output 1
  --n-concurrent 1
  --agent-kwarg "rounds=${RETRAC_ROUNDS:-8}"
  --agent-kwarg "max_total_seconds=${RETRAC_MAX_SECONDS:-3600}"
  --global-agent-timeout-sec "${RETRAC_HARNESS_TIMEOUT:-3900}"
)
if [[ "$task_id" != '--all' ]]; then
  if [[ "$task_id" == *'/'* || "$task_id" == *'\\'* || ! -d "$benchmark_root/tasks_long_cli/$task_id" ]]; then
    echo "Unknown dataset task ID: $task_id" >&2
    exit 2
  fi
  args+=(--task-id "$task_id")
fi
cd -- "$benchmark_root"
exec tb "${args[@]}" "$@"
