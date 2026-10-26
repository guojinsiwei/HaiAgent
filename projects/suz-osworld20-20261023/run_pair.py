"""One frozen task, both arms, separate fresh desktops and memories."""
import argparse
import fcntl
import hashlib
import json
import os
import sys
import time
from environment import ROOT,make_environment
from cache_assets import prefetch
sys.path.insert(0,str(ROOT/'SUZ'))
from python.suz_agent import SUZAgent
from python.run_osworld import run_task

parser=argparse.ArgumentParser();parser.add_argument('--index',type=int,required=True)
index=parser.parse_args().index
row=json.loads((ROOT/'task-manifest.json').read_text())['tasks'][index]
task_path=ROOT/row['path']
assert hashlib.sha256(task_path.read_bytes()).hexdigest()==row['sha256']
task=json.loads(task_path.read_text())
pair_dir=ROOT/'pairs'/row['id'];pair_dir.mkdir(parents=True,exist_ok=True)
lock=(pair_dir/'worker.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
result_path=pair_dir/'status.json'
state={'id':row['id'],'domain':row['domain'],'stage':'preflight','arms':{},'started':time.time()}
def save():
    tmp=result_path.with_suffix('.tmp');tmp.write_text(json.dumps(state,indent=2));tmp.replace(result_path)
save()
os.environ['SUZ_API_KEY']=(ROOT/'secrets/api-key').read_text().strip()
base=json.loads((ROOT/'model-config.json').read_text())
env=None
try:
    prefetch(task)
    env=make_environment();initial=env.reset(task_config=task)
    (pair_dir/'preflight-initial.png').write_bytes(initial['screenshot'])
    score=env.evaluate()
    if not isinstance(score,(float,int)) or not 0<=score<=1:raise RuntimeError('Invalid preflight score')
    state['preflight_score']=score
    env.close();env=None
    state['stage']='running';save()
    order=['opencua_baseline','suz'] if index%2==0 else ['suz','opencua_baseline']
    for mode in order:
        directory=ROOT/'runs'/mode/row['id']
        if directory.exists() and any(directory.iterdir()):
            prior=directory/'result.json'
            if prior.exists():
                state['arms'][mode]=json.loads(prior.read_text());save();continue
            raise RuntimeError('Existing incomplete run requires explicit recovery; no automatic paid restart')
        directory.mkdir(parents=True,exist_ok=True)
        cfg={**base,'task_id':row['id'],'mode':mode,'budget_cny':8,
             'shared_budget':{'path':str(ROOT/'budget.sqlite'),'bucket':mode+'/'+row['id'],
                              'total_limit_cny':320,'bucket_limit_cny':8}}
        (directory/'run-config.json').write_text(json.dumps(cfg,indent=2))
        (directory/'task-sha256.txt').write_text(row['sha256'])
        env=make_environment()
        agent=SUZAgent(cfg,directory,node=str(ROOT/'.venv/bin/node'))
        outcome=run_task(agent,env,task,directory)
        state['arms'][mode]=outcome;save()
        if outcome.get('error') and outcome.get('model_requests',0)>0:
            state['stage']='recovery_required'
            state['preserved_container']=env.provider.container.id
            (pair_dir/'recovery-required.json').write_text(json.dumps({
                'task_id':row['id'],'mode':mode,'container':env.provider.container.id,
                'run_directory':str(directory),'reason':outcome['error']},indent=2))
            env=None  # Preserve solved state for grading recovery; never destroy it here.
            raise RuntimeError('Paid run hit infrastructure error; VM retained for recovery')
        env.close();env=None
    state['stage']='completed'
except Exception as exc:
    if state['stage']!='recovery_required':state['stage']='engineering_failure'
    state['error']=type(exc).__name__+': '+str(exc)[:500]
finally:
    if env is not None:env.close()
    state['updated']=time.time();save()
print(json.dumps(state),flush=True)
