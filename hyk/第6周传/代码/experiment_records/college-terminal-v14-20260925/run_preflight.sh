#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
./runtime/bin/python preflight_cache.py
cp preflight/summary.json offline-preflight-summary.json
./runtime/bin/python - <<'PY'
import json
from pathlib import Path
data = json.loads(Path('offline-preflight-summary.json').read_text())
if not data.get('complete') or data.get('passed') != 36:
    raise SystemExit('Verifier preflight did not pass all 36 tasks')
Path('preflight-state.json').write_text(json.dumps({'phase': 'complete', 'passed': 36}) + '\n')
PY
