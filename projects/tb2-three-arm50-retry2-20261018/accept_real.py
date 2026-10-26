"""Real Docker installation, collection and official verifier; no API key."""
import concurrent.futures,json,os,subprocess,uuid
from pathlib import Path
from campaign import command,trial
from storage import atomic_json
R=Path(__file__).resolve().parent
def one(arm):
 row=dict(task='tune-mjcf',arm=arm,job='accept-real-'+arm,preflight_attempt_id=uuid.uuid4().hex)
 env={k:v for k,v in os.environ.items() if not k.endswith(('API_KEY','AUTH_TOKEN')) and not k.startswith('CAMPAIGN_BUDGET_')}
 env.update(PYTHONPATH=str(R),PAIRED_TASK=row['task'],PAIRED_ATTEMPT_ID=row['preflight_attempt_id'],PYTHONDONTWRITEBYTECODE='1')
 with (R/('accept-real-'+arm+'.log')).open('x') as log:
  p=subprocess.run(command(row,True),env=env,cwd=R,stdin=subprocess.DEVNULL,stdout=log,stderr=log)
 result=trial(row,True);result.update(arm=arm,harbor_exit=p.returncode,paid_calls=0)
 atomic_json(R/('accept-real-'+arm+'.json'),result)
 print(json.dumps(result),flush=True);return result
if __name__=='__main__':
 with concurrent.futures.ThreadPoolExecutor(2) as pool:results=list(pool.map(one,['native-kz','kz-dsh','dsh']))
 passed=all(r['engineering_clean'] and r['harbor_exit']==0 for r in results)
 atomic_json(R/'acceptance-real.json',dict(passed=passed,results=results,paid_calls=0))
 raise SystemExit(0 if passed else 1)
