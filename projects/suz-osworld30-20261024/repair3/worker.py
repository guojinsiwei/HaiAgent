"""Fresh single arm/task attempt; preserve paid work on scoring failure."""
import argparse,fcntl,hashlib,json,os,signal,sys,time
from environment import ROOT,make_environment
from grading_cache import prepare_cache, archive_cache
from common import SOURCE,config,deployment_hash,verify_ready
sys.path.insert(0,str(SOURCE))
from python.suz_agent import SUZAgent
from python.run_osworld import run_task
args=argparse.ArgumentParser();args.add_argument('--index',type=int,required=True);args.add_argument('--mode',required=True,choices=['opencua_baseline','suz']);a=args.parse_args()
row=json.loads((ROOT/'task-manifest.json').read_text())['tasks'][a.index]
directory=ROOT/'runs'/a.mode/row['id'];directory.mkdir(parents=True,exist_ok=True)
lock=(directory/'worker.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
if (directory/'result.json').exists():raise SystemExit('existing result retained')
if (directory/'cost-ledger.jsonl').exists():raise SystemExit('paid incomplete attempt requires explicit recovery')
ready=verify_ready()
taskpath=ROOT/row['path'];assert hashlib.sha256(taskpath.read_bytes()).hexdigest()==row['sha256']
task=json.loads(taskpath.read_text());env=None;agent=None
status={'id':row['id'],'mode':a.mode,'stage':'preflight','started':time.time()}
p=directory/'worker-status.json'
if p.exists():(directory/('prior-startup-'+str(time.time_ns())+'.json')).write_bytes(p.read_bytes())
def save():
    tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(status,indent=2));tmp.replace(p)
save()
try:
    attempt=directory/('attempt-'+str(time.time_ns()));attempt.mkdir()
    status['attempt_directory']=str(attempt);save()
    initial_cache=prepare_cache(ROOT/'assets',attempt/'preflight-cache',task['id']);env=make_environment(initial_cache);obs=env.reset(task_config=task)
    assert obs['screenshot'];score=env.evaluate();assert isinstance(score,(float,int)) and 0<=score<=1
    (directory/'preflight.json').write_text(json.dumps({'passed':True,'initial_score':score}))
    env.close();env=None
    cfg=config(row['id'],a.mode);(directory/'run-config.json').write_text(json.dumps(cfg,indent=2))
    os.environ['SUZ_API_KEY']=(ROOT/'secrets/api-key').read_text().strip()
    eval_cache=prepare_cache(ROOT/'assets',attempt/'evaluation-cache',task['id']);env=make_environment(eval_cache);agent=SUZAgent(cfg,directory,node=str(ROOT/'.venv/bin/node'))
    status['stage']='running';save()
    outcome=run_task(agent,env,task,directory);status.update(stage='completed',outcome=outcome);archive_cache(eval_cache,directory/'grading-artifacts.json')
    if outcome.get('error') and outcome['model_requests']:
        status.update(stage='recovery_required',container=env.provider.container.id)
        (directory/'recovery-required.json').write_text(json.dumps(status,indent=2));env=None
except Exception as exc:
    status.update(stage='engineering_failure',error=type(exc).__name__+': '+str(exc)[:500])
finally:
    if agent:agent.close()
    if env:env.close()
    status['updated']=time.time();save()
print(json.dumps(status),flush=True)
