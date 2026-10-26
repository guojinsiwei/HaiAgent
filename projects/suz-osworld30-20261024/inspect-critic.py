import json
from pathlib import Path
p=Path(__file__).resolve().parent/'preflight-multistep/suz'
s=json.loads((p/'controller.json').read_text());print('current',s['current'])
for x in map(json.loads,(p/'agent.jsonl').read_text().splitlines()):
 if x['event']=='role_output' and x['role']=='critic' and x.get('stage')=='review':
  print(x['output'])
