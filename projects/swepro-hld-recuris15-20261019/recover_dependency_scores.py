"""Regrade two immutable saved submissions; never invoke a solver or a model."""
import concurrent.futures,hashlib,json,sqlite3,time
from pathlib import Path
import runner
R=Path(__file__).resolve().parent

def job_ledger(job):
 with sqlite3.connect(R/'spending.sqlite') as db:
  return list(db.execute('select count(*),coalesce(sum(actual),0) from calls where job=?',(job,)).fetchone())

def recover(arm):
 job='swp-08-'+arm;folder=R/'jobs'/job;patch=folder/'model.patch'
 original=runner.read(folder/'solver.json')['patch_sha256'];assert hashlib.sha256(patch.read_bytes()).hexdigest()==original
 before=job_ledger(job)
 task=next(t for t in runner.read(R/'tasks.json')['tasks'] if t['index']==8)
 task['image_id']=runner.read(R/'preflight'/task['name']/'image.json')['id']
 output=folder/'grade-dependency-recovery';assert not output.exists()
 scored=runner.grade(task,output,patch)
 assert hashlib.sha256(patch.read_bytes()).hexdigest()==original and job_ledger(job)==before
 receipt=dict(job=job,score=scored,patch_sha256=original,ledger_before=before,ledger_after=job_ledger(job),new_model_calls=0,time=time.time())
 runner.save(folder/'dependency-score-recovery.json',receipt)
 if scored['engineering_clean']:
  (folder/'grade').rename(folder/'grade-before-dependency-cache')
  output.rename(folder/'grade')
 return receipt

if __name__=='__main__':
 runner.freeze_validate()
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
  results=list(pool.map(recover,['hld','recuris']))
 runner.save(R/'audit/dependency-repair-20261020/recovered-scores.json',results)
 print(json.dumps(results,indent=2),flush=True)
