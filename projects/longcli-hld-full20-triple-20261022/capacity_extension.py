"""Extra four workers sharing job claims and the existing monetary ledger."""
from pathlib import Path
import fcntl,json,sys,time,threading,os
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(__file__).resolve().parent

def claimed(function,row,key,ledger,probe=False):
 if probe:return function(row,key,ledger,probe=True)
 from common import save
 claims=ROOT/'claims';claims.mkdir(exist_ok=True)
 job='hld--'+row['task'];directory=ROOT/'jobs'/job
 with (claims/(job+'.lock')).open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  summary=directory/'summary.json'
  if summary.exists():return json.loads(summary.read_text())
  # A job directory without a held lock is an abandoned attempt; never buy it again.
  if directory.exists():return dict(job=job,task=row['task'],state='needs_attention',engineering_fault='existing_attempt_requires_recovery',paid_retry=False)
  return function(row,key,ledger)

def aggregate(value):
 value=dict(value);protocol=json.loads((ROOT/'protocol.json').read_text());active=[];completed=[];pending=[]
 for row in protocol['tasks']:
  d=ROOT/'jobs'/('hld--'+row['task']);p=d/'summary.json'
  if p.exists():completed.append(json.loads(p.read_text()))
  elif d.exists():active.append(row['task'])
  else:pending.append(row['task'])
 value.update(concurrency_limit=10,active=active,completed=completed,pending=pending)
 return value

def install_live():
 """Install at the existing grader import boundary, before any queued job is dispatched."""
 main=sys.modules.get('__main__')
 if not main or Path(getattr(main,'__file__','')).name!='runner.py':return
 if getattr(main,'_capacity_extension_installed',False):return
 original=main.solve;original_save=main.save
 def solve(row,key,ledger,probe=False):return claimed(original,row,key,ledger,probe)
 def save(path,value):
  if Path(path)==ROOT/'health.json':value=aggregate(value)
  return original_save(path,value)
 main.solve=solve;main.save=save;main._capacity_extension_installed=True
 original_save(ROOT/'capacity-hook-installed.json',dict(pid=os.getpid(),time=time.time(),atomic_job_claims=True))

def selftest():
 import tempfile
 global ROOT
 previous=ROOT
 with tempfile.TemporaryDirectory() as temporary:
  ROOT=Path(temporary);count=[]
  def fake(row,key,ledger):
   count.append(1);d=ROOT/'jobs'/('hld--'+row['task']);d.mkdir(parents=True)
   time.sleep(.1);result=dict(task=row['task'],state='graded');(d/'summary.json').write_text(json.dumps(result));return result
  with ThreadPoolExecutor(max_workers=2) as pool:
   a=pool.submit(claimed,fake,dict(task='one'),'',None);b=pool.submit(claimed,fake,dict(task='one'),'',None)
   assert a.result()==b.result() and len(count)==1
  d=ROOT/'jobs/hld--abandoned';d.mkdir();assert claimed(fake,dict(task='abandoned'),'',None)['paid_retry'] is False
 ROOT=previous

def main():
 from common import save
 import runner
 from spending import Ledger
 selftest();plan=json.loads((ROOT/'capacity-plan.json').read_text());protocol=runner.validate()
 assert len(plan['extra_tasks'])==len(set(plan['extra_tasks']))
 secret=json.loads((Path.home()/'.config/appworld-credentials/taotoken-standby.json').read_text());key=secret.get('key') or secret.get('api_key') or secret.get('apiKey');assert key
 ledger=Ledger(ROOT/'spending.sqlite',json.loads((ROOT/'budget-profile.json').read_text()))
 rows=[next(r for r in protocol['tasks'] if r['task']==name) for name in plan['extra_tasks']]
 with (ROOT/'capacity-launch.marker').open('x') as f:f.write(str(os.getpid()))
 with ThreadPoolExecutor(max_workers=4) as pool:
  futures={pool.submit(claimed,runner.solve,row,key,ledger):row for row in rows}
  while futures:
   for f in list(futures):
    if f.done():f.result();del futures[f]
   save(ROOT/'capacity-health.json',dict(state='running' if futures else 'complete',pid=os.getpid(),updated=time.time(),extra_slots=4,remaining=[r['task'] for r in futures.values()],combined=aggregate({}),budget=ledger.status()))
   if futures:time.sleep(10)

if __name__=='__main__':main()
