"""Run paired old/new HLD on five fixed tasks. Preserve every original result."""
import concurrent.futures,copy,hashlib,json,os,random,shutil,sqlite3,subprocess,sys,time
from pathlib import Path
import runner
R=Path(__file__).resolve().parent
OLD=R.parent/'swepro-hld-recuris15-20261019'
def admission():
 runner.freeze_validate()
 a=runner.read(R/'budget-allocation.json')
 assert runner.read(OLD/'health.json')['state']=='finished'
 with sqlite3.connect(OLD/'spending.sqlite') as db:
  rows=db.execute('select * from calls order by id').fetchall()
 assert hashlib.sha256(json.dumps(rows).encode()).hexdigest()==a['original_calls_sha256'],'Original paid campaign changed after allocation'
 assert a['combined_max_microcny']<=a['original_total_cap_microcny']
 assert not (R/'health.json').exists(),'Comparison already launched'
def qualify(task):
 """Reuse saved original calibration evidence, verify image and frozen file hashes."""
 f=runner.image_prepare(task);original=OLD/'preflight'/task['name']
 assert runner.read(original/'image.json')['id']==task['image_id'],'Image drift'
 controls={}
 for kind in ['empty','gold']:
  for prefix in ['dependency-','repair-','']:
   p=original/(prefix+kind);result=runner.read(p/'result.json')
   if result and (kind=='empty' or result.get('engineering_clean') and result.get('reward')==1):
    controls[kind]=(p,result);break
 assert len(controls)==2,'Missing official controls'
 ep,e=controls['empty'];gp,g=controls['gold']
 # Original adapter has the exact Teleport dependency-baseline exception.
 assert runner.validate_preflight(task,original,e,g),'Original empty/gold qualification rejected'
 assert g['required_passed']==g['required'] and g['required']>0
 runner.save(f/'paired-qualification.json',dict(image_id=task['image_id'],empty=e,gold=g,
  evidence={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for folder in [ep,gp] for p in folder.rglob('*') if p.is_file()},
  model_calls=0,original_tests_unchanged=True))
 return task
def preflight():
 runner.freeze_validate()
 tasks=runner.read(R/'tasks.json')['tasks']
 for t in tasks:qualify(t)
 # Both real entrypoints reach a dummy-key zero-budget block, never a provider.
 pr=R/'entry-budget';pr.mkdir()
 profile=runner.read(R/'budget-profile.json');profile.update(campaign_limit_microcny=1,task_limit_microcny=1,jobs=['entry-test'])
 runner.save(pr/'budget-profile.json',profile)
 budget=runner.BudgetService(pr,host='127.0.0.1',port=0);services=runner.Services(budget)
 try:
  for arm in ['old','new']:runner.probe(tasks[0],arm,services,budget)
 finally:services.close();budget.close()
 runner.save(R/'preflight-ready.json',dict(passed=True,time=time.time(),model_calls=0,task_count=5,arms=['old','new']))
def supervise():
 admission()
 assert runner.read(R/'preflight-ready.json').get('passed')
 with runner.supervisor_lock(R):
  tasks=runner.read(R/'tasks.json')['tasks'];random.Random(20261020).shuffle(tasks)
  rows={f'swp-{t["index"]:02}-{a}':dict(task=t['name'],arm=a,state='pending') for t in tasks for a in ['old','new']}
  budget=runner.BudgetService(R,host='127.0.0.1',port=0);services=runner.Services(budget)
  key=runner.read(Path.home()/'.config/appworld-credentials/taotoken-standby.json')['key']
  def checkpoint():
   with runner.STATE_LOCK:
    summary={a:dict(scored=sum(x['arm']==a and x.get('official_score_valid') is True for x in rows.values()),
      passed=sum(x['arm']==a and x.get('official_score_valid') is True and x.get('reward')==1 for x in rows.values()),
      completed=sum(x['arm']==a and x['state']=='completed' for x in rows.values()),
      engineering_failed=sum(x['arm']==a and x['state']=='engineering_failed' for x in rows.values())) for a in ['old','new']}
    h=dict(updated=time.time(),pid=os.getpid(),state='finished' if all(x['state'] in ['completed','engineering_failed'] for x in rows.values()) else 'running',
      rows=copy.deepcopy(rows),summary=summary,spending=budget.snapshot(),concurrency=4)
    runner.save(R/'health.json',h);runner.save(R/'status.json',h)
  def worker(t):
   jobs=[f'swp-{t["index"]:02}-{a}' for a in ['old','new']]
   try:
    while shutil.disk_usage('/var/lib/docker').free<45*1024**3 or shutil.disk_usage(R).free<5*1024**3:
     with runner.STATE_LOCK:
      for j in jobs:rows[j]['state']='held_low_disk'
      checkpoint()
     time.sleep(20)
    runner.image_prepare(t)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
     arms=['old','new'];random.Random(20261020+t['index']).shuffle(arms)
     fs=[pool.submit(runner.solve,t,a,services,budget,key,rows,checkpoint) for a in arms]
     for f in fs:f.result()
   except Exception as e:
    with runner.STATE_LOCK:
     for j in jobs:
      if rows[j]['state'] not in ['completed','engineering_failed']:rows[j].update(state='engineering_failed',error=type(e).__name__+': '+str(e)[:350])
     checkpoint()
  try:
   checkpoint()
   with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    fs=[pool.submit(worker,t) for t in tasks]
    while not all(f.done() for f in fs):checkpoint();time.sleep(10)
    for f in fs:f.result()
  finally:checkpoint();services.close();budget.close()
if __name__=='__main__':
 if '--preflight' in sys.argv:preflight()
 elif '--launch' in sys.argv:
  admission()
  assert runner.read(R/'preflight-ready.json').get('passed')
  with (R/'launch.marker').open('x') as f:f.write(str(time.time()))
  with (R/'controller.log').open('xb') as f:
   p=subprocess.Popen([sys.executable,__file__],stdin=subprocess.DEVNULL,stdout=f,stderr=f,start_new_session=True)
  print(dict(pid=p.pid,runs=10,concurrency=4,per_run_cny=8,comparison_cap_cny=80))
 else:supervise()
