#!/usr/bin/env bash
set -u
SETUP="$HOME/terminalbench-v14-setup"
LOG="$SETUP/prepare-guard.log"
exec 9>"$SETUP/prepare-guard.lock"
flock -n 9 || exit 0
for attempt in $(seq 1 20); do
  printf '[%s] preparation attempt %s/20\n' "$(date -Is)" "$attempt" >> "$LOG"
  HARBOR_TELEMETRY=0 "$SETUP/runtime/bin/python" "$SETUP/prepare_data.py" >> "$LOG" 2>&1
  status=$?
  phase=$("$SETUP/runtime/bin/python" -c 'import json,pathlib; print(json.loads((pathlib.Path.home()/"terminalbench-v14-setup/preparation.json").read_text()).get("phase"))' 2>/dev/null || true)
  if test "$status" = 0 && test "$phase" = data_ready; then
    printf '[%s] data preparation complete\n' "$(date -Is)" >> "$LOG"
    exit 0
  fi
  sleep 120
done
printf '[%s] preparation retry budget exhausted\n' "$(date -Is)" >> "$LOG"
exit 1
