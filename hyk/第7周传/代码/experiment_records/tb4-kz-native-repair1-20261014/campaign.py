"""One sequential native-KZ campaign; a development pilot gates the frozen 30."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time

ROOT=Path(__file__).resolve().parent
BASE=Path('/var/tmp/lizh639-tb4-kz-dsh-unlimited-repair-20261014')
PY=Path('/var/tmp/lizh639-tb4-taotoken-smoke-20261011/venv/bin/python')
PILOT=['payments-pipeline-fix','mvcc-lsm-compaction','uefi-bootkit']
PORT=28482

def load(path, default=None):
    try:return json.loads(Path(path).read_text())
    except (OSError,ValueError):return {} if default is None else default

def save(name, data):
    p=ROOT/name;p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(data,indent=2));tmp.replace(p)

def trial_result(job, offline=False):
    paths=list((ROOT/('preflight' if offline else 'jobs')/job).glob('*/result.json'))
    if len(paths)!=1:return dict(state='engineering_failure',reason='missing_unique_result')
    t=paths[0].parent;result=load(paths[0]);exit_record=load(t/'agent/live/agent-exit.json')
    run=load(t/'agent/live/run-status.json');native=load(t/'agent/live/result.json')
    wire=load(t/'agent/live/wire-state.json')
    grade=(result.get('verifier_result') or {}).get('rewards',{}).get('reward')
    if offline:
        return dict(state='accepted' if result.get('verifier_result') and not result.get('exception_info') else 'blocked_environment',
                    exception_type=(result.get('exception_info') or {}).get('exception_type'),trial=str(t))
    clean=(not result.get('exception_info') and exit_record.get('exit_code')==0 and not exit_record.get('timed_out')
           and bool(run) and not run.get('engineering_failure') and not run.get('unregistered_plan')
           and native.get('stop_reason')=='model_submit' and native.get('submitted') is True and grade is not None)
    return dict(state='graded' if grade is not None else 'engineering_failure',engineering_clean=clean,
                reward=grade,trial=str(t),stop_reason=native.get('stop_reason'),
                exception_type=(result.get('exception_info') or {}).get('exception_type'),
                solver_exit=exit_record.get('exit_code'),timed_out=exit_record.get('timed_out',False),
                requests=wire.get('requests'),http_status_counts=wire.get('http_status_counts'))

def gate(rows):
    pilots=[r for r in rows if r.get('task') in PILOT]
    if len(pilots)!=3 or any(r.get('state') in {'pending','preflighting','running'} for r in pilots):
        return dict(expand=False,reason='pilot_incomplete')
    if not all(r.get('engineering_clean') for r in pilots):
        return dict(expand=False,reason='pilot_engineering_failure')
    passed=sum(r.get('reward')==1 for r in pilots)
    return dict(expand=passed>=1,reason='pilot_at_least_one_success' if passed else 'pilot_no_success',passed=passed,
                note='Development go/no-go only, not statistical efficacy evidence or an unbiased 30-task score.')

def space_needed(task):
    tasks=load(ROOT/'tasks.json')['tasks'];row=next(t for t in tasks if t['name']==task)
    # Admission reserve, never an algorithm termination heuristic.
    return max(30*1024**3,2*int(row.get('environment',{}).get('storage_mb',10240))*1024**2)

def space_ready(task):
    required=space_needed(task)
    return shutil.disk_usage('/var/lib/docker').free>=required and shutil.disk_usage(ROOT).free>=2*1024**3

def validate():
    seal=load(ROOT/'ready.json')
    if seal.get('offline_passed') is not True:raise RuntimeError('Offline acceptance missing')
    for name,expected in seal['files'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=expected:raise RuntimeError('Source drift: '+name)
    base=load(BASE/'ready.json')
    for name,expected in base.get('files',{}).items():
        if hashlib.sha256((BASE/name).read_bytes()).hexdigest()!=expected:raise RuntimeError('Frozen host dependency drift: '+name)
    if not PY.exists():raise RuntimeError('Pinned Harbor Python missing')

def command(task,job,offline):
    return [str(PY),str(ROOT/'entry_harbor.py'),'run','-p',str(BASE/'official/tasks'/task),
            '-a','harbor_legacy:OfflineLegacy' if offline else 'harbor_legacy:LegacyAgent',
            '--env','docker','--no-delete','-n','1','-k','1','-r','0','--verifier-timeout-multiplier','1',
            '--job-name',job,'-o',str(ROOT/('preflight' if offline else 'jobs'))]

def supervise():
    validate()
    if (ROOT/'admissions.json').exists():raise RuntimeError('No implicit replay of admitted paid trials')
    sys.path.append(str(BASE));import network_proxy
    proxy=network_proxy.ThreadingHTTPServer((network_proxy.HOST,PORT),network_proxy.Handler)
    threading.Thread(target=proxy.serve_forever,daemon=True).start()
    names=[r['name'] for r in load(ROOT/'tasks.json')['tasks']]
    order=PILOT+[t for t in names if t not in PILOT]
    rows=[dict(task=t,job=f'native-repair1-{i+1:02d}-{t}',state='pending',split='development' if t in PILOT else 'prospective') for i,t in enumerate(order)]
    phase='development';active=None
    def status(state):
        h=dict(state=state,updated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
               pid=os.getpid(),phase=phase,planned=30,results=rows,gate=gate(rows))
        save('admissions.json',h);save('health.json',h)
    try:
        status('starting')
        for index,row in enumerate(rows):
            if index==3:
                decision=gate(rows);save('expansion-decision.json',decision)
                if not decision['expand']:status('held_no_expansion');return
                phase='prospective'
            while not space_ready(row['task']):
                status('held_low_disk');time.sleep(30)
            env=dict(os.environ,PYTHONPATH=str(ROOT)+':'+str(BASE),PYTHONDONTWRITEBYTECODE='1',
                     PAIRED_TASK=row['task'],PAIRED_PROXY_URL=f'http://10.123.0.1:{PORT}')
            # Fresh container and official verifier preflight; no paid API credential.
            offlineenv=dict(env);offlineenv.pop('TAOTOKEN_API_KEY',None)
            row['state']='preflighting';status('running')
            prejob='preflight-'+row['job']
            with (ROOT/(prejob+'.log')).open('xb') as log:
                active=subprocess.Popen(command(row['task'],prejob,True),env=offlineenv,stdout=log,stderr=log,stdin=subprocess.DEVNULL)
                while active.poll() is None:status('running');time.sleep(10)
            pre=trial_result(prejob,True);active=None
            if pre['state']!='accepted':row.update(pre);status('running');continue
            while not space_ready(row['task']):status('held_low_disk');time.sleep(30)
            row['state']='admitted';row['admitted_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();status('running')
            with (ROOT/(row['job']+'.log')).open('xb') as log:
                active=subprocess.Popen(command(row['task'],row['job'],False),env=env,stdout=log,stderr=log,stdin=subprocess.DEVNULL)
                row['state']='running'
                while active.poll() is None:
                    paths=list((ROOT/'jobs'/row['job']).glob('*/agent/live/wire-state.json'))
                    if len(paths)==1:row['wire']=load(paths[0])
                    status('running');time.sleep(10)
            active=None;row.update(trial_result(row['job']));status('running')
            if row.get('state')=='engineering_failure' or row.get('solver_exit') not in (0,None):
                status('held_engineering_failure');return
        status('finished')
    except BaseException as error:
        try:save('supervisor-error.json',dict(type=type(error).__name__,automatic_paid_replay=False))
        except OSError:pass
        # Never kill a running solver because bookkeeping failed. Its embedded
        # deadline remains active; keep task networking until Harbor exits.
        if active is not None:active.wait()
        raise
    finally:proxy.shutdown()

def precheck():
    validate()
    if (ROOT/'launch-once.marker').exists():raise RuntimeError('Already launched; explicit reconciliation required')
    if not space_ready(PILOT[0]):raise RuntimeError('Root/Docker disk reserve insufficient; no model call made')
    p=subprocess.run(['docker','info','--format','{{.DockerRootDir}}'],capture_output=True,text=True,timeout=15)
    if p.returncode:raise RuntimeError('Docker unavailable')
    print('READY',flush=True)

def launch():
    precheck();bundle=json.loads(sys.stdin.readline());key=bundle.pop('key')
    if not isinstance(key,str) or not key.strip():raise ValueError('Fresh credential required')
    with (ROOT/'launch-once.marker').open('x') as f:f.write(datetime.datetime.now(datetime.timezone.utc).isoformat())
    with (ROOT/'supervisor.log').open('xb') as log:
        p=subprocess.Popen([str(PY),str(ROOT/'campaign.py'),'--supervise'],
            env=dict(os.environ,TAOTOKEN_API_KEY=key,PYTHONDONTWRITEBYTECODE='1'),
            stdout=log,stderr=log,stdin=subprocess.DEVNULL,start_new_session=True)
    print(json.dumps(dict(pid=p.pid,development_tasks=3,max_total_tasks=30,conditional_expansion=True)))

if __name__=='__main__':
    if '--supervise' in sys.argv:supervise()
    elif '--launch' in sys.argv:launch()
    else:precheck()
