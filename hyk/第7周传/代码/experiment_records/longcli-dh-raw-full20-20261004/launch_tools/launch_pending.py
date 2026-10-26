"""Complete a partial launch; never replay claimed work or alter sealed code."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

CAMPAIGN=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(CAMPAIGN))
from common import ROOT,PYTHON,validate,save,assignments
from net_transport import request

def disposition(root,worker,rows):
    health=root/f'health-{worker}.json'
    if health.exists():
        value=json.loads(health.read_text())
        return dict(worker=worker,pending=False,state=value['state'],completed=value.get('completed',0))
    markers=[root/f'launched-{worker}.json',root/f'worker-{worker}.log']
    if any(p.exists() for p in markers) or any((root/'claims'/(r['job']+'.json')).exists() for r in rows):
        return dict(worker=worker,pending=False,state='launch_claim_exists_without_health',needs_attention=True)
    return dict(worker=worker,pending=True,state='never_launched')

def check_models(key,model,transport=request,pause=time.sleep):
    # GET only; bounded transient retry. Authentication/config errors fail once.
    for attempt in range(1,4):
        kind,body=transport('https://api.deepseek.com/models',None,key,30)
        print(json.dumps(dict(stage='model_preflight',attempt=attempt,kind=kind,
            http_status=body if kind=='http' and type(body) is int else None)),flush=True)
        if kind=='ok':
            models={r['id'] for r in json.loads(body)['data']}
            if model not in models:raise RuntimeError('Pinned model unavailable; no substitution')
            return
        transient=kind=='error' or kind=='http' and type(body) is int and (body==429 or body>=500)
        if not transient or attempt==3:
            raise RuntimeError('Model preflight failed; category='+kind+
                (' status='+str(body) if kind=='http' and type(body) is int else ''))
        pause(2)

def main(worker,status_only=False):
    import fcntl
    protocol=validate()
    rows=assignments(protocol,worker)
    state=disposition(ROOT,worker,rows)
    if status_only:
        print(json.dumps(state),flush=True);return
    if not state['pending']:raise RuntimeError('Worker is not unstarted: '+state['state'])
    with (ROOT/f'pending-launch-{worker}.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        assert disposition(ROOT,worker,rows)['pending'],'Worker concurrently claimed'
        key=sys.stdin.readline(512).strip()
        if not key or any(c.isspace() for c in key):raise RuntimeError('Invalid hidden credential input')
        check_models(key,protocol['model'])
        private=Path(tempfile.mkdtemp(prefix='dh-raw-pending-key-',dir='/dev/shm'))
        credential=private/'key'
        credential.write_text(key);credential.chmod(0o600);key=''
        process=None
        try:
            with (ROOT/f'worker-{worker}.log').open('x') as log:
                process=subprocess.Popen([PYTHON,'-B',str(ROOT/'parallel_worker.py'),
                    '--worker',str(worker),'--credential',str(credential)],cwd=ROOT,
                    stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            save(ROOT/f'launched-{worker}.json',dict(pid=process.pid,worker=worker,time=time.time(),
                controller='partial-launch-repair'))
            for _ in range(15):
                time.sleep(2)
                if process.poll() is not None:raise RuntimeError('Worker exited; inspect public worker log, do not replay')
                health=ROOT/f'health-{worker}.json'
                if health.exists():
                    state=json.loads(health.read_text())
                    if state['state']=='running':
                        print(json.dumps(dict(started=True,worker=worker,pid=process.pid,
                            trials=len(rows),concurrency=protocol['generation_concurrency_per_worker'])),flush=True)
                        return
            raise RuntimeError('Launch admitted but heartbeat is not confirmed; inspect status before retry')
        except Exception:
            # Never remove a credential that a live worker still owns.
            if process is None or process.poll() is not None:
                credential.unlink(missing_ok=True)
                if private.exists():private.rmdir()
            raise

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--worker',type=int,choices=(0,1),required=True)
    p.add_argument('--status-only',action='store_true');a=p.parse_args()
    try:main(a.worker,a.status_only)
    except Exception as error:
        # Do not print raw provider bodies, keys, or exception locals.
        print(json.dumps(dict(stage='pending_launch_failed',worker=a.worker,
            error_type=type(error).__name__,message=str(error) if isinstance(error,(RuntimeError,AssertionError))
            else 'Controller failed; inspect public launch/worker markers')),flush=True)
        raise SystemExit(1)
