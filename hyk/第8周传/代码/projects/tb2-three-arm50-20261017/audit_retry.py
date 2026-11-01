import json,sqlite3
from pathlib import Path
R=Path('/mnt/sdb/home/lizh639/tb2-three-arm50-20261017')
h=json.loads((R/'health.json').read_text())
print(json.dumps({k:h.get(k) for k in ('updated_utc','state','summary','active','spending')}))
db=sqlite3.connect('file:'+str(R/'spending.sqlite')+'?mode=ro',uri=True)
print('SCHEMA',db.execute("SELECT sql FROM sqlite_master WHERE type='table'").fetchall())
for row in h['rows']:
 if row['state']!='engineering_failure':continue
 result=row.get('result',{});t=Path(result.get('trial','/nonexistent'))
 print('\nFAIL',row['job'],result)
 rr=t/'result.json'
 if rr.exists():print('EXCEPTION',json.loads(rr.read_text()).get('exception_info'))
 for name in ('trial.log','verifier/test-stdout.txt','verifier/test-stderr.txt'):
  p=t/name
  if p.exists(): print(name,p.read_text(errors='replace')[-4500:])
 print('COST',db.execute('SELECT state,count(*),sum(reserved),sum(actual) FROM calls WHERE job=? GROUP BY state',(row['job'],)).fetchall())
for name in ('pytorch-model-recovery','mteb-leaderboard','torch-pipeline-parallelism'):
 t=R/'dependencies/official/tasks'/name
 print('TASK',name)
 for p in [t/'task.toml',*sorted((t/'environment').glob('*'))]:
  if p.is_file() and p.stat().st_size<20000:print(str(p),p.read_text(errors='replace'))
