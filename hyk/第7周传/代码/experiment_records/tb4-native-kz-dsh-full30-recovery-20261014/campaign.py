"""Two-arm recovery. Durable admission; per-task faults continue; one final retry batch."""
import collections,datetime,fcntl,hashlib,json,os,shutil,subprocess,sys,threading,time
from pathlib import Path
from queue_policy import TERMINAL,initial_rows,append_retry_batch,candidates,finish,first_finished,summary
ROOT=Path(__file__).resolve().parent
BASE=Path('/var/tmp/lizh639-tb4-kz-dsh-unlimited-repair-20261014')
REPAIR=Path('/mnt/sdb/home/lizh639/tb4-kz-native-repair1-20261014')
PY='/var/tmp/lizh639-tb4-taotoken-smoke-20261011/venv/bin/python'
PORT=28483

def read(p):
    try:return json.loads(Path(p).read_text())
    except (FileNotFoundError,ValueError):return {}

def save(name,value):
    p=ROOT/name;p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix(p.suffix+'.tmp')
    with tmp.open('w') as f:
        json.dump(value,f,indent=2);f.flush();os.fsync(f.fileno())
    tmp.replace(p)

def durable(name,value,sleep=time.sleep):
    while True:
        try:save(name,value);return
        except OSError as e:
            # Do not launch anything or kill active trials when bookkeeping is unavailable.
            print(json.dumps(dict(state='held_checkpoint_io',errno=e.errno)),flush=True);sleep(10)

def validate():
    for base in (ROOT,BASE,REPAIR):
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
    agent=('OfflineNative' if offline else 'Native') if row['arm']=='native-kz' else ('OfflineDSH' if offline else 'DSH')
    return [PY,str(ROOT/'entry_harbor.py'),'run','-p',str(BASE/'official/tasks'/row['task']),'-a','agents:'+agent,
        '--env','docker','--no-delete','-n','1','-k','1','-r','0','--verifier-timeout-multiplier','1',
        '--job-name',('preflight-' if offline else '')+row['job'],'-o',str(ROOT/('preflight' if offline else 'jobs'))]

def trial(row,offline=False):
    job=('preflight-' if offline else '')+row['job']
    folder=ROOT/('preflight' if offline else 'jobs')/job
    paths=list(folder.glob('*/config.json')) or list(folder.glob('*/result.json'))
    if len(paths)!=1:return dict(engineering_clean=False,reason='missing_unique_trial')
    t=paths[0].parent;res=read(t/'result.json');exc=(res.get('exception_info') or {}).get('exception_type')
    reward=(res.get('verifier_result') or {}).get('rewards',{}).get('reward')
    out=dict(trial=str(t),reward=reward,exception_type=exc,engineering_clean=bool(res.get('verifier_result')) and not exc)
    if offline:return out
    live=t/'agent/live';ex=read(live/'agent-exit.json');transport=read(t/'agent/transport-result.json')
    code=ex.get('exit_code',transport.get('agent_return_code'))
    out.update(solver_exit=code,timed_out=ex.get('timed_out',False))
    out['engineering_clean']=out['engineering_clean'] and code==0 and not out['timed_out'] and reward is not None
    if row['arm']=='native-kz':
        run=read(live/'run-status.json');result=read(live/'result.json');wire=read(live/'wire-state.json')
        out.update(requests=wire.get('requests'),http_status_counts=wire.get('http_status_counts',{}),stop_reason=result.get('stop_reason'))
        out['engineering_clean']=out['engineering_clean'] and bool(run) and not run.get('engineering_failure') and not run.get('unregistered_plan') and result.get('submitted') is True and result.get('stop_reason')=='model_submit'
    else:
        usage=read(live/'shared-state.json');statuses=collections.Counter();attempts=0
        p=live/'route.jsonl'
        if p.exists():
            with p.open() as f:
                for line in f:
                    try:item=json.loads(line)
                    except ValueError:continue
                    if item.get('event')=='response':statuses[str(item.get('status'))]+=1
                    if item.get('event')=='request_shape':attempts+=1
        out.update(requests=usage.get('requests'),actual_http_attempts=attempts if p.exists() else None,
                   tools=usage.get('tools'),usage=usage,http_status_counts=dict(statuses))
    statuses=out.get('http_status_counts') or {}
    out['auth_failure']=bool(statuses.get('401') or statuses.get('402') or (statuses.get('403') and not statuses.get('200')))
    wall=read(live/('server-timeout.json' if row['arm']=='native-kz' else 'wall-limit.json'))
    out['budget_exhausted']=bool(ex.get('timed_out') and wall.get('reason')=='solver_wall_limit_3h' and wall.get('limit_seconds')==10800)
    if out['budget_exhausted'] and not exc and reward is not None and not out['auth_failure']:
        # The common solver budget is an experimental outcome, not a free retry.
        out.update(engineering_clean=True,completion='budget_exhausted')
    if out['auth_failure']:out['engineering_clean']=False
    return out

def live_snapshot(row):
    paths=list((ROOT/'jobs'/row['job']).glob('*/agent/live'))
    if len(paths)!=1:return {}
    p=paths[0];state=read(p/('wire-state.json' if row['arm']=='native-kz' else 'shared-state.json'))
    return {k:state.get(k) for k in ('requests','tools','updated_utc','time','http_status_counts') if k in state}

