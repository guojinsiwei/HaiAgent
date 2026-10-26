"""Credential via stdin to private tmpfs only. No paid call at preflight."""
import argparse
import fcntl
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from common import ROOT,PYTHON,validate,save
from net_transport import request

def main(worker,check_only):
    protocol=validate()
    if (ROOT/('health-'+str(worker)+'.json')).exists(): raise RuntimeError('Worker already claimed; inspect status, do not relaunch')
    key=sys.stdin.readline(512).strip()
    if not key or any(c.isspace() for c in key): raise RuntimeError('Invalid credential input')
    kind,body=request('https://api.deepseek.com/models',None,key,30)
    if kind!='ok': raise RuntimeError('Credential/network preflight failed ('+str(kind)+'); no trial started')
    models={r['id'] for r in json.loads(body)['data']}
    if protocol['model'] not in models: raise RuntimeError('Pinned model unavailable; no substitution')
    if check_only:
        print(json.dumps(dict(worker=worker,ready=True,model=protocol['model'],generation_calls=0)),flush=True); return
    with (ROOT/('launch-'+str(worker)+'.lock')).open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (ROOT/('health-'+str(worker)+'.json')).exists(): raise RuntimeError('Already launched')
        private=Path(tempfile.mkdtemp(prefix='paired10-key-',dir='/dev/shm'))
        credential=private/'key'; credential.write_text(key); credential.chmod(0o600)
        key=''
        try:
            with (ROOT/('worker-'+str(worker)+'.log')).open('x') as log:
                process=subprocess.Popen([PYTHON,'-B',str(ROOT/'worker.py'),'--worker',str(worker),
                    '--credential',str(credential)],cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,
                    stderr=subprocess.STDOUT,start_new_session=True)
            save(ROOT/('launched-'+str(worker)+'.json'),dict(pid=process.pid,worker=worker,time=time.time()))
            time.sleep(3)
            if process.poll() is not None: raise RuntimeError('Worker exited at launch; inspect redacted worker log')
            print(json.dumps(dict(started=True,pid=process.pid,worker=worker,trials=15)),flush=True)
        except Exception:
            credential.unlink(missing_ok=True)
            if private.exists(): private.rmdir()
            raise

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--worker',type=int,choices=(0,1),required=True)
    p.add_argument('--check-only',action='store_true'); a=p.parse_args(); main(a.worker,a.check_only)
