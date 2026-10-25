"""Copy code into fresh owned directories; preserve old results by reference."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import time

ROOT=Path(__file__).resolve().parent
BASE=Path('/mnt/sdb/home/lizh639')
SOURCES={
 'retrac':('longcli-retrac-recovery4-20261007',4),
 'dh':('longcli-dh-large20-20261007',4),
 'recuris_frozen':('longcli-recuris-frozen-small20-20261007',2),
 'taco':('longcli-lats-taco-small20-20261007',1),
 'lats':('longcli-lats-taco-small20-20261007',1)}


def read(p):return json.loads(p.read_text())
def save(p,obj):p.write_text(json.dumps(obj,indent=2,ensure_ascii=False))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def alive(pid):
 p=Path('/proc')/str(pid)/'stat'
 return p.exists() and p.read_text().rsplit(')',1)[1].split()[0]!='Z'


def main():
 assert ROOT==BASE/'longcli-resume-five-20261007'
 plans=[]
 for method,(name,concurrency) in SOURCES.items():
  old=BASE/name
  h=read(old/'health.json')
  assert not alive(h['pid']),f'Original controller still alive: {method}'
  for p in (old/'jobs').glob('*/health.json'):
   j=read(p)
   assert not alive(j.get('pid',0)),f'Original job still alive: {p.parent.name}'
  dest=ROOT/(method+'-resume-20261007')
  if dest.exists():
   plans.append(read(dest/'resume-plan.json'));continue
  preserved={}
  if method=='retrac':
   for r in read(old/'recovery-plan.json')['reused_scored']:
    report=Path(r['report']);record=read(report)
    assert record['grading_state']=='complete'
    preserved[r['task']]={'task':r['task'],'report':str(report),'report_sha256':sha(report)}
  for report in (old/'grades').glob(method+'--*/result.json'):
   r=read(report)
   if r.get('grading_state')=='complete':
    task=r.get('task') or report.parent.name.split('--',1)[1]
    preserved[task]={'task':task,'report':str(report),'report_sha256':sha(report)}
  protocol=read(old/'protocol.json')
  remaining=[r for r in protocol['tasks'] if r['task'] not in preserved]
  assert len(remaining)+len(preserved)==20
  # Guard against accidentally rerunning an ungraded completed artifact.
  for row in remaining:
   f=old/'jobs'/(method+'--'+row['task'])/'summary.json'
   if f.exists():
    summary=read(f)
    assert not (summary.get('state')=='awaiting_grade' and not summary.get('engineering_fault')
                and not summary.get('error')),f'Completed artifact needs grade-only handling: {f}'
  dest.mkdir()
  for f in old.glob('*.py'):shutil.copyfile(f,dest/f.name)
  for name2 in ('upstream','input-manifest.json','sources','compatibility','retrac','recuris','taco_native'):
   f=old/name2
   if f.exists():(dest/name2).symlink_to(f.resolve(),target_is_directory=f.is_dir())
  for name2 in ('terminal_seed.json','taco-pool.json'):
   if (old/name2).exists():shutil.copyfile(old/name2,dest/name2)
  for name2 in ('jobs','grades','incoming','host-tmp','empty-tests','acceptance-jobs'):(dest/name2).mkdir()
  for name2 in ('repair_runtime.py','resume_worker.py','resume_grader.py','test_resume.py','accept_resume.py'):
   shutil.copyfile(ROOT/name2,dest/name2)
  protocol.update(experiment=dest.name,methods=[method],total_trials=len(remaining),
      tasks=remaining,run_tasks=remaining,concurrency=concurrency)
  protocol['recovery_transport']={'model_feedback':'none','completed_results_preserved':len(preserved),
    'length_repairs':'up to 3 attempts, all original budget charged',
    'retrac_action_json_mode':True,'dh_token_meter':'1.5x initial heuristic, increased from observed provider usage',
    'task_fault_policy':'record per task and continue other tasks','automatic_task_retry':False}
  save(dest/'protocol.json',protocol)
  plan={'method':method,'root':str(dest),'source':str(old),'concurrency':concurrency,
    'preserved':list(preserved.values()),'run_tasks':remaining,'time':time.time()}
  save(dest/'resume-plan.json',plan)
  plans.append(plan)
 save(ROOT/'resume-manifest.json',{'arms':plans,'preserved':sum(len(p['preserved']) for p in plans),
     'rerun':sum(len(p['run_tasks']) for p in plans),'time':time.time()})
 print(json.dumps({p['method']:{'preserved':len(p['preserved']),'rerun':len(p['run_tasks'])} for p in plans}))

if __name__=='__main__':main()
