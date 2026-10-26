"""One keyless real grading acceptance for every affected task, including replay."""
import concurrent.futures,json,os,subprocess,sys,uuid,time
from pathlib import Path
R=Path(__file__).resolve().parent
import campaign
def one(task,arm):
 receipt=R/('accept-'+task+'.json')
 if receipt.exists() and json.loads(receipt.read_text()).get('engineering_clean'):return json.loads(receipt.read_text())
 row=dict(task=task,arm=arm,job='accept-score-'+task+'-'+uuid.uuid4().hex[:6],preflight_attempt_id=uuid.uuid4().hex)
 command=campaign.command(row,True)
 if task=='torch-pipeline-parallelism':command[command.index('-a')+1]='agents:ReplayDSH'
 env={k:v for k,v in os.environ.items() if not k.endswith(('API_KEY','AUTH_TOKEN')) and not k.startswith('CAMPAIGN_BUDGET_')}
 env.update(PYTHONPATH=str(R),PAIRED_TASK=task,PAIRED_ATTEMPT_ID=row['preflight_attempt_id'],PYTHONDONTWRITEBYTECODE='1',SCORE_SNAPSHOT_ACCEPTANCE='1')
 with (R/(row['job']+'.log')).open('x') as log:
  p=subprocess.run(command,env=env,cwd=R,stdin=subprocess.DEVNULL,stdout=log,stderr=log,timeout=10800)
 result=campaign.trial(row,True);result.update(task=task,arm=arm,paid_calls=0,exit_code=p.returncode,row=row)
 if p.returncode:result['engineering_clean']=False
 receipt.write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
 return result
if __name__=='__main__':
 tasks=list(dict.fromkeys(r['task'] for r in json.loads((R/'repair-plan.json').read_text())))
 chosen=sys.argv[1:] or tasks
 with concurrent.futures.ThreadPoolExecutor(3) as pool:
  results=list(pool.map(lambda t:one(t,'dsh' if t=='torch-pipeline-parallelism' else ['native-kz','kz-dsh','dsh'][tasks.index(t)%3]),chosen))
 all_results=[json.loads((R/('accept-'+t+'.json')).read_text()) for t in tasks if (R/('accept-'+t+'.json')).exists()]
 (R/'acceptance-scoring.json').write_text(json.dumps(dict(passed=len(all_results)==len(tasks) and all(r['engineering_clean'] for r in all_results),results=all_results,paid_calls=0),indent=2))
