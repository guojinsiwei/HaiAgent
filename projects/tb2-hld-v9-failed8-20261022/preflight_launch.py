"""Zero-model acceptance first; launch the authorized single v9 batch only on success."""
from pathlib import Path
import hashlib,json,os,subprocess,sys,tempfile,time,uuid
R=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_text())
def save(n,v):(R/n).write_text(json.dumps(v,indent=2))
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
 import campaign
 from spending import Ledger,BudgetError
 from experiment import validate_protocol
 validate_protocol(R)
 profile=read(R/'budget-profile.json');assert profile['task_limit_microcny']==8000000 and profile['campaign_limit_microcny']==64000000
 with tempfile.TemporaryDirectory(dir=R) as d:
  ledger=Ledger(Path(d)/'test.sqlite',profile)
  req=dict(id='first',job=profile['jobs'][0],arm='kz',endpoint=profile['endpoint'],model=profile['model'],max_tokens=16384)
  ledger.reserve(req);ledger.settle(dict(id='first',tokens=0))
  try:ledger.reserve({**req,'job':'old-experiment','id':'bad'})
  except BudgetError as e:assert e.reason=='job_not_authorized'
  else:raise AssertionError('Unrelated job admitted')
  with ledger.db() as db:db.execute('INSERT INTO calls VALUES (?,?,?,?,?,?,?)',('spent',profile['jobs'][0],'kz',7900000,7900000,'settled',time.time()))
  try:ledger.reserve({**req,'id':'over8'})
  except BudgetError as e:assert e.reason=='per_task_budget_exhausted'
  else:raise AssertionError('Task cap missing')
 (R/'candidate/node_modules').symlink_to(R/'bundle/kz/node_modules',target_is_directory=True)
 with (R/'candidate-targeted.log').open('w') as log:
  result=subprocess.run([str(R/'bundle/node/bin/node'),'--test',str(R/'candidate/tests/efficiency-v9.test.mjs')],cwd=R/'candidate',stdout=log,stderr=log,timeout=180)
 assert result.returncode==0,'v9 targeted tests failed'
 row=dict(job='entry-hld-v9-'+uuid.uuid4().hex[:8],arm='hld-new',task='chess-best-move',preflight_attempt_id=uuid.uuid4().hex)
 env={**os.environ,'PAIRED_TASK':row['task'],'PAIRED_ATTEMPT_ID':row['preflight_attempt_id'],'PYTHONPATH':str(R),'ENTRY_ACCEPTANCE':'1','PYTHONDONTWRITEBYTECODE':'1'}
 env.pop('TAOTOKEN_API_KEY',None)
 save('preflight-health.json',dict(state='real_entry_and_grader',paid_calls=0,job=row['job'],started=time.time()))
 with (R/(row['job']+'.log')).open('w') as log:
  process=subprocess.run(campaign.command(row,True),env=env,stdout=log,stderr=log,timeout=1800)
 result=campaign.trial(row,True);assert process.returncode==0 and result['engineering_clean'],result
 save('acceptance.json',dict(passed=True,paid_calls=0,checks=[result],candidate_targeted_tests_passed=True))
 for n,digest in read(R/'algorithm-source-lock.json')['files'].items():assert sha(R/'bundle'/n)==digest
 save('validation.json',dict(passed=True,paid_calls=0,tasks=8,trials=8,concurrency=4,per_run_cny=8,campaign_cny=64,entry_and_grader=result,v9_targeted_tests=True))
 files={p.name:sha(p) for p in R.iterdir() if p.is_file() and (p.suffix in ['.py','.mjs'] or p.name in ['tasks.json','protocol.json','experiment.json','budget-profile.json','runtime-final.tar.gz','python-runtime.tar.gz'])}
 save('ready.json',dict(passed=True,paid_calls=0,files=files))
 campaign.precheck()
 save('preflight-health.json',dict(state='passed_launching',paid_calls=0,updated=time.time()))
 subprocess.run([sys.executable,str(R/'launch_private.py')],check=True)
 save('preflight-health.json',dict(state='launched',updated=time.time(),paid_preflight_calls=0))
if __name__=='__main__':
 try:main()
 except Exception as error:
  save('preflight-health.json',dict(state='failed_no_paid_launch',error_type=type(error).__name__,error=str(error)[:1500],updated=time.time()));raise
