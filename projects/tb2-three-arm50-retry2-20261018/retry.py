"""One authorized engineering retry batch, sharing original charges and limits."""
import collections,datetime,hashlib,json,os,secrets,shutil,sqlite3,subprocess,sys,threading,time
from pathlib import Path
R=Path(__file__).resolve().parent
P=R.parent/'tb2-three-arm50-20261017'
from storage import atomic_json
from recovery import owned_alive,process_identity,completed_attempt
from spending import Ledger,server_for
S=R.parent/'tb2-three-arm50-retry-20261018'
TERMINAL={'done','engineering_failure','historical'}
def read(p):
 try:return json.loads(Path(p).read_text())
 except (FileNotFoundError,ValueError):return {}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def validate():
 seal=read(R/'retry-seal.json')
 assert seal.get('tests_passed') is True,'Offline checks required'
 acceptance=read(R/'acceptance-real.json')
 assert acceptance.get('passed') is True and len(acceptance.get('results',[]))==3,'Real Docker acceptance required'
 for name in ('runtime-final.tar.gz','python-runtime.tar.gz','native-runtime.tar.gz','verifier-deps.tar.gz'):assert not (R/name).is_symlink(),'Archive symlink forbidden'
 for name,digest in seal['files'].items():assert sha(R/name)==digest,'Retry source drift: '+name
 assert read(P/'budget-profile.json')==read(R/'budget-profile.json'),'Original budget profile changed'
 for name,digest in read(R/'parent-source-seal.json')['files'].items():assert sha(P/name)==digest,'Parent source drift: '+name
def job_charge(job):
 with sqlite3.connect('file:'+str(P/'spending.sqlite')+'?mode=ro',uri=True) as db:
  return db.execute("SELECT count(*),coalesce(sum(CASE WHEN state='settled' THEN actual ELSE reserved END),0) FROM calls WHERE job=?",(job,)).fetchone()
def select_rows(parent,charge=job_charge,receipt_check=True):
 rows=[];skipped=[];profile=read(R/'budget-profile.json')
 reservation=profile['input_ceiling_tokens']*2+profile['max_output_tokens']*8
 for old in parent['rows']:
  if old['state']!='engineering_failure':continue
  result=old.get('result',{})
  if result.get('reason') in ('runner_receipt_missing_quarantined','result_collection_error','dispatch_error'):
   skipped.append(dict(job=old['job'],reason='requires_manual_ownership_reconciliation'));continue
  offline=result.get('reason')=='preflight_failed'
  if receipt_check and completed_attempt(P,old,offline) is None:
   skipped.append(dict(job=old['job'],reason='original_attempt_not_confirmed_finished'));continue
  count,charged=charge(old['job'])
  if charged+reservation>profile['task_limit_microcny'] or count>=profile['requests_per_task']:
   skipped.append(dict(job=old['job'],reason='original_task_budget_insufficient',charged_microcny=charged,remaining_microcny=profile['task_limit_microcny']-charged));continue
  rows.append(dict(task=old['task'],arm=old['arm'],stage='retry',job='retry2-'+old['job'],budget_job=old['job'],state='pending',original_result=result,previous_charged_microcny=charged,remaining_microcny=profile['task_limit_microcny']-charged))
 return rows,skipped
def select_remaining(parent):
 previous=read(S/'health.json')
 assert previous.get('state')=='finished' and not previous.get('active') and not owned_alive(previous.get('supervisor_identity')),'Previous retry must be quiescent'
 rows,skipped=select_rows(parent)
 prior={r['budget_job']:r for r in previous['rows']}
 eligible=[]
 for row in rows:
  old=prior.get(row['budget_job'])
  if old is None or old['state']!='engineering_failure':
   skipped.append(dict(job=row['budget_job'],reason='previous_retry_already_clean_or_not_selected'));continue
  offline=old.get('result',{}).get('reason')=='preflight_failed'
  if completed_attempt(S,old,offline) is None:
   skipped.append(dict(job=row['budget_job'],reason='previous_retry_ownership_not_confirmed'));continue
  row['previous_retry_result']=old.get('result',{});eligible.append(row)
 return eligible,skipped

def schedule(state,**extra):
 atomic_json(R/'schedule.json',dict(state=state,updated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),supervisor_identity=process_identity(os.getpid()),parent=str(P),**extra))
class SharedBudget:
 def __init__(self,*_,**__):
  self.ledger=Ledger(P/'spending.sqlite',read(P/'budget-profile.json'))
  # Never reconcile/reset parent reservations. Unknown charges remain reserved.
  self.token=secrets.token_urlsafe(32);self.url='http://10.123.0.1:28726'
  self.server=server_for(self.ledger,self.token,'10.123.0.1',28726)
  threading.Thread(target=self.server.serve_forever,daemon=True).start()
 def snapshot(self):return self.ledger.status()
 def close(self):self.server.shutdown();self.server.server_close()
