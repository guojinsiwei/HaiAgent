"""Two bounded slots per container, exclusive claims, no automatic task replay."""
import argparse
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import json
import os
from pathlib import Path
import subprocess
import threading
import time

from common import ROOT, PYTHON, validate, assignments, save
from cube_prepare import make_root
from admission import shared_wire_failures, terminal_provider_failures


def progress(job):
    """Bounded public progress; never reads credentials or process environments."""
    if not job:
        return None
    base=ROOT/'runs'/job
    paths=[base/'model-audit.jsonl',base/'trace/events.jsonl']
    latest=max((p.stat().st_mtime for p in paths if p.is_file()),default=None)
    return dict(updated=latest,age_seconds=None if latest is None else max(0,time.time()-latest),
                stale=latest is not None and time.time()-latest>600)


def admission_reason():
    provider=terminal_provider_failures(ROOT)
    if provider:
        return 'Terminal provider failure; no new admissions: '+str(provider)
    wire=shared_wire_failures(ROOT)
    if len(wire)>=2:
        return 'Two confirmed terminal wire faults; no new admissions: '+','.join(wire)
    return None


def run_trial(row,credential):
    claim=ROOT/'claims'/(row['job']+'.json')
    claim.parent.mkdir(exist_ok=True)
    with claim.open('x') as stream:
        json.dump(dict(row,claimed=time.time()),stream)
    make_root(row)
    with (ROOT/('console-'+row['job']+'.log')).open('x') as log:
        child=subprocess.Popen([PYTHON,'-B',str(ROOT/'runner.py'),'--row',str(claim),
            '--credential',str(credential)],stdout=log,stderr=subprocess.STDOUT,
            start_new_session=True,cwd=ROOT,env=dict(os.environ,LONGCLI_METHOD=row['method']))
        try:
            child.wait(timeout=row['wall_seconds']+180)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid,9)
            child.wait()
            raise RuntimeError('Trial exceeded hard wall guard: '+row['job'])
    summary=ROOT/'runs'/row['job']/'summary.json'
    if child.returncode or not summary.exists():
        raise RuntimeError('Trial infrastructure failure; preserve candidate: '+row['job'])
    result=json.loads(summary.read_text())
    if result['stop_reason'] in ('api_error','model_unavailable','credential_or_balance_error',
        'infrastructure_error','delivery_error'):
        return result, 'Provider/infrastructure failure: '+row['job']
    return result,None


def schedule(rows,slots,execute,publish,admission):
    """Wait for all admitted work even on an error; never retry claimed work."""
    remaining=iter(rows)
    active={}
    exhausted=False
    errors=[]
    with ThreadPoolExecutor(max_workers=len(slots)) as pool:
        while active or (not exhausted and not errors):
            reason=admission()
            if reason and reason not in errors:
                errors.append(reason)
            if not errors and not exhausted:
                used={value['slot'] for value in active.values()}
                for slot in range(len(slots)):
                    if slot in used:
                        continue
                    try:
                        row=next(remaining)
                    except StopIteration:
                        exhausted=True
                        break
                    row=dict(row,slot=slot,cpu_affinity=slots[slot])
                    active[pool.submit(execute,row)]=row
                publish(active=list(active.values()),errors=list(errors))
            if not active:
                break
            finished,_=wait(active,timeout=15,return_when=FIRST_COMPLETED)
            for future in finished:
                row=active.pop(future)
                try:
                    result,reason=future.result()
                    if reason:
                        errors.append(reason)
                    publish(result=result,active=list(active.values()),errors=list(errors))
                except Exception as error:
                    errors.append(type(error).__name__+': '+str(error))
                    publish(active=list(active.values()),errors=list(errors))
        publish(active=[],errors=list(errors),terminal=True)
    return errors


def main(worker,credential):
    import fcntl
    protocol=validate()
    slots=json.loads((ROOT/f'resources-{worker}.json').read_text())['cpu_slots']
    assert len(slots)==protocol['generation_concurrency_per_worker']==2
    rows=assignments(protocol,worker)
    state=dict(worker=worker,state='starting',completed=0,total=len(rows),active=[],
               concurrency=2,results=[],errors=[],unstarted=len(rows))
    stopped=threading.Event()
    mutex=threading.Lock()
    def snapshot():
        with mutex:
            return json.loads(json.dumps(state))
    def heartbeat():
        while not stopped.is_set():
            public=snapshot()
            public.update(updated=time.time(),pid=os.getpid(),
                progress={r['job']:progress(r['job']) for r in public['active']})
            save(ROOT/f'health-{worker}.json',public)
            stopped.wait(15)
    def publish(active,errors,result=None,terminal=False):
        with mutex:
            if result:
                state['results'].append(result)
                state['completed']+=1
                save(ROOT/f'summary-{worker}.json',state['results'])
            state.update(active=active,errors=errors,
                unstarted=len(rows)-sum((ROOT/'claims'/(r['job']+'.json')).exists() for r in rows))
            if terminal:
                state['state']='failed' if errors else 'completed'
            elif errors:
                state['state']='draining_after_error'
    with (ROOT/f'worker-{worker}.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        thread=threading.Thread(target=heartbeat,daemon=True)
        thread.start()
        errors=[]
        try:
            with mutex:
                state['state']='running'
            errors=schedule(rows,slots,lambda r:run_trial(r,credential),publish,admission_reason)
        finally:
            stopped.set()
            thread.join(timeout=3)
            final=snapshot()
            final.update(updated=time.time(),pid=os.getpid())
            save(ROOT/f'health-{worker}.json',final)
            credential.unlink(missing_ok=True)
            credential.parent.rmdir()
        if errors:
            raise RuntimeError('; '.join(errors))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--worker',type=int,choices=(0,1),required=True)
    parser.add_argument('--credential',type=Path,required=True)
    args=parser.parse_args()
    main(args.worker,args.credential)
