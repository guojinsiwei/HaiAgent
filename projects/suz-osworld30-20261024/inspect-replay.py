import json
from pathlib import Path
root=Path(__file__).resolve().parent
for folder in ['preflight-multistep','preflight-protocol-replay']:
 p=root/folder/'suz';s=json.loads((p/'controller.json').read_text())
 print(json.dumps({'folder':folder,'step':s['step'],'errors':s['roleErrors'],'supplied':s['supplied'].get('critic')}))
 for line in (p/'agent.jsonl').read_text().splitlines():
  r=json.loads(line)
  if r['event'] in ['role_protocol_rejected','stopped']:print(json.dumps(r))
  if r['event']=='role_output' and r.get('role')=='critic' and r.get('stage')=='review':print(json.dumps(r))
