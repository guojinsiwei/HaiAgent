"""Two CPU workers; no GPT scheduler. Per-task startup failures are isolated."""
import concurrent.futures,fcntl,json,os,subprocess,time
from common import ROOT,deployment_hash
lock=(ROOT/'queue.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
ready=json.loads((ROOT/'preflight-multistep/passed.json').read_text())
assert ready['deployment_sha256']==deployment_hash()
assert len(ready['arms'])==2 and all(x['passed'] and x['cpu_only'] for x in ready['arms'])
assets=json.loads((ROOT/'assets-preflight.json').read_text());assert len(assets)==30 and all(x['ok'] for x in assets)
os.environ.update(HLD_PLANNER_PROTOCOL='2',CUDA_VISIBLE_DEVICES='',NVIDIA_VISIBLE_DEVICES='void')
os.environ['PATH']=str(ROOT/'.venv/bin')+':'+os.environ['PATH']
rows=json.loads((ROOT/'task-manifest.json').read_text())['tasks']
jobs=[(i,mode) for i in range(30) for mode in (['opencua_baseline','suz'] if i%2==0 else ['suz','opencua_baseline'])]
def run(job):
    index,mode=job;folder=ROOT/'runs'/mode/rows[index]['id']
    if (folder/'result.json').exists():return {'index':index,'mode':mode,'existing':True}
    if (ROOT/'STOP_DISPATCH').exists():return {'index':index,'mode':mode,'stopped_before_start':True}
    with (ROOT/'logs'/f'{mode}-{rows[index]["id"]}.log').open('a') as log:
        rc=subprocess.run([str(ROOT/'.venv/bin/python'),str(ROOT/'worker.py'),'--index',str(index),'--mode',mode],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT).returncode
    return {'index':index,'mode':mode,'returncode':rc}
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    futures=[pool.submit(run,j) for j in jobs]
    for f in concurrent.futures.as_completed(futures):print(json.dumps(f.result()),flush=True)
# One finite retry for startup failures that spent no inference. Never replay paid work.
for index,mode in jobs:
    p=ROOT/'runs'/mode/rows[index]['id']
    if (p/'worker-status.json').exists() and not (p/'cost-ledger.jsonl').exists() and not (p/'result.json').exists():
        print(json.dumps(run((index,mode))),flush=True)
(ROOT/'logs/queue.finished').write_text(str(time.time()))
