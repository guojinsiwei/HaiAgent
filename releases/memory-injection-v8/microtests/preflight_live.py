"""No secrets or provider calls; verify the uploaded candidate before key entry."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
manifest=json.loads((ROOT/'evidence/source-manifest.json').read_text(encoding='utf-8'))
current={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
         for p in sorted((ROOT/'sources/bestfgs-project/src/bestfgs').glob('*.py'))}
if current!=manifest['candidate']: raise SystemExit('Candidate hash verification failed; do not enter key')
from run_live_memory import CASES
for case,spec in CASES.items():
    for name in spec['protected']:
        if not (ROOT/'microtests/fixtures'/case/name).is_file():
            raise SystemExit('Missing protected fixture; do not enter key')
if (ROOT/'evidence/live-memory').exists(): raise SystemExit('Live output already exists; do not restart/overwrite')
print('PREFLIGHT_OK: sealed candidate verified; three paired cases; <=60 provider decisions / <=120 wire attempts; no API call made')
