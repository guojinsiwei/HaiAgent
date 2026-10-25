"""Durable execution for exactly two predeclared replacement trials."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE),str(HERE/'upstream/harbor/src'),str(HERE/'bestfgs-project/src'),str(HERE/'hai-project/src')]
from audit import verify
from control import execute, cleanup_owned
from prepare_missing2 import hashes, write

PYTHON = '/mnt/sdb/home/lizh639/terminalbench-v14-setup/runtime/bin/python'
LEDGER = HERE/'ledger'


def validate():
    ready=json.loads((HERE/'ready.json').read_text())
    intact = all((HERE/name).is_file() and hashlib.sha256((HERE/name).read_bytes()).hexdigest() == expected
                 for name,expected in ready.get('hashes',{}).items())
    if not ready.get('ready') or not intact:
        raise RuntimeError('Frozen supplement source changed')
    spec=json.loads((HERE/'supplement.json').read_text())
    if spec['total_trials'] != 2 or spec['methods'] != ['bestfgs','raw']:
        raise RuntimeError('Unexpected replacement plan')
    return ready,spec


def identity(pid):
    try:
        fields=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()
        return fields[19] if fields[0] != 'Z' else None
    except (OSError,IndexError): return None


def trial(name, credential):
    _,spec=validate(); method=name.split('-',1)[0]
    if method not in spec['methods'] or name != method+'-'+spec['task']['task']:
        raise RuntimeError('Unexpected trial name')
    folder=LEDGER/name
    with (folder/'lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (folder/'started.json').exists(): raise RuntimeError('Never replay a replacement trial')
        write(folder/'started.json',{'pid':os.getpid(),'identity':identity(os.getpid()),'time':time.time()})
        os.environ['DEEPSEEK_API_KEY']=Path(credential).read_text().strip()
        try:
            result=execute(spec['task'],method)
            audit=Path(result['report']).parent/'agent/audit.jsonl'
            result['audit_chain']=verify(audit)
            result['replacement_for']='disk_reserve_exhausted_without_official_score'
            result['supplement_protocol_sha256']=json.loads((HERE/'ready.json').read_text())['protocol_sha256']
        except Exception as error:
            result={'task':spec['task']['task'],'method':method,'infrastructure_error':type(error).__name__,
                    'replacement_for':'disk_reserve_exhausted_without_official_score'}
        finally:
            os.environ.pop('DEEPSEEK_API_KEY',None)
        write(folder/'result.json',result)


def collect(spec):
    results=[]; active=[]; blockers=[]
    for method in spec['methods']:
        name=method+'-'+spec['task']['task']; folder=LEDGER/name
        if (folder/'result.json').exists(): results.append(json.loads((folder/'result.json').read_text())); continue
        if not folder.exists(): continue
        start=json.loads((folder/'started.json').read_text()) if (folder/'started.json').exists() else None
        intent=json.loads((folder/'intent.json').read_text())
        if start and identity(start['pid']) == start['identity']: active.append({'job':name,'pid':start['pid']})
        elif time.time()-intent['created'] < 60: active.append({'job':name})
        else: blockers.append({'job':name,'reason':'child_missing_no_replay'})
    return results,active,blockers


def scheduler(credential):
    with (HERE/'worker.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        ready,spec=validate(); LEDGER.mkdir(exist_ok=True); children=[]
        while True:
            for child in children: child.poll()
            results,active,blockers=collect(spec)
            pending=[m+'-'+spec['task']['task'] for m in spec['methods'] if not (LEDGER/(m+'-'+spec['task']['task'])).exists()]
            free=min(shutil.disk_usage(HERE).free,shutil.disk_usage('/var/lib/docker').free)
            while pending and len(active)<2 and free>=120*2**30 and not blockers:
                validate(); name=pending.pop(0); folder=LEDGER/name; folder.mkdir()
                write(folder/'intent.json',{'created':time.time(),'job':name})
                with (folder/'worker.log').open('x') as log:
                    child=subprocess.Popen([PYTHON,'-B',str(HERE/'missing2.py'),'trial',name,credential],cwd=HERE,
                        stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                children.append(child); active.append({'job':name,'pid':child.pid})
                free=min(shutil.disk_usage(HERE).free,shutil.disk_usage('/var/lib/docker').free)
            state='needs_attention' if blockers else 'completed_with_errors' if len(results)==2 and any(r.get('infrastructure_error') for r in results) else 'completed' if len(results)==2 else 'waiting_for_disk' if pending and free<120*2**30 else 'running'
            write(HERE/'summary.json',results)
            write(HERE/'health.json',{'state':state,'updated':time.time(),'completed':len(results),'total':2,
                'pending':len(pending),'active':active,'problems':blockers,'free_gib':round(free/2**30,2),
                'protocol_sha256':ready['protocol_sha256']})
            if state in {'completed','completed_with_errors','needs_attention'}: return
            time.sleep(15)


def guard(credential):
    with (HERE/'guard.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        failures=0
        try:
            while failures<4:
                child=subprocess.Popen([PYTHON,'-B',str(HERE/'missing2.py'),'scheduler',credential],cwd=HERE,start_new_session=True)
                child.wait(); health=json.loads((HERE/'health.json').read_text()) if (HERE/'health.json').exists() else {}
                if child.returncode==0 and health.get('state') in {'completed','completed_with_errors','needs_attention'}: return
                failures+=1
                if failures<4: time.sleep(min(60,5*2**failures))
            write(HERE/'health.json',{'state':'needs_attention','updated':time.time(),'reason':'scheduler_restart_limit'})
        finally:
            if json.loads((HERE/'health.json').read_text()).get('state') in {'completed','completed_with_errors'}:
                Path(credential).unlink(missing_ok=True)


if __name__=='__main__':
    {'trial':trial,'scheduler':scheduler,'guard':guard}[sys.argv[1]](*sys.argv[2:])
