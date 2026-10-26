"""Zero-provider-call runtime, verifier and budget acceptance before paid launch."""
from pathlib import Path
import os,json,sys,uuid,subprocess,hashlib,tempfile
R=Path('/mnt/sdb/home/lizh639/tb2-hld-v8-v91-paired20-20261023')
sys.path.insert(0,str(R));os.chdir(R)
import campaign
from spending import Ledger,BudgetError
read=campaign.read
def save(n,v):campaign.save(n,v)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert (R/'PAID_START_HOLD').exists() and not (R/'launch-once.marker').exists()
profile=read(R/'budget-profile.json');rows=read(R/'claimed-pending.json')['rows']
assert len(rows)==40 and len(set(profile['jobs']))==40
assert profile['campaign_limit_microcny']==320000000 and profile['task_limit_microcny']==8000000
campaign.validate_protocol(R)
with tempfile.TemporaryDirectory() as d:
 p=dict(profile,input_ceiling_tokens=0,max_output_tokens=1,task_limit_microcny=8,campaign_limit_microcny=16)
 l=Ledger(Path(d)/'test.sqlite',p)
 def req(i,j):return dict(id=i,job=j,arm='kz',endpoint=p['endpoint'],model=p['model'],max_tokens=1)
 def reject(r,reason):
  try:l.reserve(r)
  except BudgetError as e:assert e.reason==reason,(e.reason,reason)
  else:raise AssertionError(reason)
 reject(req('bad','unauthorized'),'job_not_authorized')
 l.reserve(req('1',p['jobs'][0]));l.settle(dict(id='1',tokens=8))
 reject(req('2',p['jobs'][0]),'per_task_budget_exhausted')
 l.reserve(req('3',p['jobs'][1]));l.settle(dict(id='3',tokens=8))
 reject(req('4',p['jobs'][2]),'campaign_budget_exhausted')
 assert l.status()['settled_microcny']==16
save('acceptance-progress.json',dict(state='runtime_and_verifier_preflight',paid_calls=0))
active=[];results=[]
for row in rows[:2]:
 row['preflight_attempt_id']=uuid.uuid4().hex
 env=dict(os.environ,PYTHONPATH=str(R)+':'+str(R/'dependencies'),PYTHONDONTWRITEBYTECODE='1',PAIRED_TASK=row['task'],PAIRED_ATTEMPT_ID=row['preflight_attempt_id'],ENTRY_ACCEPTANCE='1')
 env.pop('TAOTOKEN_API_KEY',None)
 log=(R/('acceptance-'+row['arm']+'.log')).open('xb')
 proc=subprocess.Popen(campaign.command(row,True),env=env,stdout=log,stderr=log,stdin=subprocess.DEVNULL)
 active.append((row,proc,log))
for row,proc,log in active:
 code=proc.wait();log.close()
 result=campaign.trial(row,True);result['harbor_exit']=code
 results.append(dict(arm=row['arm'],task=row['task'],**result))
 save('entry-acceptance-results.json',results)
 assert code==0 and result['engineering_clean'],result
 row.update(preflight_ok=True,preflight=result)
save('claimed-pending.json',dict(rows=rows))
lock=read(R/'algorithm-source-lock.json')
assert lock['runtime_sha256']==sha(R/'runtime-final.tar.gz')
for p,digest in read(R/'dependencies/ready.json')['files'].items():assert sha(R/'dependencies'/p)==digest
sealed=[p for p in R.iterdir() if p.suffix in ('.py','.mjs')]
sealed += [R/n for n in ['tasks.json','protocol.json','experiment.json','budget-profile.json','algorithm-source-lock.json','runtime-final.tar.gz','python-runtime.tar.gz','verifier-deps.tar.gz']]
save('ready.json',dict(passed=True,files={p.name:sha(p) for p in sealed}))
campaign.validate()
save('validation.json',dict(passed=True,paid_calls=0,entry_and_official_verifier=results,budget_tests_passed=True,source_hashes_verified=True,per_run_cny=8,campaign_cny=320,total_trials=40))
save('acceptance-progress.json',dict(state='passed',paid_calls=0))
print(json.dumps(read(R/'validation.json')),flush=True)
