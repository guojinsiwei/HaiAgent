"""Authorized full rerun; change monetary caps only, retain voided history."""
from pathlib import Path
import json,shutil,subprocess,time,sys
R=Path(__file__).resolve().parent
OLD=Path('/mnt/sdb/home/lizh639/longcli-hld-full20-20261022')

def main():
 assert json.loads((OLD/'voided.json').read_text())['voided']
 assert not (R/'launch-once.marker').exists()
 for name in ['common.py','college_grader.py','input-manifest.json','spending.py','container-run.mjs','runner.py']:
  shutil.copy2(OLD/name,R/name)
 for name in ['upstream']:
  if not (R/name).exists():(R/name).symlink_to(OLD/name,target_is_directory=True)
 (R/'runtime').mkdir(exist_ok=True)
 if not (R/'runtime/node').exists():(R/'runtime/node').symlink_to(OLD/'runtime/node',target_is_directory=True)
 if not (R/'runtime/kz').exists():subprocess.run(['cp','-a','--reflink=auto',str(OLD/'runtime/kz'),str(R/'runtime/kz')],check=True)
 from common import sha,save
 p=R/'runtime/kz/.runtime/kz.patch.yml';text=p.read_text();assert text.count('limitCny: 8')==1;p.write_text(text.replace('limitCny: 8','limitCny: 24'))
 p=R/'runtime/kz/shared-budget.mjs';text=p.read_text();assert text.count('estimatePeakCny:8')==1;p.write_text(text.replace('estimatePeakCny:8','estimatePeakCny:24'))
 runner=R/'runner.py';text=runner.read_text().replace('8 CNY/task 160 total','24 CNY/task 480 total').replace('budget_cny=160','budget_cny=480')
 # Status-only correction; preserve algorithm behavior and official scores.
 text=text.replace("if summary['provider_stop']:summary['engineering_fault']='provider_stop'", "if summary['provider_stop'] and summary['provider_stop'].get('kind')!='budget':summary['engineering_fault']='provider_stop'")
 text=text.replace("summary['engineering_fault']='native_error_inspect_logs'", "\n    stderr=(directory/'logs/live/dsh.stderr.log').read_text(errors='replace')\n    if 'KZ per-task monetary ceiling' in stderr:summary['stop_reason']='per_task_budget_exhausted'\n    else:summary['engineering_fault']='native_error_inspect_logs'")
 runner.write_text(text);compile(text,str(runner),'exec')
 protocol=json.loads((OLD/'protocol.json').read_text());protocol.update(experiment=R.name,task_budget_cny=24,campaign_budget_cny=480,replaces_voided_experiment=OLD.name,budget_multiplier=3)
 save(R/'protocol.json',protocol)
 profile=json.loads((OLD/'budget-profile.json').read_text());profile.update(task_limit_microcny=24000000,campaign_limit_microcny=480000000);save(R/'budget-profile.json',profile)
 (R/'empty-tests').mkdir(exist_ok=True)
 oldmanifest=json.loads((OLD/'input-manifest.json').read_text())
 for name,digest in oldmanifest['files'].items():assert sha(R/name)==digest,name
 evidence=[]
 for row in protocol['tasks']:
  assert sha(row['starter_path'])==row['starter_sha256']
  assert subprocess.check_output(['docker','image','inspect',row['image'],'--format','{{.Id}}'],text=True).strip()==row['image_id']
  fixture=OLD/'fixture-grades'/('roundtrip--'+row['task'])/'result.json';result=json.loads(fixture.read_text());assert result['grading_state']=='complete'
  evidence.append(dict(task=row['task'],path=str(fixture),sha256=sha(fixture),grading_state='complete'))
 assert sha(R/'college_grader.py')==sha(OLD/'college_grader.py')
 changes=[];files={}
 for f in (R/'runtime/kz').rglob('*'):
  if not f.is_file():continue
  rel=f.relative_to(R);digest=sha(f);files[rel.as_posix()]=digest
  if digest!=sha(OLD/rel):changes.append(rel.as_posix())
 assert sorted(changes)==['runtime/kz/.runtime/kz.patch.yml','runtime/kz/shared-budget.mjs'],changes
 save(R/'algorithm-source-lock.json',dict(version='HLD v8',source=str(OLD/'runtime/kz'),changed_files=changes,changes='Only monetary ceiling 8 -> 24 and telemetry label; algorithm identical',files=files))
 from spending import Ledger,BudgetError
 q=dict(profile,jobs=['test'],campaign_limit_microcny=480000000)
 test=Ledger(R/'budget-test.sqlite',q)
 request=dict(id='next',job='test',arm='kz',endpoint=q['endpoint'],model=q['model'],max_tokens=16384)
 with test.db() as db:db.execute('insert into calls values (?,?,?,?,?,?,?)',('prior','test','kz',9000000,9000000,'settled',time.time()))
 test.reserve(request);test.settle(dict(id='next',tokens=100000))
 with test.db() as db:db.execute('update calls set actual=23900000 where id=?',('prior',))
 try:test.reserve(dict(request,id='over'));raise AssertionError('24 CNY gate failed')
 except BudgetError as e:assert e.reason=='per_task_budget_exhausted'
 with test.db() as db:db.execute('update calls set job=?,actual=? where id=?',('previous-other-jobs',479900000,'prior'))
 try:test.reserve(dict(request,id='campaign'));raise AssertionError('480 CNY gate failed')
 except BudgetError as e:assert e.reason=='campaign_budget_exhausted'
 from runner import solve
 probe=Ledger(R/'entry-probe.sqlite',dict(profile,task_limit_microcny=1,campaign_limit_microcny=1));probes=[]
 for family in ['make-pytest','c-env']:
  row=next(r for r in protocol['tasks'] if r['family']==family)
  result=solve(row,'offline-dummy-never-transmitted',probe,probe=True);probes.append(result);print('ENTRY',family,result['state'],flush=True)
 assert all(p['state']=='passed' for p in probes),probes
 save(R/'validation.json',dict(passed=True,grading_evidence=evidence,grading_preflight_reused_reason='Identical task images, starters, grader and official files verified; only monetary caps changed',entry_probes=probes,budget_24_480_passed=True,paid_calls=0))
 names=['runner.py','spending.py','container-run.mjs','common.py','college_grader.py','protocol.json','budget-profile.json','input-manifest.json','algorithm-source-lock.json']
 hashes={n:sha(R/n) for n in names};hashes.update(files)
 save(R/'ready.json',dict(passed=True,hashes=hashes,paid_calls=0,created=time.time()))
 print('VALIDATION COMPLETE',flush=True)
 subprocess.run([sys.executable,str(R/'runner.py'),'--launch'],check=True)

if __name__=='__main__':main()
