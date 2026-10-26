"""Official empty-starter grading and zero-paid-call production entry probes."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import json,sqlite3,time
from common import ROOT,sha,save
from spending import Ledger,BudgetError
from runner import read,solve
from college_grader import grade,official_parser

def fixture(row):
 job='roundtrip--'+row['task'];path=ROOT/'fixture-grades'/job/'result.json'
 if path.exists():return read(path)
 return grade(job,row['starter_path'],row['starter_sha256'],fixture=True)

def main():
 assert read(ROOT/'prepared.json')['prepared']
 protocol=read(ROOT/'protocol.json');profile=read(ROOT/'budget-profile.json')
 official_parser()
 # Independently exercise per-task and total reservations with actual ledger code.
 sample=dict(profile,jobs=['a','b'],task_limit_microcny=387072,campaign_limit_microcny=387072)
 test=Ledger(ROOT/('budget-test-'+str(time.time_ns())+'.sqlite'),sample)
 def req(i,j):return dict(id=i,job=j,arm='kz',endpoint=sample['endpoint'],model=sample['model'],max_tokens=16384)
 test.reserve(req('a1','a'))
 for i,j,reason in [('a2','a','per_task_budget_exhausted'),('b1','b','waiting_for_inflight_usage')]:
  try:test.reserve(req(i,j));raise AssertionError('Budget gate failed')
  except BudgetError as e:assert e.reason==reason,(e.reason,reason)
 test.settle(dict(id='a1',tokens=387072))
 try:test.reserve(req('b2','b'));raise AssertionError('Campaign gate failed')
 except BudgetError as e:assert e.reason=='campaign_budget_exhausted'
 probeprofile=dict(profile,campaign_limit_microcny=1,task_limit_microcny=1)
 ledger=Ledger(ROOT/'entry-probe.sqlite',probeprofile)
 probes=[]
 for family in ['make-pytest','c-env']:
  row=next(r for r in protocol['tasks'] if r['family']==family)
  existing=ROOT/'entry-probes'/('hld--'+row['task'])/'summary.json'
  result=read(existing) if existing.exists() else solve(row,'offline-dummy-never-transmitted',ledger,probe=True)
  probes.append(result);print('ENTRY',family,result['state'],flush=True)
 assert all(r['state']=='passed' for r in probes),'Production entry preflight failed'
 results=[]
 with ThreadPoolExecutor(max_workers=6) as pool:
  futures={pool.submit(fixture,row):row for row in protocol['tasks']}
  for future in as_completed(futures):
   row=futures[future]
   try:result=future.result()
   except Exception as e:result=dict(task=row['task'],grading_state='failed',error=str(e)[:700])
   results.append(result);save(ROOT/'preflight-progress.json',dict(completed=len(results),total=20,results=results,updated=time.time()))
   print('GRADE',row['task'],result['grading_state'],result.get('error',''),flush=True)
 passed=all(r['grading_state']=='complete' for r in results) and len(results)==20
 save(ROOT/'validation.json',dict(passed=passed,entry_probes=probes,official_grading=results,paid_calls=0,budget_gates_passed=True))
 assert passed,'Official grading preflight incomplete'
 names=['runner.py','preflight.py','spending.py','container-run.mjs','common.py','college_grader.py','protocol.json','budget-profile.json','input-manifest.json','algorithm-source-lock.json']
 hashes={n:sha(ROOT/n) for n in names}
 hashes.update(read(ROOT/'algorithm-source-lock.json')['files'])
 save(ROOT/'ready.json',dict(passed=True,hashes=hashes,paid_calls=0,created=time.time()))
 print('ALL PREFLIGHTS PASSED',flush=True)

if __name__=='__main__':main()
