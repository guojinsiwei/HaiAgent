"""Continue only original unclaimed jobs after the admitted worker drains.

Same worker/campaign credential remains in private tmpfs through an inode link;
no key content is read by this controller, printed, or copied to another task.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from common import PYTHON,save,assignments,validate

def owned_worker(pid,worker):
    path=Path('/proc')/str(pid)/'cmdline'
    if not path.exists():return None
    parts=path.read_bytes().decode().split('\x00')
    if str(ROOT/'parallel_worker.py') not in parts:return None
    assert parts[parts.index('--worker')+1]==str(worker)
    return parts

def attach(worker):
    protocol=validate()
    marker=ROOT/'launch_tools'/f'continuation-{worker}.json'
    assert not marker.exists(),'Continuation already registered'
    previous=json.loads((ROOT/f'launched-{worker}.json').read_text())
    parts=owned_worker(previous['pid'],worker)
    assert parts,'Original admitted worker is no longer alive; fresh local input required'
    old_key=Path(parts[parts.index('--credential')+1])
    assert old_key.parent.parent==Path('/dev/shm') and old_key.parent.name.startswith('dh-raw-pending-key-')
    private=Path(tempfile.mkdtemp(prefix='dh-raw-continuation-key-',dir='/dev/shm'))
    credential=private/'key'
    os.link(old_key,credential)
    try:
        with (ROOT/'launch_tools'/f'continuation-{worker}.log').open('x') as log:
            child=subprocess.Popen([PYTHON,'-B',str(Path(__file__)), '--worker',str(worker),
                '--continue-after',str(previous['pid']),'--credential',str(credential)],cwd=ROOT,
                stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        save(marker,dict(pid=child.pid,worker=worker,wait_for_pid=previous['pid'],time=time.time(),
            original_trials_only=True,failed_jobs_replayed=False,secret_values_read=False))
        print(json.dumps(dict(continuation_registered=True,worker=worker,pid=child.pid,
            unclaimed_jobs=sum(not (ROOT/'claims'/(r['job']+'.json')).exists()
            for r in assignments(protocol,worker)),waits_for_admitted_work=True)),flush=True)
    except Exception:
        credential.unlink(missing_ok=True);private.rmdir();raise

def continue_after(worker,pid,credential):
    while owned_worker(pid,worker):time.sleep(15)
    # An explicitly approved supplementary attempt uses the previously idle
    # slot. Let it drain too before reclaiming both slots for the original queue.
    retry_marker=ROOT/'launch_tools/raw-scheme-retry.json'
    if retry_marker.exists():
        retry_pid=json.loads(retry_marker.read_text())['pid']
        while True:
            command=Path('/proc')/str(retry_pid)/'cmdline'
            if not command.exists():break
            parts=command.read_bytes().decode().split('\x00')
            if str(ROOT/'launch_tools/run_raw_retry.py') not in parts:break
            time.sleep(15)
    protocol=validate()
    prior=json.loads((ROOT/f'health-{worker}.json').read_text())
    assert prior['state'] in ('failed','completed') and not prior.get('active')
    history=prior.get('results',[])
    rows=assignments(protocol,worker)
    pending=[r for r in rows if not (ROOT/'claims'/(r['job']+'.json')).exists()]
    save(ROOT/'launch_tools'/f'health-before-continuation-{worker}.json',prior)
    if not pending:
        credential.unlink(missing_ok=True);credential.parent.rmdir();return
    # Deployment scheduling only. Existing run_trial, environment and algorithm
    # code are unchanged. Claim existence still prevents any previous job replay.
    import parallel_worker as scheduler
    original_save=scheduler.save
    def save_combined(path,value):
        name=Path(path).name
        if name==f'health-{worker}.json':
            value=dict(value,results=history+value['results'],completed=len(history)+value['completed'],
                total=len(rows),prior_errors=prior.get('errors',[]),continuation=True)
        elif name==f'summary-{worker}.json':value=history+value
        original_save(path,value)
    scheduler.assignments=lambda ignored,selected:pending if selected==worker else assignments(ignored,selected)
    scheduler.save=save_combined
    scheduler.main(worker,credential)

def rearm(worker):
    """Reload the waiting deployment controller, retaining its own tmpfs link."""
    marker=ROOT/'launch_tools'/f'continuation-{worker}.json'
    previous=json.loads(marker.read_text())
    assert owned_worker(previous['wait_for_pid'],worker),'Only rearm while original worker drains'
    process=Path('/proc')/str(previous['pid'])/'cmdline'
    parts=process.read_bytes().decode().split('\x00')
    assert str(Path(__file__)) in parts and '--continue-after' in parts
    credential=Path(parts[parts.index('--credential')+1])
    assert credential.parent.parent==Path('/dev/shm') and credential.parent.name.startswith('dh-raw-continuation-key-')
    assert credential.is_file()
    os.kill(previous['pid'],signal.SIGTERM)
    with (ROOT/'launch_tools'/f'continuation-{worker}.log').open('a') as log:
        child=subprocess.Popen([PYTHON,'-B',str(Path(__file__)), '--worker',str(worker),
            '--continue-after',str(previous['wait_for_pid']),'--credential',str(credential)],cwd=ROOT,
            stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    save(marker,dict(previous,pid=child.pid,rearmed=time.time(),waits_for_supplementary_retry=True))
    print(json.dumps(dict(continuation_rearmed=True,worker=worker,pid=child.pid)),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--worker',type=int,required=True)
    p.add_argument('--continue-after',type=int);p.add_argument('--credential',type=Path)
    p.add_argument('--rearm',action='store_true')
    a=p.parse_args()
    if a.rearm:rearm(a.worker)
    elif a.continue_after:continue_after(a.worker,a.continue_after,a.credential)
    else:attach(a.worker)
