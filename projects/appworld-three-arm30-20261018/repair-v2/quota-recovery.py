"""Selective fresh retries after provider quota exhaustion, sharing original task caps."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import importlib.util,json,os,sys,subprocess,time,hashlib
V=Path(__file__).resolve().parent;R=V.parent;Q=R/'repair-v3'
sys.path.insert(0,str(R))
spec=importlib.util.spec_from_file_location('validated_repair',V/'runner.py')
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)

class AliasLedger:
    def __init__(self,ledger,aliases):self.ledger=ledger;self.aliases=aliases
    def reserve(self,request):
        q=dict(request);q['job']=self.aliases[q['job']];return self.ledger.reserve(q)
    def halt(self,reason,job=None):return self.ledger.halt(reason,self.aliases[job])
    def settle(self,request):return self.ledger.settle(request)
    def status(self):return self.ledger.status()

def prepare():
    plan=runner.validate();assert runner.read(V/'health.json').get('concurrency')==0
    queue=[]
    for item in plan['queue']:
        old=item['row']['_job'];d=R/'jobs'/old;s=runner.read(d/'summary.json')
        stop=runner.read(d/'audit/provider-stop.json')
        if stop.get('kind')!='quota' or s.get('official_success') is True:continue
        assert s.get('grading')=='complete'
        row=dict(item['row']);row.update(_job=old+'--quota3',_rerun_of=old,_attempt=row.get('_attempt',1)+1)
        queue.append({'arm':item['arm'],'row':row,'budget_job':old,'previous_tests':[s['passed_tests'],s['total_tests']]})
    assert len(queue)==3, 'Unexpected recovery selection; inspect results'
    Q.mkdir(exist_ok=True)
    preserved={str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for d in (R/'jobs').glob('*--mechanism2') for p in d.iterdir() if p.name in ['summary.json','health.json','world-manifest.json']}
    runner.save(Q/'before-result-hashes.json',preserved)
    plan={'queue':queue,'campaign_limit_cny':720,'shared_attempt_limit_cny':8,'model':'deepseek-flash','fresh_worlds':True,'account':'standby','baseline_effective':{'hld':28,'kzdsh-new':28},'reason':'provider_quota'}
    runner.save(Q/'resume-plan.json',plan);return plan

def campaign():
    runner.validate();plan=runner.read(Q/'resume-plan.json')
    ledger=runner.Ledger(R/'spending.sqlite',runner.read(R/'budget-profile.json'))
    assert ledger.status()['reserved_microcny']==0
    aliases={q['row']['_job']:q['budget_job'] for q in plan['queue']}
    budget=AliasLedger(ledger,aliases)
    credentials=json.loads((Path.home()/'.config/appworld-credentials/taotoken-standby.json').read_text())
    assert credentials['endpoint']==ledger.profile['endpoint']
    key=credentials['key'];assert key.startswith('sk-')
    completed=[]
    with ThreadPoolExecutor(max_workers=3) as pool:
        active={pool.submit(runner.trial,q['row'],key,q['arm'],budget):q for q in plan['queue']}
        while active:
            for f in list(active):
                if f.done():
                    q=active.pop(f)
                    try:completed.append(f.result())
                    except Exception as e:completed.append({'job':q['row']['_job'],'state':'needs_attention','engineering_fault':type(e).__name__})
            runner.save(Q/'health.json',{'state':'running' if active else 'complete','pid':os.getpid(),'updated':time.time(),'concurrency':len(active),'pending':[],'active':[{'job':q['row']['_job'],'arm':q['arm'],'task':q['row']['task']} for q in active.values()],'completed':completed,'budget':ledger.status(),'recovery_plan':str(Q/'resume-plan.json')})
            if active:time.sleep(5)
    runner.save(Q/'summary.json',runner.read(Q/'health.json'))

if __name__=='__main__':
    if '--supervise' in sys.argv:campaign()
    elif '--launch' in sys.argv:
        plan=prepare();(Q/'launch-once.marker').open('x').write('Authorized standby account recovery; shared prior attempt budgets.\n')
        with (Q/'supervisor.log').open('ab',buffering=0) as log:
            p=subprocess.Popen([sys.executable,__file__,'--supervise'],stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
        time.sleep(2);assert p.poll() is None
        print(json.dumps({'started':True,'pid':p.pid,'tasks':len(plan['queue']),'workers':3,'shared_prior_caps':True}))
    else:
        plan=prepare();print(json.dumps({'ready':True,'tasks':len(plan['queue']),'paid_calls':0}))
