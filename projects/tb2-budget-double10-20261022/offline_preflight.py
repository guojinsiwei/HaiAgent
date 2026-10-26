"""Run every selected original verifier and a blocked production entry, without credentials."""
from pathlib import Path
import concurrent.futures,json,os,subprocess,uuid,sys
import campaign
R=Path(__file__).resolve().parent
def one(row):
 row=dict(row);row['preflight_attempt_id']=uuid.uuid4().hex
 env=dict(os.environ,PYTHONPATH=str(R)+':'+str(R/'dependencies'),PYTHONDONTWRITEBYTECODE='1',ENTRY_ACCEPTANCE='1',PAIRED_TASK=row['task'],PAIRED_ATTEMPT_ID=row['preflight_attempt_id'])
 env.pop('TAOTOKEN_API_KEY',None)
 with (R/('offline-'+row['job']+'-'+row['preflight_attempt_id']+'.log')).open('x') as out:
  p=subprocess.run(campaign.command(row,True),env=env,stdout=out,stderr=out)
 result=campaign.trial(row,True);result['harbor_exit']=p.returncode
 row.update(state='pending' if result['engineering_clean'] and p.returncode==0 else 'engineering_failure',preflight_ok=result['engineering_clean'] and p.returncode==0,preflight=result)
 print(json.dumps(dict(job=row['job'],passed=row['preflight_ok'],result=result)),flush=True)
 return row
def main():
 rows=json.loads((R/'claimed-pending.json').read_text())['rows']
 assert not (R/'launch-once.marker').exists()
 if '--retry-failed' in sys.argv:
  pending=[x for x in rows if not x.get('preflight_ok')]
  for x in pending:
   src=R/'preflight'/('preflight-'+x['job'])
   dest=R/'preflight-history'/((x.get('preflight_attempt_id') or uuid.uuid4().hex)+'-'+x['job'])
   assert src.resolve().is_relative_to(R.resolve()) and dest.resolve().is_relative_to(R.resolve())
   if src.exists():dest.parent.mkdir(exist_ok=True);src.rename(dest)
 else:
  assert all(not x.get('preflight_ok') for x in rows);pending=rows
 with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:changed=list(pool.map(one,pending))
 byjob={x['job']:x for x in changed};done=[byjob.get(x['job'],x) for x in rows]
 passed=all(r['preflight_ok'] for r in done)
 (R/'claimed-pending.json').write_text(json.dumps(dict(rows=done),indent=2))
 (R/'acceptance.json').write_text(json.dumps(dict(passed=passed,paid_calls=0,checks=done),indent=2))
 print('ALL_PREFLIGHT_PASSED',passed,flush=True)
if __name__=='__main__':main()
