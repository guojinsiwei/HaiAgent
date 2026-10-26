"""Independent KZ-on-DSH campaign; per-task faults continue without automatic retry."""
import collections,datetime,hashlib,importlib.util,json,os,shutil,subprocess,sys,threading,time,uuid
try:
    import fcntl
except ImportError:
    fcntl=None  # Pure receipt/queue tests work on Windows; supervision is Linux-only.
from pathlib import Path
from receipts import read_receipt, lifecycle_status, valid_reward
from storage import atomic_json, supervisor_lock
from recovery import process_identity, reconcile, completed_attempt
from experiment import validate_protocol
from spending import BudgetService
from queue_policy import TERMINAL,initial_rows,append_retry_batch,candidates,finish,first_finished,summary
ROOT=Path(__file__).resolve().parent
BASE=ROOT/'dependencies'
PY=str(ROOT/'venv/bin/python')
PORT=28635

def read(p):
    try:return json.loads(Path(p).read_text())
    except (FileNotFoundError,ValueError):return {}

def save(name,value):
    atomic_json(ROOT/name,value)


def durable(name,value,sleep=time.sleep):
    while True:
        try:save(name,value);return
        except OSError as e:
            # Do not launch anything or kill active trials when bookkeeping is unavailable.
            print(json.dumps(dict(state='held_checkpoint_io',errno=e.errno)),flush=True);sleep(10)

def validate():
    validate_protocol(ROOT)
    for base in (ROOT,BASE):
        seal=read(base/'ready.json')
        if not seal.get('files'):raise RuntimeError('Missing seal: '+str(base))
        for name,digest in seal['files'].items():
            if hashlib.sha256((base/name).read_bytes()).hexdigest()!=digest:raise RuntimeError('Source drift: '+name)
    if not read(ROOT/'ready.json').get('passed'):raise RuntimeError('Offline acceptance required')

def disk_need(task):
    r=next(r for r in read(ROOT/'tasks.json')['tasks'] if r['name']==task)
    return max(30*1024**3,2*int(r.get('environment',{}).get('storage_mb',10240))*1024**2)

def space_ready(task,active):
    # Reserve active trials' remaining scratch space as well as the next trial.
    return (shutil.disk_usage('/var/lib/docker').free>=disk_need(task)+sum(disk_need(x['row']['task']) for x in active.values())
            and shutil.disk_usage(ROOT).free>=2*1024**3)

def command(row,offline):
    agent='OfflineNative' if offline else 'Native'
    return [PY,str(ROOT/'trial_runner.py'),PY,str(ROOT/'entry_harbor.py'),'run','-p',str(BASE/'official/tasks'/row['task']),'-a','agents:'+agent,
        '--env','docker','--no-delete','-n','1','-k','1','-r','0','--verifier-timeout-multiplier','1',
        '--job-name',('preflight-' if offline else '')+row['job'],'-o',str(ROOT/('preflight' if offline else 'jobs'))]

def trial(row,offline=False):
    job=('preflight-' if offline else '')+row['job']
    folder=ROOT/('preflight' if offline else 'jobs')/job
    paths=list(folder.glob('*/config.json')) or list(folder.glob('*/result.json'))
    if len(paths)!=1:return dict(engineering_clean=False,reason='missing_unique_trial')
    t=paths[0].parent
    res,result_status=read_receipt(t/'result.json');res=res or {}
    exception=res.get('exception_info')
    exc=exception.get('exception_type') if isinstance(exception,dict) else exception
    verifier=res.get('verifier_result')
    rewards=verifier.get('rewards') if isinstance(verifier,dict) else None
    reward=rewards.get('reward') if isinstance(rewards,dict) else None
    attempt_id=row.get('preflight_attempt_id' if offline else 'attempt_id')
    lifecycle,failures=lifecycle_status(t/'lifecycle.json',attempt_id)
    clean=result_status=='present' and not exception and valid_reward(reward) and lifecycle=='succeeded'
    out=dict(trial=str(t),reward=reward,exception_type=exc,engineering_clean=clean,
             result_status=result_status,lifecycle_status=lifecycle,collection_failures=failures)
    if offline:return out
    live=t/'agent/live'
    ex,exit_status=read_receipt(live/'agent-exit.json');ex=ex or {}
    code=ex.get('exit_code')
    exit_valid=(exit_status=='present' and type(code) is int and type(ex.get('timed_out')) is bool
                and (attempt_id is None or ex.get('attempt_id')==attempt_id))
    out.update(solver_exit=code,timed_out=ex.get('timed_out'),exit_receipt_status=exit_status)
    out['engineering_clean']=clean and exit_valid and code==0 and not ex.get('timed_out')
    usage,usage_status=read_receipt(live/'wire-state.json');usage=usage or {}
    progress=read(live/'progress.json');native=read(live/'run-status.json')
    out.update(requests=usage.get('requests'),tools=progress.get('tools'),usage=read(live/'usage.json'),usage_status=usage_status,
               http_status_counts=usage.get('http_status_counts',{}),native_status=native)
    wall=read(live/'server-timeout.json');stop=read(live/'budget-stop.json');reason=stop.get('reason')
    out['budget_stop']=stop;out['provider']=read(live/'provider-state.json')
    out['budget_exhausted']=reason in ('per_task_budget_exhausted','per_task_request_limit') or wall.get('reason')=='solver_wall_limit'
    if out['budget_exhausted'] and clean and exit_valid:
        out.update(engineering_clean=True,completion='budget_exhausted')
    if native.get('engineering_failure') and not out['budget_exhausted']:out['engineering_clean']=False
    if out['provider'].get('kind')=='accounting' or reason in ('usage_unavailable','usage_exceeds_model_ceiling','budget_service_unavailable'):out['engineering_clean']=False
    return out


