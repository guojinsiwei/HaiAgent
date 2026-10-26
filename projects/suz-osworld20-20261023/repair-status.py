"""Read only: original vs repaired attempts, all roles and attempts in budget."""
import json,sqlite3,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'SUZ-repair1'))
from python.outcomes import classify
out={'checked_at':time.time(),'groups':{}}
for mode in ['opencua_baseline','suz']:
    old={p.parent.name:json.loads(p.read_text()) for p in (ROOT/'runs'/mode).glob('*/result.json')}
    new={p.parent.name:json.loads(p.read_text()) for p in (ROOT/'repair1-runs'/mode).glob('*/result.json')}
    workers=[json.loads(p.read_text()) for p in (ROOT/'repair1-runs'/mode).glob('*/worker-status.json')]
    merged={**old,**new}
    out['groups'][mode]={'original_passed':sum(r.get('official_score')==1 for r in old.values()),
      'original_engineering_stops':sum(classify(r)=='engineering_failure' for r in old.values()),
      'repair_finished':len(new),'repair_passed':sum(r.get('official_score')==1 for r in new.values()),
      'repair_engineering_errors':sum(classify(r)=='engineering_failure' for r in new.values()),
      'combined_passed':sum(r.get('official_score')==1 for r in merged.values()),
      'preflight_failures':[{'id':r['id'],'error':r.get('error')} for r in workers if r['stage']=='engineering_failure'],
      'active':[{'id':r['id'],'stage':r['stage']} for r in workers if r['stage'] in {'preflight','running','recovery_required'}]}
with sqlite3.connect('file:'+str(ROOT/'budget.sqlite')+'?mode=ro',uri=True) as db:
    out['accounted_cny']=db.execute('select coalesce(sum(charge),0) from calls').fetchone()[0]
    out['reserved']=db.execute("select count(*),coalesce(sum(charge),0) from calls where status='reserved'").fetchone()
print(json.dumps(out,indent=2))
