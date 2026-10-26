from pathlib import Path
import json,hashlib,time,sys
V=Path(__file__).resolve().parent;R=V.parent;sys.path.insert(0,str(R))
from spending import Ledger
def read(p):
    try:return json.loads(p.read_text())
    except (FileNotFoundError,ValueError):return {}
h=read(V/'health.json');plan=read(V/'resume-plan.json');details=[]
for q in plan.get('queue',[]):
    job=q['row']['_job'];s=read(R/'jobs'/job/'summary.json') or read(R/'jobs'/job/'health.json')
    details.append({'arm':q['arm'],'task':q['row']['task'],'job':job,'before':q['before_tests'],
      'state':s.get('state','pending'),'graded':s.get('grading')=='complete','pass':s.get('official_success'),
      'tests':[s.get('passed_tests'),s.get('total_tests')],'requests':s.get('shared_requests',0),'fault':s.get('engineering_fault')})
arms={}
for arm in ['hld','kzdsh-new']:
    rs=[x for x in details if x['arm']==arm];wins=sum(x['pass'] is True for x in rs)
    arms[arm]={'reruns_finished':sum(x['graded'] for x in rs),'reruns_total':len(rs),'new_passes':wins,
               'effective_passes':plan.get('baseline_passed',{}).get(arm,0)+wins}
out={'time':time.time(),'state':h.get('state','not_started'),'concurrency':h.get('concurrency',0),'pending':len(h.get('pending',[])),
     'arms':arms,'details':details,'budget':Ledger(R/'spending.sqlite',read(R/'budget-profile.json')).status()}
if '--verify-originals' in sys.argv:
    originals=read(V/'original-result-manifest.json')
    out['original_results_unchanged']=all(hashlib.sha256((R/p).read_bytes()).hexdigest()==sha for p,sha in originals.items())
print(json.dumps(out,ensure_ascii=False,indent=2))
