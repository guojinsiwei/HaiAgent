"""Compact, credential-free experiment status."""
import json,collections
from pathlib import Path
ROOT=Path(__file__).resolve().parent
h=json.loads((ROOT/'health.json').read_text())
print(json.dumps({k:h[k] for k in ('state','updated_utc','pid','summary','spending','active')},indent=2))
print(json.dumps(dict(states=dict(collections.Counter(r['state'] for r in h['rows'])),current=[{k:r[k] for k in ('task','arm','state','live','result') if k in r} for r in h['rows'] if r['state'] not in ('pending',)]),indent=2))
