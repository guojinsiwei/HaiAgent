"""After the active campaign drains, admit only compile-gated tasks with ZERO calls."""
import concurrent.futures,json,os,sqlite3,subprocess,sys,time
from pathlib import Path
import runner
from status import normalized
R=Path(__file__).resolve().parent
def recover():
 while True:
  h=runner.read(R/'health.json')
  runner.save(R/'status.json',normalized(R,h))
  if h.get('state')=='finished':
   try:
    with runner.supervisor_lock(R):break
   except BlockingIOError:pass
  runner.save(R/'recovery-health.json',dict(state='waiting_for_current_campaign',updated=time.time(),purpose='Restore unpaid admissions blocked by compile-failure classification; no paid reruns'))
  time.sleep(20)
 with runner.supervisor_lock(R):
  h=runner.read(R/'health.json');assert h['state']=='finished'
  runner.save(R/'audit/verifier-directory-repair/health-before-unpaid-recovery.json',h)
  tasks=runner.read(R/'tasks.json')['tasks'];rows=normalized(R,h)['rows'];eligible=[]
  with sqlite3.connect(R/'spending.sqlite') as db:
   for t in tasks:
    jobs=[f'swp-{t["index"]:02}-{a}' for a in ('hld','recuris')]
    if not all(rows[j].get('paid_calls')==0 and rows[j].get('error')=='Official empty/gold preflight did not validate' for j in jobs):continue
    if any(db.execute('select count(*) from calls where job=?',(j,)).fetchone()[0] for j in jobs):continue
    if any((R/'jobs'/j).exists() for j in jobs):continue
    folder=R/'preflight'/t['name']
    old=runner.read(folder/'empty/result.json');g=runner.read(folder/'gold/result.json')
    empty=runner.assess(t,folder/'empty',old.get('exit_code'))
    gold=runner.assess(t,folder/'gold',g.get('exit_code'))
    if empty.get('failure_kind')!='compilation' or not empty['engineering_clean'] or not gold['engineering_clean'] or gold['reward']!=1:continue
    t['image_id']=runner.read(folder/'image.json')['id']
    if subprocess.run(['docker','image','inspect',t['image_id']],capture_output=True).returncode:continue
    runner.save(folder/'classification-repair.json',dict(previous=old,corrected=empty,gold=gold,paid_calls_before_recovery=0))
    for j in jobs:rows[j]=dict(task=t['name'],arm=rows[j]['arm'],state='pending',recovered_unpaid_admission=True)
    eligible.append(t)
  budget=runner.BudgetService(R,host='127.0.0.1',port=0);services=runner.Services(budget)
  def checkpoint():
   with runner.STATE_LOCK:
    summary={a:dict(completed=sum(r['arm']==a and r['state']=='completed' for r in rows.values()),passed=sum(r['arm']==a and r['state']=='completed' and r.get('reward')==1 for r in rows.values()),engineering_failed=sum(r['arm']==a and r['state']=='engineering_failed' for r in rows.values())) for a in ('hld','recuris')}
    state='finished' if all(r['state'] in ('completed','engineering_failed') for r in rows.values()) else 'running'
    runner.save(R/'health.json',dict(updated=time.time(),pid=os.getpid(),state=state,phase='unpaid_admission_recovery',summary=summary,rows=rows,spending=budget.snapshot()))
    runner.save(R/'status.json',normalized(R,runner.read(R/'health.json')))
    runner.save(R/'recovery-health.json',dict(state=state,updated=time.time(),eligible_tasks=[t['name'] for t in eligible],spending=budget.snapshot()))
  try:
   checkpoint();key=runner.read(Path.home()/'.config/appworld-credentials/taotoken-standby.json')['key']
   for task in eligible:
    assert runner.read(R/'entry-ready.json').get('passed')
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
     futures=[pool.submit(runner.solve,task,a,services,budget,key,rows,checkpoint) for a in ('hld','recuris')]
     while not all(f.done() for f in futures):checkpoint();time.sleep(10)
     for f in futures:f.result()
  finally:checkpoint();services.close();budget.close()
if __name__=='__main__':
 if '--launch' in sys.argv:
  with (R/'unpaid-recovery.marker').open('x') as f:f.write(str(time.time()))
  with (R/'unpaid-recovery.log').open('xb') as f:p=subprocess.Popen([sys.executable,__file__],stdin=subprocess.DEVNULL,stdout=f,stderr=f,start_new_session=True)
  print(json.dumps(dict(pid=p.pid,waiting_for_current_campaign=True,no_paid_retries=True)))
 else:recover()
