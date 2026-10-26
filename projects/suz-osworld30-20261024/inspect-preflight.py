import json
from pathlib import Path
root=Path(__file__).resolve().parent
for mode in ['opencua_baseline','suz']:
 p=root/'preflight-multistep'/mode
 state=json.loads((p/'controller.json').read_text()) if (p/'controller.json').exists() else {}
 agent=[json.loads(x) for x in (p/'agent.jsonl').read_text().splitlines()] if (p/'agent.jsonl').exists() else []
 print(json.dumps({'mode':mode,'step':state.get('step'),'stopped':state.get('halted'),'role_errors':state.get('roleErrors'),
  'protocol_repairs':[{'event':x['event'],'reason':x.get('reason')} for x in agent if 'rejected' in x['event']],
  'last_action':next((x['actions'] for x in reversed(agent) if x['event']=='prediction'),None)}))
assets=root/'assets-preflight.json'
if assets.exists():
 a=json.loads(assets.read_text());print(json.dumps({'assets_passed':sum(x['ok'] for x in a),'total':len(a),'errors':[x for x in a if not x['ok']]}))
