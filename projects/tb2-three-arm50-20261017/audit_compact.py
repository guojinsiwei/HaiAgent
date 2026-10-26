import json,sqlite3,urllib.request,urllib.error,inspect
from pathlib import Path
R=Path('/mnt/sdb/home/lizh639/tb2-three-arm50-20261017')
h=json.loads((R/'health.json').read_text());db=sqlite3.connect('file:'+str(R/'spending.sqlite')+'?mode=ro',uri=True)
for row in h['rows']:
 if row['state']!='engineering_failure':continue
 res=row['result'];t=Path(res.get('trial','/nonexistent'));rr=t/'result.json'
 e=json.loads(rr.read_text()).get('exception_info') if rr.exists() else None
 print(json.dumps(dict(job=row['job'],error=(e or {}).get('exception_message'),cost=db.execute('SELECT state,count(*),sum(coalesce(actual,reserved)) FROM calls WHERE job=? GROUP BY state',(row['job'],)).fetchall())))
 if res.get('reason')!='preflight_failed':
  live=t/'agent/live'
  for fn in ('route.jsonl','provider-audit.jsonl','transport-recovery.jsonl','provider-state.json','native-transport.jsonl'):
   p=live/fn
   if p.exists():
    lines=p.read_text(errors='replace').splitlines()[-5:]
    for line in lines:
     try:
      x=json.loads(line);safe={k:v for k,v in x.items() if k in ('event','status','kind','reason','error','origin','attempt','retry','usage','time','updated_utc')}
      print(fn,json.dumps(safe))
     except ValueError:pass
  print('LIVEFILES',[p.name for p in live.iterdir()] if live.exists() else [])
for url in ['https://pypi.org/simple/pytest/','https://files.pythonhosted.org/']:
 try:
  with urllib.request.urlopen(url,timeout=20) as r:print('NETWORK',url,r.status)
 except urllib.error.HTTPError as e:print('NETWORK',url,e.code)
 except Exception as e:print('NETWORK',url,type(e).__name__)
from harbor.trial.trial import Trial
print(inspect.getsource(Trial._start_agent_environment))
