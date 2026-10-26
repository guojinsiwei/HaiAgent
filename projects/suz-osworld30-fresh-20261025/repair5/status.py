import json,sqlite3,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
out={'checked_at':time.time(),'experiment':ROOT.name,'fresh_runs_only':True,'total_per_arm':30,'groups':{}}
for mode in ['opencua_baseline','suz']:
    results=[json.loads(p.read_text()) for p in (ROOT/'runs'/mode).glob('*/result.json')]
    workers=[json.loads(p.read_text()) for p in (ROOT/'runs'/mode).glob('*/worker-status.json')]
    out['groups'][mode]={'ended':len(results),'scored':sum(x.get('official_score') is not None for x in results),
      'passed':sum(x.get('official_score')==1 for x in results),
      'engineering_failures':sum(x.get('outcome_kind')=='engineering_failure' for x in results),
      'startup_failures':[x['id'] for x in workers if x['stage']=='engineering_failure'],
      'active':[{'id':x['id'],'stage':x['stage']} for x in workers if x['stage'] in ['preflight','running','recovery_required']]}
if (ROOT/'budget.sqlite').exists():
    with sqlite3.connect('file:'+str(ROOT/'budget.sqlite')+'?mode=ro',uri=True) as db:
        out['accounted_cny']=db.execute('select coalesce(sum(charge),0) from calls').fetchone()[0]
        out['reserved']=db.execute("select count(*),coalesce(sum(charge),0) from calls where status='reserved'").fetchone()
out['budget_cny']=480
print(json.dumps(out,indent=2))
