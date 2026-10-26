from pathlib import Path
R=Path(__file__).resolve().parent
s=(R/'runner.py').read_text()
def replace(a,b):
    global s
    assert s.count(a)==1,a
    s=s.replace(a,b)
replace('from spending import Ledger,server_for','from spending import Ledger,server_for\nfrom repair_classification import classify')
replace("job=arm+'--'+row['task'];d=R/'jobs'/job;d.mkdir(parents=True,exist_ok=False)","job=row.get('_job',arm+'--'+row['task']);d=R/'jobs'/job;d.mkdir(parents=True,exist_ok=False)\n    save(d/'repair-version.json',{'version':1,'attempt':row.get('_attempt',1),'rerun_of':row.get('_rerun_of')})")
replace("s=dict(job=job,arm=arm,task=row['task'],scenario=row['scenario'],state='preparing',started=time.time(),world=world,solver=solver)","s=dict(job=job,arm=arm,task=row['task'],scenario=row['scenario'],state='preparing',started=time.time(),world=world,solver=solver,repair_version=1,attempt=row.get('_attempt',1),rerun_of=row.get('_rerun_of'))")
replace("        rec=read(d/'audit/recuris/state.json')","        s=classify(s,d)\n        rec=read(d/'audit/recuris/state.json')")
start=s.index('def validate():');end=s.index('    with ThreadPoolExecutor(max_workers=6) as pool:',start)
s=s[:start]+'''def validate():
    ready=read(R/'repair-v1/ready.json');assert ready.get('passed'),'Repair acceptance required'
    for name,value in ready['hashes'].items():assert hashlib.sha256((R/name).read_bytes()).hexdigest()==value,name
    plan=read(R/'repair-v1/resume-plan.json');assert plan['campaign_limit_cny']==720 and plan['attempt_limit_cny']==8
    return plan

def campaign(key):
    plan=validate();ledger=Ledger(R/'spending.sqlite',read(R/'budget-profile.json'))
    ledger.reconcile_restart()
    queue=[(item['row'],item['arm']) for item in plan['queue']]
    complete=plan['previous_completed'];active={}
''' +s[end:]
replace("'active':[{'task':r['task'],'arm':a} for r,a in active.values()]","'active':[{'task':r['task'],'arm':a,'job':r.get('_job',a+'--'+r['task'])} for r,a in active.values()]")
replace("'pending':[{'task':r['task'],'arm':a} for r,a in queue]","'pending':[{'task':r['task'],'arm':a,'job':r.get('_job',a+'--'+r['task'])} for r,a in queue]")
replace("(R/'launch-once.marker').open('x').write('120 trials; 8 CNY each, shared 720 CNY; no automatic paid retries.\\n')","(R/'repair-v1/launch-once.marker').open('x').write('Authorized budget repair and selective retries; cumulative campaign ledger retained.\\n')")
replace("print(json.dumps({'started':True,'pid':p.pid,'trials':120,'workers':6,'campaign_cny':720}))","print(json.dumps({'started':True,'pid':p.pid,'queued_attempts':len(read(R/'repair-v1/resume-plan.json')['queue']),'workers':6,'campaign_cny':720,'repair_version':1}))")
(R/'runner_repair.py').write_text(s)
