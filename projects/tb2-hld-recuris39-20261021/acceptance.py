"""Actual Harbor installation, denied model admission, original TB4 grading."""
from pathlib import Path
import json,os,subprocess,uuid
R=Path(__file__).resolve().parent
def main():
 import campaign
 results=[]
 for arm in ['hld','recuris']:
  row={'job':'entry-'+arm+'-'+uuid.uuid4().hex[:8],'arm':arm,'task':'build-pmars','preflight_attempt_id':uuid.uuid4().hex}
  env={**os.environ,'PAIRED_TASK':row['task'],'PAIRED_ATTEMPT_ID':row['preflight_attempt_id'],'PYTHONPATH':str(R),'ENTRY_ACCEPTANCE':'1','PYTHONDONTWRITEBYTECODE':'1'}
  env.pop('TAOTOKEN_API_KEY',None)
  with (R/(row['job']+'.log')).open('w') as out:
   p=subprocess.run(campaign.command(row,True),env=env,stdout=out,stderr=out,timeout=1800)
  result=campaign.trial(row,True);result.update(arm=arm,exit_code=p.returncode)
  results.append(result);print(json.dumps(result),flush=True)
  (R/'acceptance.json').write_text(json.dumps({'passed':all(x['engineering_clean'] and x['exit_code']==0 for x in results) and len(results)==2,'checks':results,'paid_calls':0},indent=2))
  if p.returncode or not result['engineering_clean']:raise RuntimeError('Keyless entry/original grading failed')
if __name__=='__main__':main()