def live_snapshot(row):
    paths=list((ROOT/'jobs'/row['job']).glob('*/agent/live'))
    if len(paths)!=1:return {}
    p=paths[0];state=read(p/'wire-state.json')
    return {k:state.get(k) for k in ('requests','tools','updated_utc','time','http_status_counts') if k in state}

def proxy_module():
    spec=importlib.util.spec_from_file_location('candidate_network_proxy',BASE/'network_proxy.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def supervise(resume=False):
    validate()
    with supervisor_lock(ROOT):
        restored=None
        if (ROOT/'admissions.json').exists():
            if not resume:raise RuntimeError('Use explicit reconciliation and --resume; no implicit replay')
            restored,problems=reconcile(ROOT,read(ROOT/'admissions.json'),trial)
            if problems:raise RuntimeError('Recovery blocked: '+repr(problems))
        elif resume:raise RuntimeError('No campaign to resume')
        budget=BudgetService(ROOT,port=28636)
        network_proxy=proxy_module()
        proxy=network_proxy.ThreadingHTTPServer((network_proxy.HOST,PORT),network_proxy.Handler)
        threading.Thread(target=proxy.serve_forever,daemon=True).start()
        rows=restored['rows'] if restored else initial_rows([t['name'] for t in read(ROOT/'tasks.json')['tasks']],read(ROOT/'history.json'))
        active={};retry_built=bool(restored and restored['phase']=='retry');auth_pause=False;draining=False;recovery_pause=False
        def checkpoint(state):
            h=dict(state=state,updated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),pid=os.getpid(),supervisor_identity=process_identity(os.getpid()),auth_paused=auth_pause,
                phase='retry' if retry_built else 'first',summary=summary(rows),rows=rows,spending=budget.snapshot(),
                active=[dict(job=v['row']['job'],pid=v['process'].pid,offline=v['offline']) for v in active.values()])
            durable('admissions.json',h);durable('health.json',h)
        checkpoint('starting')
        try:
            while True:
                spending=budget.snapshot()
                if spending.get('halt_reason'):
                    # The reserving container writes its own stop receipt. Host
                    # must not write into container-owned live directories.
                    if not active:checkpoint('held_budget_or_provider');break
                control=read(ROOT/'control.json')
                if control.get('command')=='drain' and control.get('supervisor_identity')==process_identity(os.getpid()):draining=True
                for job,entry in list(active.items()):
                    row=entry['row'];process=entry['process']
                    if process.poll() is None:
                        try:row['live']=live_snapshot(row)
                        except (OSError,ValueError):pass
                        continue
                    entry['log'].close();del active[job]
                    receipt=completed_attempt(ROOT,row,entry['offline'])
                    if receipt is None:
                        row.update(state='reconciliation_required',reason='missing_or_active_runner_receipt')
                        recovery_pause=True
                        checkpoint('held_reconciliation')
                        continue
                    try:
                        result=trial(row,entry['offline']);result['harbor_exit']=process.returncode
                        if process.returncode!=0:result['engineering_clean']=False
                        if entry['offline']:
                            row['preflight']=result
                            if result['engineering_clean']:row.update(state='pending',preflight_ok=True)
                            else:finish(row,dict(**result,reason='preflight_failed',paid_calls=0))
                        else:
                            finish(row,result)
                    except Exception as e:
                        finish(row,dict(engineering_clean=False,reason='result_collection_error',error_type=type(e).__name__))
                    checkpoint('running')
                if draining and not active:
                    checkpoint('drained');break
                if not retry_built and first_finished(rows) and not active:
                    retry_built=True  # This explicitly authorized design has no paid retries.
                    durable('retry-batch.json',dict(rows=[r.copy() for r in rows if r['stage']=='retry']))
                    checkpoint('running')
                if retry_built and not active and all(r['state'] in TERMINAL for r in rows):
                    durable('unresolved.json',dict(rows=[r for r in rows if r['stage']=='retry' and not r.get('engineering_clean')]))
                    checkpoint('finished');break
                held_disk=False
                for row in candidates(rows,{v['row']['arm'] for v in active.values()}):
                    if auth_pause or draining or recovery_pause or spending.get('halt_reason'):break
                    if any(v['row']['arm']==row['arm'] for v in active.values()):continue
                    try:
                        if not space_ready(row['task'],active):held_disk=True;continue
                        offline=not row.get('preflight_ok')
                        # Commit intent BEFORE process creation. Never silently repeat a paid admission.
                        row['preflight_attempt_id' if offline else 'attempt_id']=uuid.uuid4().hex
                        row['admission_offline']=offline
                        row.update(state='preflight_admitted' if offline else 'paid_admitted',admitted_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
                        checkpoint('running')
                        env=dict(os.environ,PYTHONPATH=str(ROOT)+':'+str(BASE),PYTHONDONTWRITEBYTECODE='1',
                            PAIRED_TASK=row['task'],PAIRED_ATTEMPT_ID=row['preflight_attempt_id' if offline else 'attempt_id'],PAIRED_PROXY_URL=f'http://10.123.0.1:{PORT}')
                        if offline:env.pop('TAOTOKEN_API_KEY',None)
                        else:env.update(CAMPAIGN_BUDGET_REQUIRED='1',CAMPAIGN_BUDGET_URL=budget.url,CAMPAIGN_BUDGET_TOKEN=budget.token,CAMPAIGN_BUDGET_JOB=row.get('budget_job',row['job']),CAMPAIGN_BUDGET_ARM='native-kz')
                        log=(ROOT/(('preflight-' if offline else '')+row['job']+'.log')).open('xb')
                        try:p=subprocess.Popen(command(row,offline),env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
                        except Exception:log.close();raise
                        active[row['job']]=dict(process=p,log=log,row=row,offline=offline)
                        row.update(state='preflighting' if offline else 'running',pid=p.pid)
                    except Exception as e:
                        finish(row,dict(engineering_clean=False,reason='dispatch_error',error_type=type(e).__name__))
                    checkpoint('running')
                checkpoint('draining' if draining else 'held_reconciliation' if recovery_pause else 'held_authentication' if auth_pause else 'held_low_disk' if held_disk and not active else 'running')
                time.sleep(10)
        finally:
            # Unexpected supervisor termination must not break an already admitted solver's proxy.
            for v in active.values():v['process'].wait();v['log'].close()
            proxy.shutdown();budget.close()

def precheck(resume=False):
    if sys.platform!='linux':raise RuntimeError('Campaign launch requires Linux')
    validate()
    if not resume and (ROOT/'launch-once.marker').exists():raise RuntimeError('Already launched')
    if resume:
        with supervisor_lock(ROOT):
            _,problems=reconcile(ROOT,read(ROOT/'admissions.json'),trial)
            if problems:raise RuntimeError('Recovery blocked: '+repr(problems))
    p=subprocess.run(['docker','info','--format','{{.DockerRootDir}}'],capture_output=True,text=True,timeout=20)
    if p.returncode or p.stdout.strip()!='/var/lib/docker':raise RuntimeError('Docker unavailable or root changed')
    print('READY',flush=True)

def launch(resume=False):
    precheck(resume);bundle=json.loads(sys.stdin.readline());key=bundle.pop('key')
    if not isinstance(key,str) or not key.strip():raise ValueError('Fresh key required')
    if not resume:
        with (ROOT/'launch-once.marker').open('x') as f:f.write(str(time.time()))
    name='supervisor-resume-'+uuid.uuid4().hex+'.log' if resume else 'supervisor.log'
    with (ROOT/name).open('xb') as log:
        p=subprocess.Popen([PY,__file__,'--resume-supervise' if resume else '--supervise'],env=dict(os.environ,TAOTOKEN_API_KEY=key,PYTHONDONTWRITEBYTECODE='1'),
            stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
    time.sleep(2)
    if p.poll() is not None:raise RuntimeError('Supervisor failed before acknowledgement; inspect before retry')
    print(json.dumps(dict(pid=p.pid,detached=True,paired_tasks=len(read(ROOT/'tasks.json')['tasks']),total_trials=3,retry_batches=0,total_concurrency=1)))

if __name__=='__main__':
    if '--check-resume' in sys.argv:precheck(resume=True)
    elif '--resume-supervise' in sys.argv:supervise(resume=True)
    elif '--resume' in sys.argv:launch(resume=True)
    elif '--supervise' in sys.argv:supervise()
    elif '--launch' in sys.argv:launch()
    else:precheck()
