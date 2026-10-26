"""Continue only four unstarted jobs after required-interface preflight repair."""
import concurrent.futures,copy,datetime,os,shutil,sqlite3,subprocess,sys,time
from pathlib import Path
import runner
from status import normalized
R=Path(__file__).resolve().parent
INDICES=[14,15]

def unpaid(task):
 with sqlite3.connect(R/'spending.sqlite') as db:
  for arm in ['hld','recuris']:
   job=f'swp-{task["index"]:02}-{arm}'
   if db.execute('select count(*) from calls where job=?',(job,)).fetchone()[0] or (R/'jobs'/job).exists():
    raise RuntimeError('Refusing repeated paid job '+job)

def supervise():
 runner.freeze_validate()
 with runner.supervisor_lock(R):
  rows=normalized(R,runner.read(R/'health.json'))['rows']
  tasks=sorted([t for t in runner.read(R/'tasks.json')['tasks'] if t['index'] in INDICES],key=lambda t:INDICES.index(t['index']))
  for t in tasks:
   unpaid(t)
   for arm in ['hld','recuris']:rows[f'swp-{t["index"]:02}-{arm}']=dict(task=t['name'],arm=arm,state='pending',first_paid_run=True,dependency_admission=True)
  budget=runner.BudgetService(R,host='127.0.0.1',port=0);services=runner.Services(budget)
  key=runner.read(Path.home()/'.config/appworld-credentials/taotoken-standby.json')['key']
  def checkpoint():
   with runner.STATE_LOCK:
    h=normalized(R,dict(rows=copy.deepcopy(rows)))
    h.update(updated=time.time(),pid=os.getpid(),state='finished' if all(x['state'] in ('completed','engineering_failed') for x in h['rows'].values()) else 'running',phase='interface_preflight_repaired_remaining4',spending=budget.snapshot())
    runner.save(R/'health.json',h);runner.save(R/'status.json',h)
  def worker(task):
   jobs=[f'swp-{task["index"]:02}-{a}' for a in ['hld','recuris']]
   try:
    while shutil.disk_usage('/var/lib/docker').free<45*1024**3 or shutil.disk_usage(R).free<5*1024**3:
     with runner.STATE_LOCK:
      for j in jobs:rows[j]['state']='held_low_disk'
      checkpoint()
     time.sleep(20)
    with runner.STATE_LOCK:
     for j in jobs:rows[j]['state']='preflight'
     checkpoint()
    folder=runner.image_prepare(task)
    empty=runner.read(folder/'dependency-empty/result.json');gold=runner.read(folder/'dependency-gold/result.json')
    if not empty:raise RuntimeError('Missing preserved empty evidence')
    if not gold:raise RuntimeError('Missing preserved gold evidence')
    if not runner.validate_preflight(task,folder,empty,gold):raise RuntimeError('Official empty/gold preflight failed; no model admitted')
    runner.save(folder/'dependency-ready.json',dict(empty=empty,gold=gold,source_hashes_unchanged=True,time=time.time()))
    unpaid(task)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
     fs=[pool.submit(runner.solve,task,a,services,budget,key,rows,checkpoint) for a in ['hld','recuris']]
     for f in fs:f.result()
   except Exception as exc:
    with runner.STATE_LOCK:
     for j in jobs:
      if rows[j]['state'] not in ('completed','engineering_failed'):rows[j].update(state='engineering_failed',error_type=type(exc).__name__,error=str(exc)[:450])
     checkpoint()
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
   if t['index'] in INDICES:unpaid(t)
  with (R/'interface-resume.marker').open('x') as f:f.write(str(time.time()))
  with (R/'interface-resume.log').open('xb') as f:p=subprocess.Popen([sys.executable,__file__],stdin=subprocess.DEVNULL,stdout=f,stderr=f,start_new_session=True)
  print(dict(pid=p.pid,original_ledger=True,new_jobs=4,concurrency=4))
 else:supervise()
