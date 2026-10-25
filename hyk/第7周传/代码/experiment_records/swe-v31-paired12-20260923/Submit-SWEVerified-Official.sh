#!/usr/bin/env bash
set -euo pipefail

ROOT="/mnt/c/Users/54177/Documents/ChatGPT/mcts"
CLIENT_DIR="$ROOT/official-submission-v3"
RESULTS_DIR="$ROOT/experiment_records/swe-v31-paired12-20260923/downloaded-results"

cd "$CLIENT_DIR"

if [[ ! -x .sb-cli-venv/bin/sb-cli ]]; then
  python3 -m venv .sb-cli-venv
  .sb-cli-venv/bin/python -m pip install --upgrade pip
  .sb-cli-venv/bin/python -m pip install 'sb-cli==0.1.5'
fi

read -r -s -p 'SWE-bench API Key: ' SWEBENCH_API_KEY
echo
export SWEBENCH_API_KEY

.sb-cli-venv/bin/sb-cli submit swe-bench_verified test \
  --predictions_path "$RESULTS_DIR/bestfgs-predictions.jsonl" \
  --run_id bestfgs-v31-paired12-20260924 \
  --verify_submission 1 \
  --wait_for_evaluation 0 \
  --gen_report 0

.sb-cli-venv/bin/sb-cli submit swe-bench_verified test \
  --predictions_path "$RESULTS_DIR/raw-predictions.jsonl" \
  --run_id raw-v31-paired12-20260924 \
  --verify_submission 1 \
  --wait_for_evaluation 0 \
  --gen_report 0

unset SWEBENCH_API_KEY
echo 'Both submissions were accepted for official evaluation. Use sb-cli list-runs to check progress later.'
