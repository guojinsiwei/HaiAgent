"""Bounded CPU workers, no LLM scheduler. Original results are immutable inputs."""
import concurrent.futures,fcntl,hashlib,importlib.util,json,os,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('common',ROOT/'repair-common.py');common=importlib.util.module_from_spec(spec);spec.loader.exec_module(common)
lock=(ROOT/'repair1-queue.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
ready=json.loads((ROOT/'preflight-multistep-repair1/passed.json').read_text())
assert ready['source_sha256']==common.source_hash()
assert len(ready['arms'])==2 and all(x['passed'] and x['cpu_only'] for x in ready['arms'])
assert all(x['source_sha256']==ready['source_sha256'] for x in ready['arms'])
os.environ['PATH']=str(ROOT/'.venv/bin')+':'+os.environ['PATH']
os.environ['HLD_PLANNER_PROTOCOL']='2';os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['NVIDIA_VISIBLE_DEVICES']='void'
manifest=json.loads((ROOT/'repair1-manifest.json').read_text())
for row in manifest['runs']:
    assert hashlib.sha256((ROOT/row['original_result']).read_bytes()).hexdigest()==row['original_sha256']
def run(index):
    row=manifest['runs'][index]
    with (ROOT/'logs'/('repair1-'+row['mode']+'-'+row['id']+'.log')).open('a') as log:
        proc=subprocess.Popen([str(ROOT/'.venv/bin/python'),str(ROOT/'repair-worker.py'),'--index',str(index)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        return {'index':index,'returncode':proc.wait()}
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    for row in pool.map(run,range(len(manifest['runs']))):print(json.dumps(row),flush=True)
(ROOT/'logs/repair1.finished').write_text(str(time.time()))
