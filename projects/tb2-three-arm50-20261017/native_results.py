import collections,json
from pathlib import Path
from receipts import read_receipt,lifecycle_status,valid_reward
ROOT=Path(__file__).resolve().parent
def read(p):
 try:return json.loads(Path(p).read_text())
 except (FileNotFoundError,ValueError):return {}
def trial(row,offline=False):
    job=('preflight-' if offline else '')+row['job']
    folder=ROOT/('preflight' if offline else 'jobs')/job
    paths=list(folder.glob('*/config.json')) or list(folder.glob('*/result.json'))
    if len(paths)!=1:return dict(engineering_clean=False,reason='missing_unique_trial')
    t=paths[0].parent
    res,result_status=read_receipt(t/'result.json');res=res or {}
    exception=res.get('exception_info')
    exc=exception.get('exception_type') if isinstance(exception,dict) else exception
    verifier=res.get('verifier_result')
    rewards=verifier.get('rewards') if isinstance(verifier,dict) else None
    reward=rewards.get('reward') if isinstance(rewards,dict) else None
    attempt_id=row.get('preflight_attempt_id' if offline else 'attempt_id')
    lifecycle,failures=lifecycle_status(t/'lifecycle.json',attempt_id)
    clean=result_status=='present' and not exception and valid_reward(reward) and lifecycle=='succeeded'
    out=dict(trial=str(t),reward=reward,exception_type=exc,engineering_clean=clean,
             result_status=result_status,lifecycle_status=lifecycle,collection_failures=failures)
    if offline:return out
    live=t/'agent/live'
    ex,exit_status=read_receipt(live/'agent-exit.json');ex=ex or {}
    code=ex.get('exit_code')
    exit_valid=(exit_status=='present' and type(code) is int and type(ex.get('timed_out')) is bool
                and (attempt_id is None or ex.get('attempt_id')==attempt_id))
    out.update(solver_exit=code,timed_out=ex.get('timed_out'),exit_receipt_status=exit_status)
    out['engineering_clean']=clean and exit_valid and code==0 and not ex.get('timed_out')
    usage,usage_status=read_receipt(live/'wire-state.json');usage=usage or {}
    progress=read(live/'progress.json');native=read(live/'run-status.json')
    out.update(requests=usage.get('requests'),tools=progress.get('tools'),usage=read(live/'usage.json'),usage_status=usage_status,
               http_status_counts=usage.get('http_status_counts',{}),native_status=native)
    wall=read(live/'server-timeout.json');stop=read(live/'budget-stop.json');reason=stop.get('reason')
    out['budget_stop']=stop;out['provider']=read(live/'provider-state.json')
    out['budget_exhausted']=reason in ('per_task_budget_exhausted','per_task_request_limit') or wall.get('reason')=='solver_wall_limit'
    if out['budget_exhausted'] and clean and exit_valid:
        out.update(engineering_clean=True,completion='budget_exhausted')
    if native.get('engineering_failure') and not out['budget_exhausted']:out['engineering_clean']=False
    if out['provider'].get('kind')=='accounting' or reason in ('usage_unavailable','usage_exceeds_model_ceiling','budget_service_unavailable'):out['engineering_clean']=False
    return out


def live_snapshot(row):
    paths=list((ROOT/'jobs'/row['job']).glob('*/agent/live'))
    if len(paths)!=1:return {}
    p=paths[0];state=read(p/'wire-state.json')
    return {k:state.get(k) for k in ('requests','tools','updated_utc','time','http_status_counts') if k in state}

