#!/usr/bin/env bash
set -euo pipefail

ROOT="/mnt/c/Users/54177/Documents/ChatGPT/mcts"
HARNESS_DIR="$ROOT/official-submission-v3"
RESULTS_DIR="$ROOT/experiment_records/swe-v31-paired12-20260923/downloaded-results"
OUT_DIR="$ROOT/experiment_records/swe-v31-paired12-20260923/local-official-results"

IDS=(
  scikit-learn__scikit-learn-25747
  django__django-13121
  sphinx-doc__sphinx-9658
  django__django-11066
  django__django-13809
  django__django-14752
  sympy__sympy-22080
  pydata__xarray-3095
  django__django-11749
  django__django-15957
  django__django-15382
  django__django-15467
)

backup_images() {
  for id in "${IDS[@]}"; do
    image="swebench/sweb.eval.x86_64.${id/__/_1776_}:latest"
    backup="swebench-local-cache/${id}:v31-paired12"
    docker image inspect "$image" >/dev/null
    docker tag "$image" "$backup"
  done
}

restore_images() {
  for id in "${IDS[@]}"; do
    image="swebench/sweb.eval.x86_64.${id/__/_1776_}:latest"
    backup="swebench-local-cache/${id}:v31-paired12"
    docker tag "$backup" "$image"
  done
}

run_eval() {
  local label="$1"
  local predictions="$2"
  python -m swebench.harness.run_evaluation \
    --dataset_name SWE-bench/SWE-bench_Verified \
    --split test \
    --predictions_path "$predictions" \
    --max_workers 2 \
    --timeout 1800 \
    --run_id "${label}-v31-paired12-20260924" \
    --report_dir "$OUT_DIR/$label"
}

mkdir -p "$OUT_DIR/bestfgs" "$OUT_DIR/raw"
cd "$HARNESS_DIR"
source .official-eval-venv/bin/activate

backup_images
run_eval bestfgs "$RESULTS_DIR/bestfgs-predictions.jsonl"

# The official harness removes the original image tags after a run. Restore
# them from the local backup tags before the Raw control arm starts.
restore_images
run_eval raw "$RESULTS_DIR/raw-predictions.jsonl"

echo "Local official evaluation completed. Reports: $OUT_DIR"
