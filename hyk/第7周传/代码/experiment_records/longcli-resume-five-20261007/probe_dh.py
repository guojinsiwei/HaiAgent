import json
from pathlib import Path
p=Path('/mnt/sdb/home/lizh639/longcli-dh-large20-20261007/jobs/dh--cs61_fa24_cats/model-audit.jsonl')
last={}
for line in p.open():
 r=json.loads(line)
 if r['event'] in ('context_measurement','wire_request','transport_diagnostic'):last[r['event']]=r
 if r['event']=='wire_response' and r.get('envelope'):last['usage']=r['envelope'].get('usage')
r=last['wire_request'];body=r['payload'];ms=body['messages']
print(json.dumps({'context':last.get('context_measurement'),'usage':last.get('usage'),'messages':len(ms),'chars':sum(len(m['content']) for m in ms),'max_tokens':body['max_tokens']},ensure_ascii=False))
for path in ['sources','compatibility']:
 print(path,[str(f) for f in (p.parents[2]/path).iterdir()])
