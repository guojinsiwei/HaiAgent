from pathlib import Path
import collections,json,time
from repair_classification import classify
R=Path(__file__).resolve().parent
def read(p):
    try:return json.loads(p.read_text())
    except (FileNotFoundError,ValueError):return {}
h=read(R/'health.json');rows=[]
for p in (R/'jobs').glob('*/health.json'):
    s=read(p)
    if s:rows.append(classify(s,p.parent))
arms={}
for arm in ['hld','kzdsh-new','recuris','dsh']:
    a=[r for r in rows if r['arm']==arm];finished=[r for r in a if r.get('grading')=='complete']
    bytask=collections.defaultdict(list)
    for r in finished:bytask[r['task']].append(r)
    effective=[]
    for rs in bytask.values():
        # Retained pass takes precedence; otherwise report the latest completed attempt.
        passed=[r for r in rs if r.get('official_success') is True]
        effective.append(max(passed or rs,key=lambda r:r.get('ended',0)))
    scenarios=collections.defaultdict(list)
    for r in effective:scenarios[r['scenario']].append(r)
    arms[arm]={'finished_tasks':len(effective),'finished_attempts':len(finished),'passed':sum(r.get('official_success') is True for r in effective),
      'unresolved_engineering_faults':sum(bool(r.get('engineering_fault')) for r in effective),
      'legacy_budget_affected_unpassed':sum(bool(r.get('budget_accounting_affected')) and not r.get('official_success') for r in effective),
      'scenarios_passed':sum(len(rs)==3 and all(r.get('official_success') for r in rs) for rs in scenarios.values()),
      'active':[{'task':r['task'],'job':r['job'],'state':r['state'],'requests':r.get('shared_requests',0),'tools':r.get('tools',0),'attempt':r.get('attempt',1)} for r in a if r.get('grading')!='complete' and r['state'] not in ['graded','needs_attention']]}
print(json.dumps({'time':time.time(),'state':h.get('state'),'concurrency':h.get('concurrency',0),'pending':len(h.get('pending',[])),
 'budget':h.get('budget'),'arms':arms,'repair_plan':{k:v for k,v in read(R/'repair-v1/resume-plan.json').items() if k.endswith('_count')}},indent=2))
