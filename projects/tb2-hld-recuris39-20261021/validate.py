from pathlib import Path
import hashlib,json,subprocess,sys,tempfile
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
 coverage=read(R/'coverage.json');assert len(coverage['previous'])==50 and len(coverage['added'])==39 and len(set(coverage['union']))==89
 assert not set(coverage['previous'])&set(coverage['added'])
 rows=initial_rows(coverage['added'],{})
 assert len(rows)==78 and len({r['job'] for r in rows})==78
 selected=choose(rows,[],[]);assert len(selected)==8 and sum(r['arm']=='hld' for r in selected)==4
 assert len(choose(rows,['hld']*4+['recuris']*3,[]))==1
 assert choose(rows,['hld']*4+['recuris']*4,[])==[]
 profile=read(R/'budget-profile.json');assert profile['campaign_limit_microcny']==624000000 and profile['task_limit_microcny']==8000000
 assert set(profile['jobs'])=={r['job'] for r in rows}
 assert profile['model']=='deepseek-flash' and profile['solver_seconds']==7200
 with tempfile.TemporaryDirectory() as temp:
  ledger=Ledger(Path(temp)/'ledger.sqlite',profile)
  assert ledger.status()['remaining_microcny']==624000000
  try:ledger.reserve(dict(id='old-attempt',job='tb2hr50-01-hld-headless-terminal',arm='kz',endpoint=profile['endpoint'],model=profile['model'],max_tokens=1))
  except BudgetError as e:assert e.reason=='job_not_authorized'
  else:raise AssertionError('Old job accepted by new budget')
 lock=read(R/'continuation-lock.json');assert sha(R/'runtime-final.tar.gz')==lock['runtime_sha256']
 assert sha(R/'python-runtime.tar.gz')==lock['python_sha256']
 assert sha(R/'algorithm-source-lock.json')==lock['source_lock_sha256']
 old=read(R/'previous-results-lock.json');assert all(sha(Path(old['root'])/p)==s for p,s in old['files'].items())
 from warm_dependencies import recipe
 for name in coverage['added']:
  recipe(name)
  p=R/'manifests'/f'{name}.source.json';pin=read(p)
  assert pin['header_verified'] and pin['digest']=='sha256:'+sha(p.parent/f'{name}.manifest.json')
 subprocess.run([sys.executable,'-m','unittest','test_bounded_ledger'],cwd=R,check=True)
 acceptance=read(R/'acceptance.json');assert acceptance['passed'] and len(acceptance['checks'])==2 and acceptance['paid_calls']==0
 assert {x['arm'] for x in acceptance['checks']}=={'hld','recuris'}
 result=dict(passed=True,paid_calls=0,tasks=39,trials=78,concurrency=8,per_arm=4,budget_cny=624,per_run_cny=8,
             prior_result_files_unchanged=len(old['files']),runtime_identical=True,all_manifests_pinned=True,acceptance=acceptance)
 (R/'validation.json').write_text(json.dumps(result,indent=2)+'\n')
 subprocess.run([sys.executable,str(R/'seal.py')],check=True)
 import campaign
 campaign.precheck(resume=(R/'launch-once.marker').exists())
 print(json.dumps(result))
if __name__=='__main__':main()
