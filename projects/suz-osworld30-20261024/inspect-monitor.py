import json,sys
from pathlib import Path
root=Path(__file__).resolve().parent;sys.path.insert(0,str(root/'SUZ'))
from python.runtime import parse_json
p=root/'preflight-multistep/suz';s=json.loads((p/'controller.json').read_text())
print(json.dumps({'step':s['step'],'supplied_monitor':s['supplied']['monitor'],'recent':s['recent'],'errors':s['roleErrors']}))
for x in map(json.loads,(p/'agent.jsonl').read_text().splitlines()):
 if x['event']=='role_output' and x['role']=='monitor':
  a=parse_json(x['output']);print(json.dumps({'verdict':a.get('verdict'),'evidence_ids':a.get('evidence_ids'),'memories':[{'conclusion':m.get('conclusion'),'evidence_ids':m.get('evidence_ids')} for m in a.get('memories',[])]}))
