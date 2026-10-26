"""Two arms, fresh ledger, persistent admission, no automatic paid retries."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import fcntl,hashlib,json,os,shutil,subprocess,sys,time
from runner import R,read,save,trial
from spending import Ledger
from app_preflight import ensure
ARMS=('hld','recuris')
def validate():
 ready=read(R/'ready.json');assert ready.get('passed'),'Offline acceptance required'
 for name,digest in ready['files'].items():
  with (R/name).open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==digest,name
 p=read(R/'budget-profile.json')
 assert p['campaign_limit_microcny']==1120000000 and p['task_limit_microcny']==8000000
 assert len(set(p['jobs']))==140
 return p
def run_one(row,arm,key,ledger):
 try:ensure(row)
 except Exception as e:return dict(task=row['task'],arm=arm,state='needs_attention',engineering_fault='preflight_failed',error=str(e)[:1000],paid_calls=0)
 return trial(row,key,arm,ledger)
def campaign(key):
 profile=validate()
 with (R/'supervisor.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  assert (R/'pause-hld-20261020/resume-ready.json').exists(),'Explicit reconciliation required'
  ledger=Ledger(R/'spending.sqlite',profile)
  tasks=read(R/'task-manifest.json')['tasks']
  completed=read(R/'pause-hld-20261020/resume-ready.json')['completed']
  done=list(completed);finished={x['job'] for x in done}
  queue=[(r,'recuris') for r in tasks if 'recuris--'+r['task'] not in finished]
  assert all(not (R/'jobs'/('recuris--'+r['task'])).exists() for r,a in queue),'Existing attempt requires reconciliation'
  active={};auth_pause=False
  def checkpoint():
   s=dict(state='held_provider' if auth_pause and not active else 'running' if active else 'waiting_for_storage' if queue else 'complete',
    updated=time.time(),pid=os.getpid(),concurrency=len(active),completed=done,paused_arms=['hld'],enabled_arms=['recuris'],
    active=[dict(task=r['task'],arm=a,job=a+'--'+r['task']) for r,a in active.values()],
    pending=[dict(task=r['task'],arm=a) for r,a in queue],budget=ledger.status())
   save(R/'admissions.json',s);save(R/'health.json',s)
   return s
  checkpoint()
  with ThreadPoolExecutor(max_workers=2) as pool:
   while queue or active:
    for future in list(active):
     if future.done():
      r,a=active.pop(future)
      try:result=future.result()
      except Exception as e:result=dict(task=r['task'],arm=a,state='needs_attention',engineering_fault=type(e).__name__)
      done.append(result)
      if any(x in (401,402,403) for x in result.get('http_errors',[])):auth_pause=True
    budget=ledger.status()
    if budget['halt_reason'] or (budget['remaining_microcny']<387072 and not active):
     done.extend(dict(task=r['task'],arm=a,state='not_run_budget') for r,a in queue);queue=[]
    if auth_pause and not active:checkpoint();return
    while queue and len(active)<2 and not auth_pause and not budget['halt_reason']:
     if shutil.disk_usage('/var/lib/docker').free<24*2**30 or shutil.disk_usage(R).free<8*2**30:break
     # Admission is durable before the worker can issue a request.
     r,a=queue.pop(0)
     save(R/'admitted'/(a+'--'+r['task']+'.json'),dict(task=r['task'],arm=a,time=time.time(),automatic_paid_retry=False))
     active[pool.submit(run_one,r,a,key,ledger)]=(r,a)
    checkpoint()
    if queue or active:time.sleep(5)
  s=checkpoint();save(R/'summary.json',s)
def launch():
 validate()
 payload=json.loads(sys.stdin.readline(16384));key=payload['key'];assert key and key.isascii()
 (R/'launch-once.marker').open('x').write(str(time.time()))
 with (R/'supervisor.log').open('xb',buffering=0) as log:
  p=subprocess.Popen([sys.executable,__file__,'--supervise'],stdin=subprocess.PIPE,stdout=log,stderr=log,start_new_session=True)
  p.stdin.write((json.dumps(dict(key=key))+'\n').encode());p.stdin.close()
 time.sleep(2);assert p.poll() is None
 print(json.dumps(dict(started=True,pid=p.pid,runs=140,workers=2,cap_cny=1120)))
if __name__=='__main__':
 if '--supervise' in sys.argv:campaign(json.loads(sys.stdin.readline(16384))['key'])
 elif '--launch' in sys.argv:launch()
 else:validate();print('READY')
