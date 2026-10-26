from pathlib import Path
import collections,json,time
R=Path(__file__).resolve().parent
def read(p):
    try:return json.loads(p.read_text())
    except (FileNotFoundError,ValueError):return {}
h=read(R/'health.json');rows=[]
for p in (R/'jobs').glob('*/health.json'):rows.append(read(p))
arms={}
for arm in ['hld','kzdsh-new','recuris','dsh']:
    a=[r for r in rows if r['arm']==arm];valid=[r for r in a if r.get('grading')=='complete' and not r.get('engineering_fault')]
    scenarios=collections.defaultdict(list)
    for r in valid:scenarios[r['scenario']].append(r)
    arms[arm]={'finished':sum(r['state'] in ['graded','needs_attention'] for r in a),'valid_scored':len(valid),
      'passed':sum(r.get('official_success') is True for r in valid),'engineering_faults':sum(bool(r.get('engineering_fault')) for r in a),
      'scenarios_passed':sum(len(rs)==3 and all(r.get('official_success') for r in rs) for rs in scenarios.values()),
      'active':[{'task':r['task'],'state':r['state'],'requests':r.get('shared_requests',0),'tools':r.get('tools',0)} for r in a if r['state'] not in ['graded','needs_attention']]}
print(json.dumps({'time':time.time(),'state':h.get('state','preparing'),'concurrency':h.get('concurrency',0),'pending':len(h.get('pending',[])),
  'budget':h.get('budget'),'arms':arms,'faults':[{'arm':r['arm'],'task':r['task'],'fault':r.get('engineering_fault'),'error':r.get('error')} for r in rows if r.get('engineering_fault')]},indent=2))
