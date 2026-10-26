"""One finite post-queue recovery for zero-call startup failures; no GPT automation."""
import fcntl,json,os,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
while not (ROOT/'logs/repair1.finished').exists():time.sleep(30)
lock=(ROOT/'repair1-queue.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX)
rows=json.loads((ROOT/'repair1-manifest.json').read_text())['runs']
os.environ['PATH']=str(ROOT/'.venv/bin')+':'+os.environ['PATH'];os.environ['HLD_PLANNER_PROTOCOL']='2'
for index,row in enumerate(rows):
    p=ROOT/'repair1-runs'/row['mode']/row['id']
    status=json.loads((p/'worker-status.json').read_text()) if (p/'worker-status.json').exists() else {}
    if status.get('stage')!='engineering_failure' or (p/'result.json').exists() or (p/'cost-ledger.jsonl').exists():continue
    with (ROOT/'logs'/('repair1-'+row['mode']+'-'+row['id']+'.log')).open('a') as log:
        result=subprocess.run([str(ROOT/'.venv/bin/python'),str(ROOT/'repair-worker.py'),'--index',str(index)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
    print(json.dumps({'index':index,'returncode':result.returncode}),flush=True)
(ROOT/'logs/repair1-unpaid-recovery.finished').write_text(str(time.time()))
