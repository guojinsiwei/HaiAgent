import json,collections
from pathlib import Path
P=Path('/mnt/sdb/home/lizh639/tb2-three-arm50-retry2-20261018/jobs/retry2-tb50-09-dsh-torch-pipeline-parallelism/torch-pipeline-parallelism__Ksib3ke/agent/live/dsh.jsonl')
rows=[json.loads(l) for l in P.read_text().splitlines()]
print('TYPES',collections.Counter(r.get('type') for r in rows))
for i,r in enumerate(rows):
 if r.get('type')=='tool_call' and r['tool'] in ['write','edit']:
  print('MUTATION',i,r['tool'],r.get('truncated'),list(r['input']),len(r['input'].get('content','')),r['input'].get('file_path'))
  if 'content' in r['input']:print('TAIL',r['input']['content'][-180:])
for i,r in enumerate(rows):
 if r.get('type')=='tool_call' and (r['tool']=='read' and r['input'].get('file_path')=='/app/pipeline_parallel.py' or r['tool']=='bash' and 'pipeline_parallel.py' in r['input'].get('command','')):
  res=next(x for x in rows if x.get('type')=='tool_result' and x['callId']==r['callId'])
  print('READ',i,json.dumps(r['input'])[:1500], 'RESULT',str(res.get('result'))[:18000])