def candidates(rows,active_arms):
 busy=collections.Counter(active_arms);out=[]
 for row in rows:
  if sum(busy.values())>=3:break
  if row['state']=='pending' and busy[row['arm']]<1:out.append(row);busy[row['arm']]+=1
 return out
def warm_images(rows):
 import tomllib
 for task in dict.fromkeys(r['task'] for r in rows if r['original_result'].get('exception_type')=='EnvironmentStartTimeoutError'):
  manifest=tomllib.loads((R/'dependencies/official/tasks'/task/'task.toml').read_text())
  image=manifest.get('environment',{}).get('docker_image')
  if not image:continue
  check=subprocess.run(['docker','image','inspect',image],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20)
  if check.returncode==0:continue
  while shutil.disk_usage('/var/lib/docker').free<45*1024**3:
   schedule('waiting_image_disk',task=task,needed_free_gib=45);time.sleep(30)
  schedule('warming_image',task=task,image=image,paid_calls=0)
  env={k:v for k,v in os.environ.items() if k!='TAOTOKEN_API_KEY' and not k.startswith('CAMPAIGN_BUDGET_')}
  with (R/('image-'+task+'.log')).open('xb') as log:
   try:code=subprocess.run(['docker','pull',image],env=env,stdout=log,stderr=log,timeout=1800).returncode
   except subprocess.TimeoutExpired:code=124
  atomic_json(R/('image-'+task+'.json'),dict(image=image,exit_code=code,paid_calls=0))
  if code:
   for row in rows:
    if row['task']==task:row.update(state='engineering_failure',engineering_clean=False,result=dict(engineering_clean=False,reason='image_prewarm_failed',paid_calls=0))
def supervise():
 validate()
 while True:
  parent=read(P/'health.json')
  if parent.get('state')=='finished' and not parent.get('active') and not owned_alive(parent.get('supervisor_identity')):break
  count=sum(r['state']=='engineering_failure' for r in parent.get('rows',[]))
  state='waiting_first_pass' if owned_alive(parent.get('supervisor_identity')) else 'held_parent_not_finished'
  schedule(state,engineering_failures_seen=count,parent_summary=parent.get('summary'),paid_calls=0)
  time.sleep(30)
 validate()
 rows,skipped=select_remaining(parent)
 atomic_json(R/'parent-final.json',parent)
 atomic_json(R/'retry-plan.json',dict(rows=rows,skipped=skipped,automatic_batches=1,max_concurrency=3,per_arm_concurrency=1,budget='Original shared 600 CNY ledger and cumulative 4 CNY per original arm/task'))
 if not rows:schedule('finished_no_eligible_retries',skipped=skipped);return
 # Retain all available parent image/user/workdir fingerprints.
 shutil.copytree(P/'environment-locks',R/'environment-locks',dirs_exist_ok=True)
 warm_images(rows)
 import campaign
 campaign.validate=validate;campaign.BudgetService=SharedBudget;campaign.PORT=28725
 campaign.initial_rows=lambda *_:rows;campaign.candidates=candidates
 schedule('running_retry',eligible_trials=len(rows),skipped=skipped)
 campaign.supervise()
 final=read(R/'health.json');schedule('finished' if final.get('state')=='finished' else 'held',summary=final.get('summary'),spending=final.get('spending'),skipped=skipped)
def launch():
 validate()
 assert not (R/'launch-once.marker').exists(),'Retry already launched; inspect before recovery'
 bundle=json.loads(sys.stdin.readline());key=bundle.pop('key')
 assert isinstance(key,str) and key.startswith('sk-'),'Invalid credential format'
 with (R/'launch-once.marker').open('x') as f:f.write(str(time.time()))
 with (R/'supervisor.log').open('xb') as log:
  child=subprocess.Popen([str(R/'venv/bin/python'),str(R/'retry.py'),'--supervise'],env=dict(os.environ,TAOTOKEN_API_KEY=key,PYTHONDONTWRITEBYTECODE='1'),stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True,cwd=R)
 key='';bundle.clear();time.sleep(2)
 assert child.poll() is None,'Retry watcher exited; inspect log'
 print(json.dumps(dict(pid=child.pid,detached=True,credential_received=True,state=read(R/'schedule.json').get('state'),model_calls_started=False)))
if __name__=='__main__':
 if '--launch' in sys.argv:launch()
 elif '--supervise' in sys.argv:supervise()
 else:validate();print('RETRY_READY')
