import json
from pathlib import Path
p=Path(__file__).resolve().parent/'preflight-multistep/suz'
s=json.loads((p/'controller.json').read_text())
print(json.dumps({'supplied':s.get('supplied',{}).get('planner')}))
for line in (p/'agent.jsonl').read_text().splitlines():
 r=json.loads(line)
 if r.get('event')=='role_output' and r.get('role')=='planner':
  raw=r['output'].strip().removeprefix('```json').removesuffix('```').strip()
  try: a=json.loads(raw);print(json.dumps({'memory_review':a.get('memory_review'),'keys':list(a)}))
  except Exception as e: print(type(e).__name__)
