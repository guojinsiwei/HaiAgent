"""Read-only reconciliation of provider-available misclassification from saved evidence."""
import copy,hashlib,json,time
from pathlib import Path
def read(p):
 try:return json.loads(Path(p).read_text())
 except (FileNotFoundError,ValueError):return {}
def normalized(root,health):
 h=copy.deepcopy(health);corrections=[]
 # An explicitly admitted repair can run alongside the original supervisor.
 # Its own receipt owns this job until fresh official grading reconciles it.
 repair=read(Path(root)/'literal-retry-health.json')
 for job,retry in repair.get('rows',{}).items():
  old=h.get('rows',{}).get(job,{})
  if (job=='swp-08-recuris' and repair.get('original_ledger') is True
      and retry.get('repair')=='literal_memory_context'
      and old.get('state')=='engineering_failed' and retry.get('started',0)>old.get('started',0)
      and old.get('task')==retry.get('task') and old.get('arm')==retry.get('arm')):
   h['rows'][job]=copy.deepcopy(retry)
 for job,row in h.get('rows',{}).items():
  if row.get('state')!='engineering_failed':continue
  folder=Path(root)/'jobs'/job;grade=read(folder/'grade/result.json');solver=read(folder/'solver.json');ex=read(folder/'live/agent-exit.json');provider=read(folder/'live/provider-state.json')
  patch=folder/'model.patch'
  stop=read(folder/'live/limit-stop.json') or read(folder/'live/budget-stop.json');wall=read(folder/'live/wall-limit.json')
  bounded=stop.get('reason') in ('per_task_request_limit','per_task_tool_limit','per_task_budget_exhausted')
  if not bounded and solver.get('exit_code')==1:
   from budget_classification import hld_monetary_stop
   bounded=hld_monetary_stop(folder/'live',row.get('arm'),bool(ex),1)
  bounded=bounded or (ex.get('timed_out') is True and ex.get('stopped_by')=='solver_wall_limit' and wall.get('limit_seconds')==3000 and wall.get('attempt_id')==ex.get('attempt_id'))
  recovered=solver.get('recovered_from_stopped_container') is True and solver.get('new_model_calls')==0
  normal=solver.get('exit_code')==0 and ex.get('exit_code')==0 and ex.get('timed_out') is False
  if not (grade.get('engineering_clean') and grade.get('reward') in (0,1) and (normal or bounded or recovered) and ex.get('arm')==row.get('arm') and isinstance(ex.get('attempt_id'),str) and len(ex['attempt_id'])==32 and provider.get('kind') in ('available','budget')):continue
  if not patch.is_file() or hashlib.sha256(patch.read_bytes()).hexdigest()!=solver.get('patch_sha256'):continue
  row.update(state='completed',engineering_clean=True,reward=grade['reward'],classification_corrected='Verified saved patch and official score after normal/bounded stop or artifact recovery')
  if recovered:row.update(artifact_recovered=True,historical_solver_fault='oom',recovery_model_calls=0)
  corrections.append(job)
 h['summary']={a:dict(completed=sum(r['arm']==a and r['state']=='completed' for r in h['rows'].values()),passed=sum(r['arm']==a and r['state']=='completed' and r.get('reward')==1 for r in h['rows'].values()),engineering_failed=sum(r['arm']==a and r['state']=='engineering_failed' for r in h['rows'].values())) for a in ('hld','recuris')}
 h['classification_corrections']=corrections;h['status_checked']=time.time();return h
if __name__=='__main__':
 r=Path(__file__).resolve().parent;print(json.dumps(normalized(r,read(r/'health.json')),indent=2))
