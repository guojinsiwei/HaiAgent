import collections,json,hashlib
from pathlib import Path
result={'retries':[],'dsh':[],'context':[]}
for task,root in [('61810_lock','kz2-low4-20261009'),('61810_mmap','kz2-retry2-memory-soft-20261009'),('61810_cow','kz2-cow-timeout-retry-20261009'),('cmu15_445_p2','kz2-retry2-memory-soft-20261009')]:
 job=Path('/mnt/sdb/home/lizh639')/root/'jobs'/('1342--'+task)
 es=[json.loads(s) for s in (job/'trace/events.jsonl').read_text().splitlines() if s.strip()]
 result['retries'].append({'task':task,'job':str(job),'counts':dict(collections.Counter(e.get('event') for e in es)),'selected':[e for e in es if 'contrastive' in e.get('event','')],'summary':json.loads((job/'summary.json').read_text())})
for root in ['lizh639-longcli-kz-dsh3-20261012','lizh639-longcli-kz-dsh3-repair5-20261013']:
 for job in sorted((Path('/var/tmp')/root/'jobs').glob('kz--*')):
  logs=list((job/'audit/kz').glob('*.jsonl'))
  if not logs:continue
  es=[{'line':i,**json.loads(s)} for p in logs for i,s in enumerate(p.read_text().splitlines(),1) if s.strip()]
  result['dsh'].append({'root':root,'task':job.name,'log':str(logs[0]),'sha256':hashlib.sha256(logs[0].read_bytes()).hexdigest(),'counts':dict(collections.Counter(e.get('event') for e in es)),'gates':[{'line':e['line'],'event':e.get('event'),'decision':e.get('decision'),'result':e.get('result'),'callId':e.get('callId')} for e in es if e.get('event') in ['gate','proposal']],'episodes':[e for e in es if 'episode' in e.get('event','') or 'contrastive' in e.get('event','')]})
for root,task,ranges in [('longcli-dh-routing3x7-20261008','cs61_fa24_hog',[(193,300)]),('longcli-dh-routing3x7-20261008','cmu15_445_p1',[(350,425)]),('longcli-dh-1342-complete20-20261009','cmu15_445_p2',[(600,900)])]:
 base=Path('/var/tmp') if root.endswith('20261008') else Path('/mnt/sdb/home/lizh639')
 p=base/root/'jobs'/('1342--'+task)/'trace/events.jsonl'
 es=[]
 for i,s in enumerate(p.read_text().splitlines(),1):
  if not any(a<=i<=b for a,b in ranges) or not s.strip():continue
  e=json.loads(s)
  if e.get('event') in ['model_request','model_response']:continue
  es.append({'line':i,**e})
 result['context'].append({'task':task,'path':str(p),'events':es})
print(json.dumps(result,ensure_ascii=False))
