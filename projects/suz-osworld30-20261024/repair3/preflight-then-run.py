"""One finite CPU preflight and repair batch, no agent/LLM polling automation."""
from pathlib import Path
import concurrent.futures,json,os,subprocess,time
from common import deployment_hash
ROOT=Path(__file__).resolve().parent
env=dict(os.environ,CUDA_VISIBLE_DEVICES='',NVIDIA_VISIBLE_DEVICES='void',HLD_PLANNER_PROTOCOL='2')
env['PATH']=str(ROOT/'.venv/bin')+':'+env['PATH']
def preflight(mode):
    with (ROOT/'logs'/('preflight-'+mode+'.log')).open('a') as log:
        return subprocess.run([str(ROOT/'.venv/bin/python'),'-u',str(ROOT/'preflight-multistep.py'),'--mode',mode],
            cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT).returncode
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    results=list(pool.map(preflight,['opencua_baseline','suz']))
if any(results):raise SystemExit('preflight failed; paid repair queue not started: '+str(results))
ready=json.loads((ROOT/'preflight-multistep/passed.json').read_text())
assert ready['deployment_sha256']==deployment_hash()
assert all(r['passed'] and r['cpu_only'] for r in ready['arms'])
if (ROOT/'STOP_DISPATCH').exists():raise SystemExit('dispatch paused')
(ROOT/'logs/preflight-accepted.json').write_text(json.dumps({'time':time.time(),'deployment_sha256':deployment_hash()}))
with (ROOT/'logs/queue.log').open('a') as log:
    code=subprocess.run([str(ROOT/'.venv/bin/python'),'-u',str(ROOT/'launch.py')],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT).returncode
raise SystemExit(code)
