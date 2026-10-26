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
from admission import shared_wire_failures,terminal_provider_failures

def progress(job):
    """Bounded public log status; never read credentials or process environments."""
    if not job:return None
    base=ROOT/'runs'/job
    paths=[base/'model-audit.jsonl']+list((base/'trace').glob('*.jsonl'))
    latest=max((p.stat().st_mtime for p in paths if p.is_file()),default=None)
    audit=base/'model-audit.jsonl'
    evidence={}
    if audit.is_file():
        with audit.open('rb') as stream:
            stream.seek(max(0,audit.stat().st_size-262144))
            lines=stream.read().decode('utf-8','replace').splitlines()
        for line in reversed(lines):
            try: row=json.loads(line)
            except ValueError:continue
            if 'last_audit_event' not in evidence:evidence['last_audit_event']=row.get('event')
            usage=row.get('cumulative_usage')
            if usage:evidence['usage']=usage;evidence['usage_role']=row.get('role');break
    trace=base/'trace/events.jsonl'
    if trace.is_file():
        with trace.open('rb') as stream:
            stream.seek(max(0,trace.stat().st_size-262144))
            lines=stream.read().decode('utf-8','replace').splitlines()
        for line in reversed(lines):
            try:row=json.loads(line)
            except ValueError:continue
            event=row.get('event')
            if 'last_runtime_event' not in evidence:evidence['last_runtime_event']=event
            if event in ('tool_start','tool_end','tool_attempt','tool_call'):
                ident=row.get('call_id') or row.get('evidence_id','')
                evidence['last_tool']=ident
                evidence['last_tool_event']=event
                evidence['last_tool_time']=row.get('time')
                evidence['last_tool_age_seconds']=max(0,time.time()-row.get('time',time.time()))
                break
    return dict(updated=latest,age_seconds=None if latest is None else max(0,time.time()-latest),
                stale=latest is not None and time.time()-latest>600,**evidence)

def main(worker,credential):
    state=dict(worker=worker,state='starting',completed=0,total=2,active=None,results=[])
    stopped=threading.Event()
    def heartbeat():
        while not stopped.is_set():
            save(ROOT/('health-'+str(worker)+'.json'),dict(state,updated=time.time(),pid=os.getpid(),
                progress=progress(state['active'])))
            stopped.wait(15)
    with (ROOT/('worker-'+str(worker)+'.lock')).open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        protocol=validate()
        state['total']=len(assignments(protocol,worker))
        thread=threading.Thread(target=heartbeat,daemon=True); thread.start()
        state['state']='running'
        try:
            for row in assignments(protocol,worker):
                # A plain local/shared-file guard, not a model or GPT automation.
                provider_failures=terminal_provider_failures(ROOT)
                if provider_failures:raise RuntimeError('Terminal provider failure; no new tasks: '+str(provider_failures))
                failures=shared_wire_failures(ROOT)
                if len(failures)>=2:
                    raise RuntimeError('Two protocol-limited tasks; stop new admissions: '+','.join(failures))
                state['active']=row['job']
                claim=ROOT/'claims'/(row['job']+'.json')
                claim.parent.mkdir(exist_ok=True)
                with claim.open('x') as stream: json.dump(dict(row,claimed=time.time()),stream)
                make_root(row)
                with (ROOT/('console-'+row['job']+'.log')).open('x') as log:
                    child_env=dict(os.environ,LONGCLI_METHOD=row['method'])
                    child=subprocess.Popen([PYTHON,'-B',str(ROOT/'runner.py'),'--row',str(claim),
                        '--credential',str(credential)],stdout=log,stderr=subprocess.STDOUT,
                        start_new_session=True,cwd=ROOT,env=child_env)
                    try: child.wait(timeout=row['wall_seconds']+180)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid,9); child.wait(); raise RuntimeError('Trial exceeded hard wall guard')
                summary=ROOT/'runs'/row['job']/'summary.json'
                if child.returncode or not summary.exists(): raise RuntimeError('Trial infrastructure failure; candidate retained')
                result=json.loads(summary.read_text()); state['results'].append(result); state['completed']+=1
                save(ROOT/('summary-'+str(worker)+'.json'),state['results'])
                if terminal_provider_failures(ROOT):
                    raise RuntimeError('Terminal provider failure; remaining trials not started')
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
    parser=argparse.ArgumentParser(); parser.add_argument('--worker',type=int,choices=(0,),required=True)
    parser.add_argument('--credential',type=Path,required=True)
    args=parser.parse_args(); main(args.worker,args.credential)
