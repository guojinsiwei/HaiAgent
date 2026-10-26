"""One selected engineering failure, isolated fresh desktop, cumulative original budget."""
import argparse,fcntl,importlib.util,json,os,sys,time,hashlib
from environment import ROOT,make_environment
from cache_assets import prefetch
spec=importlib.util.spec_from_file_location('common',ROOT/'repair-common.py');common=importlib.util.module_from_spec(spec);spec.loader.exec_module(common)
sys.path.insert(0,str(common.SOURCE))
from python.suz_agent import SUZAgent
from python.run_osworld import run_task
parser=argparse.ArgumentParser();parser.add_argument('--index',type=int,required=True);index=parser.parse_args().index
row=json.loads((ROOT/'repair1-manifest.json').read_text())['runs'][index]
directory=ROOT/'repair1-runs'/row['mode']/row['id']
directory.mkdir(parents=True,exist_ok=True)
lock=(directory/'worker.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
if (directory/'result.json').exists():raise SystemExit('already completed')
if (directory/'cost-ledger.jsonl').exists():raise SystemExit('paid incomplete run requires explicit recovery')
prior_status=directory/'worker-status.json'
if prior_status.exists():
    (directory/('startup-status-'+str(time.time_ns())+'.json')).write_bytes(prior_status.read_bytes())
ready=json.loads((ROOT/'preflight-multistep-repair1/passed.json').read_text())
assert ready['source_sha256']==common.source_hash(),'source changed since multi-step preflight'
taskpath=ROOT/row['path'];assert hashlib.sha256(taskpath.read_bytes()).hexdigest()==row['sha256']
task=json.loads(taskpath.read_text());env=None;agent=None
state={'stage':'preflight','id':row['id'],'mode':row['mode'],'started':time.time(),'original_result':row['original_result']}
def save():
    p=directory/'worker-status.json';tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(state,indent=2));tmp.replace(p)
save()
try:
    prefetch(task);env=make_environment();initial=env.reset(task_config=task)
    assert initial['screenshot'];score=env.evaluate();assert isinstance(score,(float,int)) and 0<=score<=1
    (directory/'preflight.json').write_text(json.dumps({'initial_score':score,'passed':True}))
    env.close();env=None
    cfg=common.config(row['id'],row['mode']);(directory/'run-config.json').write_text(json.dumps(cfg,indent=2))
    os.environ['SUZ_API_KEY']=(ROOT/'secrets/api-key').read_text().strip()
    env=make_environment()
    agent=SUZAgent(cfg,directory,node=str(ROOT/'.venv/bin/node'));state['stage']='running';save()
    outcome=run_task(agent,env,task,directory);state.update(stage='completed',outcome=outcome)
    if outcome.get('error') and outcome['model_requests']>0:
        state.update(stage='recovery_required',container=env.provider.container.id)
        (directory/'recovery-required.json').write_text(json.dumps(state,indent=2));env=None
except Exception as exc:
    state.update(stage='engineering_failure',error=type(exc).__name__+': '+str(exc)[:400])
finally:
    if agent:agent.close()
    if env:env.close()
    state['updated']=time.time();save()
print(json.dumps(state),flush=True)
