"""Durable dispatch: independent trial workers survive scheduler restarts.

Never rerun a launched trial. A missing/ambiguous child stops dispatch for review.
The guard may restart the scheduler, not model attempts or scientific budgets.
"""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import control
from control import HERE, METHODS, PYTHON, validate, execute, environment, cleanup_owned
from prepare import write, reserve
from outcomes import classify

LEDGER = HERE/'ledger'

def event(name, **fields):
    with (HERE/'supervision.jsonl').open('a') as f:
        f.write(json.dumps(dict(event=name,time=time.time(),**fields))+'\n')
        f.flush()
        os.fsync(f.fileno())

def identity(pid):
    try:
        fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()
        if fields[0] == 'Z': return None
        return fields[19]
    except (FileNotFoundError, ProcessLookupError):
        return None

def trial(name):
    directory = LEDGER/name
    with (directory/'lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (directory/'started.json').exists():
            raise RuntimeError('Never restart a launched trial')
        spec = json.loads((directory/'intent.json').read_text())
        write(directory/'started.json', {'pid':os.getpid(),'identity':identity(os.getpid()),'time':time.time()})
        try:
            result = execute(spec['task'],spec['method'])
            events = [json.loads(line) for line in (Path(result['report']).parent/'agent/audit.jsonl').read_text().splitlines()]
            result['classification'] = classify(result,events)
        except Exception as error:
            result = {'task':spec['task']['task'],'method':spec['method'],
                      'infrastructure_error':type(error).__name__,
                      'classification':{'infrastructure_ok':False,'reasons':['trial_worker_exception:'+type(error).__name__]}}
        write(directory/'result.json', result)

def collect():
    rows = json.loads((HERE/'prior-results.json').read_text())
    active, problems = [], []
    for d in sorted(LEDGER.iterdir()):
        spec = json.loads((d/'intent.json').read_text())
        if (d/'result.json').exists():
            value = json.loads((d/'result.json').read_text())
            rows.append(value)
            if not value['classification']['infrastructure_ok']:
                problems.append({'job':d.name,'reasons':value['classification']['reasons']})
            continue
        start = json.loads((d/'started.json').read_text()) if (d/'started.json').exists() else None
        if start and identity(start['pid']) == start['identity']:
            active.append(spec)
        elif time.time()-spec['created'] < 60:
            active.append(spec) # Intent/start atomicity gap: wait, never relaunch.
        else:
            problems.append({'job':d.name,'reasons':['launched_child_missing_no_automatic_replay']})
    return rows,active,problems

def scheduler(credential):
    LEDGER.mkdir(exist_ok=True)
    with (HERE/'worker.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        ready = validate()
        os.environ['DEEPSEEK_API_KEY'] = Path(credential).read_text().strip()
        manifest=json.loads((HERE/'manifest.json').read_text())
        wanted=[]
        prior={(r['task'],r['method']) for r in json.loads((HERE/'prior-results.json').read_text())}
        for i,row in enumerate(manifest['tasks']):
            for method in METHODS[i%3:]+METHODS[:i%3]:
                if (row['task'],method) not in prior: wanted.append((row,method))
        processes=[]
        last_state=None
        while True:
            for p in processes: p.poll() # Reap our children; adopted workers are checked via /proc.
            rows,active,problems=collect()
            pending=[(r,m) for r,m in wanted if not (LEDGER/(m+'-'+r['task'])).exists()]
            disk_ok=True
            try: reserve()
            except RuntimeError: disk_ok=False
            state='draining_after_error' if problems and active else 'needs_attention' if problems else 'waiting_for_disk' if not disk_ok and pending else 'running'
            if not problems and disk_ok:
                while pending and len(active)<3:
                    validate()
                    row,method=pending.pop(0)
                    name=method+'-'+row['task']
                    d=LEDGER/name
                    d.mkdir() # Exclusive intent prevents duplicate launches after any restart.
                    spec={'task':row,'method':method,'created':time.time()}
                    write(d/'intent.json',spec)
                    with (d/'worker.log').open('x') as out:
                        p=subprocess.Popen([PYTHON,'-B',str(HERE/'durable.py'),'trial',name],
                            cwd=HERE,env=environment(),stdout=out,stderr=subprocess.STDOUT,start_new_session=True)
                    processes.append(p)
                    active.append(spec)
                    event('dispatch',job=name,pid=p.pid)
            if not pending and not active and not problems: state='completed'
            if state!=last_state:
                event('state',state=state,problems=problems)
                last_state=state
            write(HERE/'summary.json',rows)
            write(HERE/'health.json',{'state':state,'updated':time.time(),'completed':sum(r.get('verifier_result') is not None for r in rows),
                'total':36,'pending':len(pending),'active':[{'task':s['task']['task'],'method':s['method']} for s in active],
                'problems':problems,'protocol_sha256':ready['protocol_sha256']})
            if state in {'completed','needs_attention'}: return
            time.sleep(15)

def guard(credential):
    with (HERE/'guard.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:
            for attempt in range(4):
                event('scheduler_start',attempt=attempt+1)
                p=subprocess.Popen([PYTHON,'-B',str(HERE/'durable.py'),'scheduler',credential],cwd=HERE)
                p.wait()
                health=json.loads((HERE/'health.json').read_text()) if (HERE/'health.json').exists() else {}
                if p.returncode==0 and health.get('state') in {'completed','needs_attention'}: return
                event('scheduler_exit',code=p.returncode,attempt=attempt+1)
                if attempt<3: time.sleep(30)
            write(HERE/'guard-failure.json',{'state':'needs_attention','reason':'scheduler_restart_limit','time':time.time()})
        finally:
            Path(credential).unlink(missing_ok=True)
            try: Path(credential).parent.rmdir()
            except OSError: pass

if __name__=='__main__':
    {'trial':trial,'scheduler':scheduler,'guard':guard}[sys.argv[1]](sys.argv[2])
