import json
from pathlib import Path
root=Path('/data/share/lizh639/suz-osworld20-20261023')
for mode in ['opencua_baseline','suz']:
 p=root/'preflight-multistep-repair1'/mode
 state=json.loads((p/'controller.json').read_text()) if (p/'controller.json').exists() else {}
 responses=[json.loads(x) for x in (p/'model-responses.jsonl').read_text().splitlines()] if (p/'model-responses.jsonl').exists() else []
 agent=[json.loads(x) for x in (p/'agent.jsonl').read_text().splitlines()] if (p/'agent.jsonl').exists() else []
 print(json.dumps({'mode':mode,'step':state.get('step'),'stopped':state.get('halted'),'role_errors':state.get('roleErrors'),
  'length_stops':sum(x['choices'][0].get('finish_reason')=='length' for x in responses),'recovery_32k':sum(x['max_tokens']==32768 for x in responses),
  'protocol_repairs':[{'event':x['event'],'reason':x.get('reason')} for x in agent if 'rejected' in x['event']],
  'last_action':next((x['actions'] for x in reversed(agent) if x['event']=='prediction'),None)},ensure_ascii=False))
