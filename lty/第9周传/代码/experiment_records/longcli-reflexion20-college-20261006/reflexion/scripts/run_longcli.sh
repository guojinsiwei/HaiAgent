#!/usr/bin/env bash
# Run only when invoked by the experiment owner.
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo 'Usage: bash run_longcli.sh /absolute/path/to/longcli-bench TASK_ID|--all [tb run options...]' >&2
  exit 2
fi
api_key_env=${REFLEXION_API_KEY_ENV:-DEEPSEEK_API_KEY}
if [[ ! "$api_key_env" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]]; then
  echo 'REFLEXION_API_KEY_ENV must be an environment variable name.' >&2
  exit 2
fi
if [[ -z "${!api_key_env:-}" ]]; then
  echo "Set $api_key_env in the current environment." >&2
  exit 2
fi
if [[ "$api_key_env" == 'OPENAI_API_KEY' ]]; then
  model=${REFLEXION_MODEL:-${OPENAI_MODEL:-}}
else
  model=${REFLEXION_MODEL:-${DEEPSEEK_MODEL:-${OPENAI_MODEL:-}}}
fi
if [[ -z "$model" ]]; then
  echo 'Set REFLEXION_MODEL, DEEPSEEK_MODEL or OPENAI_MODEL to a provider model ID.' >&2
  exit 2
fi
benchmark_root=$(cd -- "$1" && pwd)
task_id=$2
shift 2
if [[ ! -d "$benchmark_root/tasks_long_cli" ]]; then
  echo "Missing LongCLI-Bench dataset: $benchmark_root/tasks_long_cli" >&2
  exit 2
fi
command -v tb >/dev/null || { echo 'Activate the Python environment containing LongCLI-Bench and reflexion.' >&2; exit 2; }
python -c 'from reflexion.longcli import ReflexionAgent; assert ReflexionAgent.name() == "reflexion"'
args=(
  run
  --agent-import-path reflexion.longcli:ReflexionAgent
  --model "$model"
  --dataset-path "$benchmark_root/tasks_long_cli"
  --n-attempts 1
  --give-test-output 1
  --n-concurrent 1
  --agent-kwarg "api_key_env=$api_key_env"
  --agent-kwarg "max_trials=${REFLEXION_MAX_TRIALS:-3}"
  --agent-kwarg "max_total_seconds=${REFLEXION_MAX_SECONDS:-3600}"
  --global-agent-timeout-sec "${REFLEXION_HARNESS_TIMEOUT:-3900}"
)
if [[ -n "${REFLEXION_BASE_URL:-}" ]]; then
  args+=(--agent-kwarg "base_url=$REFLEXION_BASE_URL")
fi
if [[ "$task_id" != '--all' ]]; then
  if [[ "$task_id" == *'/'* || "$task_id" == *'\'* || ! -d "$benchmark_root/tasks_long_cli/$task_id" ]]; then
    echo "Unknown dataset task ID: $task_id" >&2
    exit 2
  fi
  args+=(--task-id "$task_id")
fi
cd -- "$benchmark_root"
exec tb "${args[@]}" "$@"
