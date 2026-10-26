import json,sqlite3,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
out={'checked_at':time.time(),'benchmark':'OSWorld-Verified','total_per_arm':30,'groups':{}}
for mode in ['opencua_baseline','suz']:
    outcomes=[json.loads(p.read_text()) for p in (ROOT/'runs'/mode).glob('*/result.json')]
    workers=[json.loads(p.read_text()) for p in (ROOT/'runs'/mode).glob('*/worker-status.json')]
    originals={p.parent.name:json.loads(p.read_text()) for p in (ROOT.parent/'runs'/mode).glob('*/result.json')}
    latest={**originals,**{x['task_id']:x for x in outcomes}}
    jobs=json.loads((ROOT/'repair-jobs.json').read_text())
    out['groups'][mode]={'repair_planned':sum(x['mode']==mode for x in jobs),'repair_finished':len(outcomes),'repair_passed':sum(x.get('official_score')==1 for x in outcomes),
      'original_passed':sum(x.get('official_score')==1 for x in originals.values()),
      'latest_combined_passed':sum(x.get('official_score')==1 for x in latest.values()),
      'scored':sum(x.get('official_score') is not None for x in outcomes),
      'engineering_failures':sum(x.get('outcome_kind')=='engineering_failure' for x in outcomes),
      'startup_failures':[{'id':x['id'],'error':x.get('error')} for x in workers if x['stage']=='engineering_failure'],
      'active':[{'id':x['id'],'stage':x['stage']} for x in workers if x['stage'] in {'preflight','running','recovery_required'}]}
if (ROOT.parent/'budget.sqlite').exists():
    with sqlite3.connect('file:'+str(ROOT.parent/'budget.sqlite')+'?mode=ro',uri=True) as db:
        out['accounted_cny']=db.execute('select coalesce(sum(charge),0) from calls').fetchone()[0]
        out['reserved']=db.execute("select count(*),coalesce(sum(charge),0) from calls where status='reserved'").fetchone()
out['budget_cny']=480
print(json.dumps(out,indent=2))
