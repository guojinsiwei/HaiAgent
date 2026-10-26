from pathlib import Path
import hashlib,json,subprocess,tempfile
R=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_text())
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
 from experiment import validate_protocol
 from spending import Ledger,BudgetError
 from tb_capacity_policy import choose
 validate_protocol(R);a=read(R/'acceptance.json');assert a['passed'] and len(a['checks'])==10 and a['paid_calls']==0
 assert all(r['preflight_ok'] for r in read(R/'claimed-pending.json')['rows'])
 for name,digest in read(R/'algorithm-source-lock.json').items():assert sha(R/'bundle'/name)==digest
 assert sha(R/'runtime-final.tar.gz')==read(R/'prepared.json')['runtime_sha256']
 p=read(R/'budget-profile.json');assert p['task_limit_microcny']==16000000 and p['campaign_limit_microcny']==160000000
 with tempfile.TemporaryDirectory() as t:
  l=Ledger(Path(t)/'test.sqlite',p);assert l.status()['remaining_microcny']==160000000
  req=dict(id='x',job='old-unauthorized',arm='kz',endpoint=p['endpoint'],model=p['model'],max_tokens=1)
  try:l.reserve(req)
  except BudgetError as e:assert e.reason=='job_not_authorized'
  else:raise AssertionError('Old job admitted')
 # Concurrent-reservation and per-task budget protection regression tests.
 subprocess.run([str(R/'venv/bin/python'),'-m','unittest','test_bounded_ledger'],cwd=R,check=True)
 rows=read(R/'selection.json')['rows'];chosen=choose(rows,[],[]);assert len(chosen)==6 and sum(x['arm']=='hld' for x in chosen)==3
 files={p.name:sha(p) for p in R.iterdir() if p.is_file() and (p.suffix in ['.py','.mjs'] or p.name in ['tasks.json','protocol.json','experiment.json','budget-profile.json','runtime-final.tar.gz','python-runtime.tar.gz','selection.json','algorithm-source-lock.json'])}
 save=dict(passed=True,paid_calls=0,files=files,acceptance='All 10 production entries blocked before network; all original verifiers executed')
 (R/'ready.json').write_text(json.dumps(save,indent=2));(R/'validation.json').write_text(json.dumps(dict(passed=True,paid_calls=0,runs=10,concurrency=6,budget_cny=160,per_run_cny=16),indent=2))
 import campaign
 campaign.precheck();print('VALIDATED',flush=True)
if __name__=='__main__':main()
