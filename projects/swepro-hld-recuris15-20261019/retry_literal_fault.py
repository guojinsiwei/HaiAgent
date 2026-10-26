"""One bounded repair retry, sharing the unchanged campaign ledger and job ID."""
import hashlib,json,os,sqlite3,subprocess,sys,time
from pathlib import Path
import runner

R=Path(__file__).resolve().parent
JOB='swp-08-recuris'
AUDIT=R/'audit/engineering-repair-20261020'

def validate():
 runner.freeze_validate()
 folder=R/'jobs'/JOB
 assert (folder/'model.patch').read_bytes()==b'', 'Do not repeat a completed submission'
 state=runner.read(folder/'live/recuris/state.json')
 assert any(f.get('op')=='dsh_host' and 'malformed prompt variable reference' in f.get('message','') for f in state['faults'])
 assert state['usage']['nativeTools']==2
 with sqlite3.connect(R/'spending.sqlite') as db:
  n,cost,pending=db.execute("select count(*),coalesce(sum(actual),0),sum(state!='settled') from calls where job=?",(JOB,)).fetchone()
 assert n==4 and pending==0 and cost<8000000
 assert not (AUDIT/'recuris-08-before-literal').exists()
 return dict(prior_calls=n,prior_cost_microcny=cost,prior_patch_sha256=hashlib.sha256(b'').hexdigest())

def work():
 evidence=validate()
 task=next(t for t in runner.read(R/'tasks.json')['tasks'] if t['index']==8)
 image=runner.read(R/'preflight'/task['name']/'image.json')
 task['image_id']=image['id']
 assert runner.inspect(task['image'])['Id']==task['image_id']
 # The first attempt only inspected files. Keep its session, evidence and score.
 (R/'jobs'/JOB).rename(AUDIT/'recuris-08-before-literal')
 budget=runner.BudgetService(R,host='127.0.0.1',port=0)
 services=runner.Services(budget)
 rows={JOB:dict(task=task['name'],arm='recuris',state='pending',repair='literal_memory_context',**evidence)}
 def checkpoint():
  runner.save(R/'literal-retry-health.json',dict(updated=time.time(),pid=os.getpid(),rows=rows,spending=budget.snapshot(),original_ledger=True))
 try:
  checkpoint()
  key=runner.read(Path.home()/'.config/appworld-credentials/taotoken-standby.json')['key']
  runner.solve(task,'recuris',services,budget,key,rows,checkpoint)
 finally:
  checkpoint();services.close();budget.close()

if __name__=='__main__':
 if '--launch' in sys.argv:
  evidence=validate()
  with (R/'literal-retry-launch.marker').open('x') as f:f.write(str(time.time()))
  with (R/'literal-retry.log').open('xb') as f:
   p=subprocess.Popen([sys.executable,__file__],stdin=subprocess.DEVNULL,stdout=f,stderr=f,start_new_session=True)
  print(json.dumps(dict(pid=p.pid,job=JOB,ledger='original spending.sqlite',per_job_limit_cny=8,campaign_limit_cny=240,**evidence)))
 else:work()