def supervise():
    validate()
    with (ROOT/'supervisor.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (ROOT/'admissions.json').exists():raise RuntimeError('Explicit reconciliation required before restart; no implicit replay')
        sys.path.append(str(BASE));import network_proxy
        proxy=network_proxy.ThreadingHTTPServer((network_proxy.HOST,PORT),network_proxy.Handler)
        threading.Thread(target=proxy.serve_forever,daemon=True).start()
        rows=initial_rows([t['name'] for t in read(ROOT/'tasks.json')['tasks']],read(ROOT/'history.json'))
        active={};retry_built=False;auth_pause=False
        def checkpoint(state):
            h=dict(state=state,updated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),pid=os.getpid(),
                phase='retry' if retry_built else 'first',summary=summary(rows),rows=rows,
                active=[dict(job=v['row']['job'],pid=v['process'].pid,offline=v['offline']) for v in active.values()])
            durable('admissions.json',h);durable('health.json',h)
        checkpoint('starting')
        try:
            while True:
                for job,entry in list(active.items()):
                    row=entry['row'];process=entry['process']
                    if process.poll() is None:
                        try:row['live']=live_snapshot(row)
                        except (OSError,ValueError):pass
                        continue
                    entry['log'].close();del active[job]
                    try:
                        result=trial(row,entry['offline']);result['harbor_exit']=process.returncode
                        if process.returncode!=0:result['engineering_clean']=False
                        if entry['offline']:
                            row['preflight']=result
                            if result['engineering_clean']:row.update(state='pending',preflight_ok=True)
                            else:finish(row,dict(**result,reason='preflight_failed',paid_calls=0))
                        else:
                            finish(row,result);auth_pause=auth_pause or result.get('auth_failure',False)
                    except Exception as e:
                        finish(row,dict(engineering_clean=False,reason='result_collection_error',error_type=type(e).__name__))
                    checkpoint('running')
                if not retry_built and first_finished(rows) and not active:
                    append_retry_batch(rows);retry_built=True
                    durable('retry-batch.json',dict(rows=[r.copy() for r in rows if r['stage']=='retry']))
                    checkpoint('running')
                if retry_built and not active and all(r['state'] in TERMINAL for r in rows):
                    durable('unresolved.json',dict(rows=[r for r in rows if r['stage']=='retry' and not r.get('engineering_clean')]))
                    checkpoint('finished');break
                held_disk=False
                for row in candidates(rows,{v['row']['arm'] for v in active.values()}):
                    if auth_pause:break
                    if any(v['row']['arm']==row['arm'] for v in active.values()):continue
                    try:
                        if not space_ready(row['task'],active):held_disk=True;continue
                        offline=not row.get('preflight_ok')
                        # Commit intent BEFORE process creation. Never silently repeat a paid admission.
                        row.update(state='preflight_admitted' if offline else 'paid_admitted',admitted_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
                        checkpoint('running')
                        env=dict(os.environ,PYTHONPATH=str(ROOT)+':'+str(BASE),PYTHONDONTWRITEBYTECODE='1',
                            PAIRED_TASK=row['task'],PAIRED_PROXY_URL=f'http://10.123.0.1:{PORT}')
                        if offline:env.pop('TAOTOKEN_API_KEY',None)
                        log=(ROOT/(('preflight-' if offline else '')+row['job']+'.log')).open('xb')
                        try:p=subprocess.Popen(command(row,offline),env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
                        except Exception:log.close();raise
                        active[row['job']]=dict(process=p,log=log,row=row,offline=offline)
                        row.update(state='preflighting' if offline else 'running',pid=p.pid)
                    except Exception as e:
                        finish(row,dict(engineering_clean=False,reason='dispatch_error',error_type=type(e).__name__))
                    checkpoint('running')
                checkpoint('held_authentication' if auth_pause else 'held_low_disk' if held_disk and not active else 'running')
                time.sleep(10)
        finally:
            # Unexpected supervisor termination must not break an already admitted solver's proxy.
            for v in active.values():v['process'].wait();v['log'].close()
            proxy.shutdown()

def precheck():
    validate()
    if (ROOT/'launch-once.marker').exists():raise RuntimeError('Already launched')
    p=subprocess.run(['docker','info','--format','{{.DockerRootDir}}'],capture_output=True,text=True,timeout=20)
    if p.returncode or p.stdout.strip()!='/var/lib/docker':raise RuntimeError('Docker unavailable or root changed')
    print('READY',flush=True)

def launch():
    precheck();bundle=json.loads(sys.stdin.readline());key=bundle.pop('key')
    if not isinstance(key,str) or not key.strip():raise ValueError('Fresh key required')
    with (ROOT/'launch-once.marker').open('x') as f:f.write(str(time.time()))
    with (ROOT/'supervisor.log').open('xb') as log:
        p=subprocess.Popen([PY,__file__,'--supervise'],env=dict(os.environ,TAOTOKEN_API_KEY=key,PYTHONDONTWRITEBYTECODE='1'),
            stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
    time.sleep(2)
    if p.poll() is not None:raise RuntimeError('Supervisor failed before acknowledgement; inspect before retry')
    print(json.dumps(dict(pid=p.pid,detached=True,kz_tasks=30,dsh_tasks=30,retry_batches=1,per_arm_concurrency=1)))

if __name__=='__main__':
    if '--supervise' in sys.argv:supervise()
    elif '--launch' in sys.argv:launch()
    else:precheck()
