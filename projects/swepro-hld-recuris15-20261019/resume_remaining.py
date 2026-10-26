"""Resume seven never-solved pairs on the original immutable spending ledger."""
import concurrent.futures,copy,json,os,shutil,sqlite3,subprocess,sys,time
from pathlib import Path
import runner
from status import normalized
R=Path(__file__).resolve().parent
INDICES=[8,10,11,12,13,14,15]
def verify_admission(task):
 with sqlite3.connect(R/'spending.sqlite') as db:
  for a in ('hld','recuris'):
   j=f'swp-{task["index"]:02}-{a}'
   if db.execute('select count(*) from calls where job=?',(j,)).fetchone()[0] or (R/'jobs'/j).exists():raise RuntimeError('Refusing repeated paid work: '+j)
def supervise():
 runner.freeze_validate()
 with runner.supervisor_lock(R):
  old=runner.read(R/'health.json');assert old['state']=='finished'
  audit=R/'audit/engineering-repair-20261020';runner.save(audit/'health-before-resume.json',old)
  rows=normalized(R,old)['rows'];tasks=[t for t in runner.read(R/'tasks.json')['tasks'] if t['index'] in INDICES]
  # Task 10 already has an independently running official-image import; use it last.
  tasks.sort(key=lambda t:t['index']==10)
  assert len(tasks)==7
  for task in tasks:
   verify_admission(task)
   for a in ('hld','recuris'):rows[f'swp-{task["index"]:02}-{a}']=dict(task=task['name'],arm=a,state='pending',first_paid_run=True)
  budget=runner.BudgetService(R,host='127.0.0.1',port=0);services=runner.Services(budget)
  key=runner.read(Path.home()/'.config/appworld-credentials/taotoken-standby.json')['key']
  def checkpoint():
   with runner.STATE_LOCK:
    h=normalized(R,dict(rows=copy.deepcopy(rows)))
    h.update(updated=time.time(),pid=os.getpid(),state='finished' if all(r['state'] in ('completed','engineering_failed') for r in rows.values()) else 'running',phase='remaining14_engineering_repair',spending=budget.snapshot())
    runner.save(R/'health.json',h);runner.save(R/'status.json',h)
  def worker(task):
   jobs=[f'swp-{task["index"]:02}-{a}' for a in ('hld','recuris')]
   try:
    while shutil.disk_usage('/var/lib/docker').free<45*1024**3 or shutil.disk_usage(R).free<5*1024**3:
     with runner.STATE_LOCK:
      for j in jobs:rows[j]['state']='held_low_disk'
      checkpoint()
     time.sleep(20)
    with runner.STATE_LOCK:
     for j in jobs:rows[j]['state']='preflight'
     checkpoint()
    prior_image=runner.read(R/'preflight'/task['name']/'image.json')
    folder=runner.image_prepare(task)
    if task['index']==8:
     empty=runner.read(folder/'empty/result.json');gold=runner.read(folder/'gold/result.json')
     # Previously completed, unchanged original verifier runs are retained.
     assert prior_image['id']==task['image_id']
     if not runner.validate_preflight(task,folder,empty,gold):raise RuntimeError('Teleport preflight evidence failed validation')
    else:
     empty=runner.grade(task,folder/'repair-empty');gold=runner.grade(task,folder/'repair-gold',gold=True)
     if not runner.validate_preflight(task,folder,empty,gold):raise RuntimeError('Original empty/gold preflight failed')
    runner.save(folder/'repair-ready.json',dict(passed=True,empty=empty,gold=gold,source_hashes_unchanged=True))
    verify_admission(task)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
     fs=[pool.submit(runner.solve,task,a,services,budget,key,rows,checkpoint) for a in ('hld','recuris')]
     for f in fs:f.result()
   except Exception as exc:
    with runner.STATE_LOCK:
     for j in jobs:
      if rows[j]['state'] not in ('completed','engineering_failed'):rows[j].update(state='engineering_failed',error_type=type(exc).__name__,error=str(exc)[:400])
     checkpoint()
   finally:
    if task.get('image_id') and not task.get('image_preexisting') and all(rows[j]['state']=='completed' for j in jobs):
     p=subprocess.run(['docker','image','rm',task['image']],capture_output=True,text=True)
     runner.save(R/'preflight'/task['name']/'repair-image-release.json',dict(exit_code=p.returncode))
  try:
   checkpoint()
   with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    fs=[pool.submit(worker,t) for t in tasks]
    while not all(f.done() for f in fs):checkpoint();time.sleep(10)
    for f in fs:f.result()
  finally:checkpoint();services.close();budget.close()
if __name__=='__main__':
 if '--launch' in sys.argv:
  runner.freeze_validate()
  for t in runner.read(R/'tasks.json')['tasks']:
   if t['index'] in INDICES:verify_admission(t)
  with (R/'remaining14-launch.marker').open('x') as f:f.write(str(time.time()))
  with (R/'remaining14.log').open('xb') as f:p=subprocess.Popen([sys.executable,__file__],stdin=subprocess.DEVNULL,stdout=f,stderr=f,start_new_session=True)
  print(json.dumps(dict(pid=p.pid,new_runs=14,total_budget_cny=240,per_run_cny=8,ledger='original spending.sqlite',concurrency=4)))
 else:supervise()
