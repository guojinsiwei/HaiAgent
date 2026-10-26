"""Fixed CPU experiment queue, no GPT scheduler/automation. Two desktops maximum."""
import concurrent.futures
import fcntl
import json
import os
from pathlib import Path
import subprocess
import time
ROOT=Path(__file__).resolve().parent
lock=(ROOT/'queue.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
for marker in ['bootstrap.ready','vm.ready','docker-image.ready','gui.ready','protocol.ready']:
    if not (ROOT/'logs'/marker).exists():raise RuntimeError('Missing preflight: '+marker)
rows=json.loads((ROOT/'task-manifest.json').read_text())['tasks']
assert len(rows)==20
os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['NVIDIA_VISIBLE_DEVICES']='void'
os.environ['PYTHONPATH']=str(ROOT/'OSWorld')+':'+str(ROOT/'SUZ')
def run(index):
    row=rows[index]
    prior=ROOT/'pairs'/row['id']/'status.json'
    if prior.exists():return {'id':row['id'],'status':'already_attempted'}
    with (ROOT/'logs'/('pair-'+row['id']+'.log')).open('a') as log:
        process=subprocess.Popen([str(ROOT/'.venv/bin/python'),str(ROOT/'run_pair.py'),'--index',str(index)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        return {'id':row['id'],'returncode':process.wait()}
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    for result in pool.map(run,range(len(rows))):print(json.dumps(result),flush=True)
(ROOT/'logs/queue.finished').write_text(str(time.time()))
