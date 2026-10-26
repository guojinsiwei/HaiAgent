"""One durable worker per container. Never silently replay a claimed trial."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import threading
import time

from common import ROOT, PYTHON, validate, assignments, save
from cube_prepare import make_root

def main(worker,credential):
    state=dict(worker=worker,state='starting',completed=0,total=10,active=None,results=[])
    stopped=threading.Event()
    def heartbeat():
        while not stopped.is_set():
            save(ROOT/('health-'+str(worker)+'.json'),dict(state,updated=time.time(),pid=os.getpid()))
            stopped.wait(15)
    with (ROOT/('worker-'+str(worker)+'.lock')).open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        protocol=validate()
        thread=threading.Thread(target=heartbeat,daemon=True); thread.start()
        state['state']='running'
        try:
            for row in assignments(protocol,worker):
                state['active']=row['job']
                claim=ROOT/'claims'/(row['job']+'.json')
                claim.parent.mkdir(exist_ok=True)
                with claim.open('x') as stream: json.dump(dict(row,claimed=time.time()),stream)
                make_root(row)
                with (ROOT/('console-'+row['job']+'.log')).open('x') as log:
                    child=subprocess.Popen([PYTHON,'-B',str(ROOT/'runner.py'),'--row',str(claim),
                        '--credential',str(credential)],stdout=log,stderr=subprocess.STDOUT,
                        start_new_session=True,cwd=ROOT)
                    try: child.wait(timeout=row['wall_seconds']+180)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid,9); child.wait(); raise RuntimeError('Trial exceeded hard wall guard')
                summary=ROOT/'runs'/row['job']/'summary.json'
                if child.returncode or not summary.exists(): raise RuntimeError('Trial infrastructure failure; candidate retained')
                result=json.loads(summary.read_text()); state['results'].append(result); state['completed']+=1
                save(ROOT/('summary-'+str(worker)+'.json'),state['results'])
                if result['stop_reason'] in ('api_error','model_unavailable','credential_or_balance_error',
                    'infrastructure_error','delivery_error'):
                    raise RuntimeError('Provider/infrastructure failure; remaining trials not started')
            state.update(state='completed',active=None)
        except Exception as error:
            state.update(state='failed',error_type=type(error).__name__,reason=str(error))
            raise
        finally:
            stopped.set(); thread.join(timeout=3)
            save(ROOT/('health-'+str(worker)+'.json'),dict(state,updated=time.time(),pid=os.getpid()))
            credential.unlink(missing_ok=True)
            credential.parent.rmdir()

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--worker',type=int,choices=(0,1),required=True)
    parser.add_argument('--credential',type=Path,required=True)
    args=parser.parse_args(); main(args.worker,args.credential)
