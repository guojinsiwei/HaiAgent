"""Acceptance and spending checks, without any paid model calls."""
from pathlib import Path
import hashlib,json,subprocess,tempfile
R=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_text())
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
 from experiment import validate_protocol
 from queue_policy import initial_rows
 from tb_capacity_policy import choose
 from spending import Ledger,BudgetError
 validate_protocol(R)
 names=[t['name'] for t in read(R/'tasks.json')['tasks']];rows=initial_rows(names,{})
 assert len(rows)==20 and len({r['job'] for r in rows})==20
 chosen=choose(rows,[],[]);assert len(chosen)==8 and sum(r['arm']=='hld-old' for r in chosen)==4
 profile=read(R/'budget-profile.json');assert profile['campaign_limit_microcny']==160000000 and profile['task_limit_microcny']==8000000
 assert set(profile['jobs'])=={r['job'] for r in rows}
 with tempfile.TemporaryDirectory() as temp:
  ledger=Ledger(Path(temp)/'ledger.sqlite',profile)
  assert ledger.status()['remaining_microcny']==160000000
  try:ledger.reserve(dict(id='prior',job='tb2hr39-10-hld-crack-7z-hash',arm='kz',endpoint=profile['endpoint'],model=profile['model'],max_tokens=1))
  except BudgetError as e:assert e.reason=='job_not_authorized'
  else:raise AssertionError('Prior campaign incorrectly shares this budget')
 for name,digest in read(R/'baseline-lock.json').items():assert sha(R/'baseline'/name.replace('\\','/'))==digest
 for arm,files in read(R/'algorithm-source-lock.json').items():
  for name,digest in files.items():assert sha(R/'bundle'/name)==digest
 assert sha(R/'runtime-final.tar.gz')==read(R/'prepared.json')['runtime_sha256']
 a=read(R/'acceptance.json');assert a['passed'] and a['paid_calls']==0 and {x['arm'] for x in a['checks']}=={'hld-old','hld-new'}
 local=read(R/'offline-validation.json');assert local['no_unexplained_new_failures'] and local['new_mechanism_tests_passed']
 subprocess.run([str(R/'venv/bin/python'),'-m','unittest','test_bounded_ledger'],cwd=R,check=True)
 result=dict(passed=True,paid_calls=0,tasks=10,trials=20,concurrency=8,per_arm=4,budget_cny=160,per_run_cny=8,acceptance=a,offline=local)
 (R/'validation.json').write_text(json.dumps(result,indent=2)+'\n')
 subprocess.run([str(R/'venv/bin/python'),str(R/'seal.py')],check=True)
 import campaign
 campaign.precheck()
 print(json.dumps(result))
if __name__=='__main__':main()
