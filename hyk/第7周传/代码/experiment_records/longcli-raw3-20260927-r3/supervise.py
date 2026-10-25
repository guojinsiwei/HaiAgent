"""One durable Raw trial at a time; restart only orchestration, never rerun tools."""
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from control import validate,export
from runner import HERE,PYTHON,run_one
from haiagent.storage import atomic_json

def identity(pid):
    try:
        fields=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()
        return fields[19] if fields[0]!='Z' else None
    except (FileNotFoundError,ProcessLookupError): return None

def event(name,**fields):
    with (HERE/'supervision.jsonl').open('a') as f:
        f.write(json.dumps(dict(event=name,time=time.time(),**fields))+'\n'); f.flush(); os.fsync(f.fileno())

def trial(task):
    folder=HERE/'ledger'/task
    with (folder/'lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (folder/'started.json').exists(): raise RuntimeError('No trial replay')
        atomic_json(folder/'started.json',{'pid':os.getpid(),'identity':identity(os.getpid())})
        try:
            result=run_one(task,os.environ['DEEPSEEK_API_KEY'])
            artifact=export(task)
            record={k:result.get(k) for k in ['submitted','stop_reason','interaction_rounds','tool_calls','wall_seconds']}
            record.update(task_id=task,artifact=artifact,official_success=None)
            record['needs_attention']=result['stop_reason'] in {'api_error','infrastructure_error','interrupted'}
        except Exception as error:
            record={'task_id':task,'needs_attention':True,'error_type':type(error).__name__}
        atomic_json(folder/'result.json',record)

def scheduler(credential):
    with (HERE/'worker.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        protocol=validate()
        os.environ['DEEPSEEK_API_KEY']=Path(credential).read_text().strip()
        ledger=HERE/'ledger'; ledger.mkdir(exist_ok=True)
        children=[]
        last_state=None
        while True:
            for p in children: p.poll()
            results=[]; active=None; problem=None
            for task in protocol['tasks']:
                folder=ledger/task
                if (folder/'result.json').exists():
                    result=json.loads((folder/'result.json').read_text()); results.append(result)
                    if result['needs_attention']: problem={'task':task,'reason':result.get('stop_reason',result.get('error_type'))}; break
                    continue
                active=task
                if folder.exists():
                    intent=json.loads((folder/'intent.json').read_text())
                    started=json.loads((folder/'started.json').read_text()) if (folder/'started.json').exists() else None
                    if started and identity(started['pid'])==started['identity']: break
                    if time.time()-intent['created']<60: break
                    problem={'task':task,'reason':'child_missing_no_automatic_replay'}; break
                if shutil.disk_usage(HERE).free<2*2**30: break
                validate()
                folder.mkdir()
                atomic_json(folder/'intent.json',{'created':time.time(),'task':task})
                with (folder/'worker.log').open('x') as log:
                    p=subprocess.Popen([PYTHON,'-B',str(HERE/'supervise.py'),'trial',task],cwd=HERE,
                        stdout=log,stderr=subprocess.STDOUT,env=dict(os.environ),start_new_session=True)
                children.append(p); event('dispatch',task=task,pid=p.pid)
                break
            state='needs_attention' if problem else 'completed' if len(results)==len(protocol['tasks']) else 'waiting_for_disk' if active and not (ledger/active).exists() else 'running'
            if state!=last_state: event('state',state=state,problem=problem); last_state=state
            atomic_json(HERE/'summary.json',results)
            atomic_json(HERE/'health.json',{'state':state,'updated':time.time(),'active':active,
                'completed':sum(not r['needs_attention'] for r in results),'total':len(protocol['tasks']),
                'results':results,'problem':problem})
            if state in {'completed','needs_attention'}: return
            time.sleep(15)

def guard(credential):
    with (HERE/'guard.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:
            for attempt in range(4):
                event('scheduler_start',attempt=attempt+1)
                p=subprocess.Popen([PYTHON,'-B',str(HERE/'supervise.py'),'scheduler',credential],cwd=HERE)
                p.wait()
                health=json.loads((HERE/'health.json').read_text()) if (HERE/'health.json').exists() else {}
                if p.returncode==0 and health.get('state') in {'completed','needs_attention'}: return
                event('scheduler_exit',code=p.returncode,attempt=attempt+1)
                if attempt<3: time.sleep(30)
            atomic_json(HERE/'guard-failure.json',{'state':'needs_attention','reason':'scheduler_restart_limit','updated':time.time()})
        finally:
            Path(credential).unlink(missing_ok=True)
            try: Path(credential).parent.rmdir()
            except OSError: pass

if __name__=='__main__': {'guard':guard,'scheduler':scheduler,'trial':trial}[sys.argv[1]](sys.argv[2])
