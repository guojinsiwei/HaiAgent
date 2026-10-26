"""Fault-isolated paired scheduler. No paid retries, no automatic task budget.

Durable admission precedes Popen: an uncertain launch is NEVER silently repeated.
Only unpaid preflights retry (two total attempts). A failed task remains in the
denominator as blocked, rather than becoming a zero score or stopping other tasks.
"""
import collections,datetime,hashlib,json,os,signal,subprocess,sys,threading,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
PYTHON='/var/tmp/lizh639-tb4-taotoken-smoke-20261011/venv/bin/python'
PREFLIGHT_ATTEMPTS=2
TOTAL_CAP=4
ARM_CAP=2
PREFLIGHT_CAP=2

def read(path):
    try:return json.loads(path.read_text())
    except (OSError,ValueError):return {}

def save(name,value):
    path=ROOT/name;path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp');temp.write_text(json.dumps(value,indent=2));temp.replace(path)

def validate():
    ready=read(ROOT/'ready.json')
    if not ready.get('passed') or not ready.get('files'):raise RuntimeError('Offline acceptance not ready; launch denied')
    for name,expected in ready['files'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=expected:raise RuntimeError('Sealed deployment drift: '+name)
    return ready

def command(arm,task,job):
    return [PYTHON,str(ROOT/'unlimited_harbor.py'),'run','-p',str(ROOT/'official/tasks'/task),
      '-a','harbor_pair:'+('KZAgent' if arm=='kz' else 'PairAgent'),'--env','docker','--no-delete',
      '-n','1','-k','1','-r','0','--verifier-timeout-multiplier','1','--job-name',job,'-o',str(ROOT/'jobs')]

def preflight_command(task,attempt):
    job=f'preflight-{task}-a{attempt}'
    return [PYTHON,str(ROOT/'unlimited_harbor.py'),'run','-p',str(ROOT/'official/tasks'/task),
      '-a','harbor_pair:OfflineAgent','--env','docker','--no-delete','-n','1','-k','1','-r','0',
      '--job-name',job,'-o',str(ROOT/'task-preflight')]

def finish_preflight(task,attempt,code):
    found=list((ROOT/'task-preflight'/f'preflight-{task}-a{attempt}').glob('*/result.json'))
    result=read(found[0]) if len(found)==1 else {}
    passed=code==0 and bool(result.get('verifier_result')) and not result.get('exception_info')
    receipt=dict(passed=passed,paid_calls=0,attempt=attempt,exit_code=code,
                 trial=str(found[0]) if len(found)==1 else None,
                 exception=(result.get('exception_info') or {}).get('exception_type') or (None if passed else 'missing_or_invalid_preflight_result'))
    save(f'task-acceptance/{task}-a{attempt}.json',receipt)
    return receipt

def snapshot(row):
    record=dict(row)
    trials=[p for p in (ROOT/'jobs'/row['job']).glob('*') if p.is_dir() and (p/'config.json').exists()]
    if len(trials)!=1:return record
    trial=trials[0];logs=trial/'agent/live';usage=read(logs/'shared-state.json')
    exit_info=read(logs/'agent-exit.json');transport=read(trial/'agent/transport-result.json');result=read(trial/'result.json')
    record.update(trial=str(trial),requests=usage.get('requests',0),tools=usage.get('tools',0),
                  usage=usage,budget_stop=usage.get('stopped'),last_progress=usage.get('updated_utc'))
    if usage:record['state']='running'
    code=exit_info.get('exit_code',transport.get('agent_return_code'))
    if code is not None:record.update(solver_exit=code,state='grading',signal=exit_info.get('signal'))
    if result:
        record['grade']=result.get('verifier_result');record['exception']=(result.get('exception_info') or {}).get('exception_type')
        record['state']='graded' if record['grade'] and not record['exception'] else 'engineering_failure'
        if code!=0:record['fault']='solver_exit_'+str(code if code is not None else 'missing')
        record['valid_solver_completion']=code==0 and not record['exception']
    # Route audit contains only status/shape, never API key or prompt. Stream it:
    # do not load a potentially unbounded log into scheduler RAM every tick.
    statuses=collections.Counter()
    try:
        with (logs/'route.jsonl').open() as stream:
            for line in stream:
                try:item=json.loads(line)
                except ValueError:continue
                if item.get('event')=='response':statuses[str(item.get('status'))]+=1
    except OSError:pass
    record['http_status_counts']=dict(statuses)
    if statuses['401']:record['auth_failure']='401'
    elif statuses['403'] and not statuses['200']:record['auth_failure']='403'
    try:
        stamp=datetime.datetime.fromisoformat(record['last_progress']).timestamp()
        if time.time()-stamp>600 and record['state']=='running':record['warning']='no_new_accounting_event_over_10m; inspect active command/request, not proof of deadlock'
    except (KeyError,TypeError,ValueError):pass
    return record

class Schedule:
    def __init__(self,tasks):
        if not tasks or len(set(tasks))!=len(tasks):raise ValueError('Tasks must be nonempty and unique')
        self.rows=[];self.tasks={name:dict(state='pending',attempts=0) for name in tasks}
        self.pause_reason=None
        for index,task in enumerate(tasks):
            for arm in (['kz','dsh'] if index%2==0 else ['dsh','kz']):
                self.rows.append(dict(task=task,arm=arm,job=f'{index+1:02d}-{arm}-{task}',state='pending'))
    def preflight_candidates(self):
        if self.pause_reason:return []
        # First attempts across distinct tasks before retrying a failed task.
        available=[(v['attempts'],k) for k,v in self.tasks.items() if v['state']=='pending']
        return [k for _,k in sorted(available,key=lambda pair:pair[0])]
    def begin_preflight(self,task):
        value=self.tasks[task];value['attempts']+=1;value['state']='preflighting';return value['attempts']
    def end_preflight(self,task,receipt):
        value=self.tasks[task];value['receipt']=receipt
        if receipt['passed']:value['state']='ready'
        elif value['attempts']<PREFLIGHT_ATTEMPTS:value['state']='pending'
        else:
            value['state']='blocked'
            for row in self.rows:
                if row['task']==task and row['state']=='pending':row.update(state='blocked_environment',exception=receipt['exception'],paid_calls=0)
    def eligible(self,active):
        if self.pause_reason or len(active)>=TOTAL_CAP:return None
        counts=collections.Counter(row['arm'] for row in active)
        for row in self.rows:
            if row['state']=='pending' and self.tasks[row['task']]['state']=='ready' and counts[row['arm']]<ARM_CAP:return row
        return None
    def observe_global(self,rows):
        # A generic exit 1/137, invalid JSON or repeated task build failure is NOT
        # evidence of a shared outage. No cumulative generic-error circuit breaker.
        if any(row.get('auth_failure')=='401' for row in rows):self.pause_reason='confirmed_provider_401'
        elif len({r['task'] for r in rows if r.get('auth_failure')=='403'})>=2:self.pause_reason='provider_403_across_distinct_tasks'
    def health(self,running,preflights):
        terminal=[r for r in self.rows if r['state'] in ('graded','engineering_failure','blocked_environment','launch_error')]
        graded=[r for r in terminal if r.get('grade') is not None]
        pending=sum(r['state']=='pending' for r in self.rows)
        state='draining_shared_fault' if self.pause_reason and (running or preflights) else 'needs_attention' if self.pause_reason else 'running'
        if not running and not preflights and len(terminal)==len(self.rows):
            state='complete_with_failures' if any(r['state']!='graded' or r.get('fault') for r in terminal) else 'complete'
        return dict(state=state,updated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
          supervisor_pid=os.getpid(),planned=len(self.rows),finished=len(graded),resolved=len(terminal),
          blocked=sum(r['state']=='blocked_environment' for r in terminal),pending=pending,running=running,
          preflights=preflights,pause_reason=self.pause_reason,concurrency_cap=TOTAL_CAP,per_arm_cap=ARM_CAP,budget_mode='unlimited')

def supervise():
    import fcntl
    from network_proxy import server,HOST,PORT
    validate();os.chdir(ROOT)
    with (ROOT/'supervisor.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (ROOT/'admissions.json').exists():raise RuntimeError('Existing admissions require reconciliation; no blind paid replay')
        schedule=Schedule([r['name'] for r in read(ROOT/'tasks.json')['tasks']]);active={};preflights={}
        proxy=server();threading.Thread(target=proxy.serve_forever,daemon=True).start()
        env=dict(os.environ,PYTHONPATH=str(ROOT),PAIRED_PROXY_URL=f'http://{HOST}:{PORT}')
        def checkpoint():save('admissions.json',dict(rows=schedule.rows,tasks=schedule.tasks,pause_reason=schedule.pause_reason))
        def start(args,log_name,child_env):
            log=(ROOT/log_name).open('xb',buffering=0)
            try:return subprocess.Popen(args,cwd=ROOT,env=child_env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True),log
            except Exception:log.close();raise
        try:
            while True:
                for task,(p,log,attempt) in list(preflights.items()):
                    if p.poll() is not None:
                        log.close();del preflights[task]
                        schedule.end_preflight(task,finish_preflight(task,attempt,p.returncode));checkpoint()
                for job,(p,log,row) in list(active.items()):
                    if p.poll() is not None:
                        log.close();del active[job];final=snapshot(row);final['harbor_exit']=p.returncode
                        if final['state'] not in ('graded','engineering_failure'):final.update(state='engineering_failure',exception='missing_result')
                        row.update(final);checkpoint()
                running=[snapshot(row) for _,_,row in active.values()]
                schedule.observe_global(schedule.rows+running)
                # Inspect only a small number of upcoming environments; never
                # let a slow first preflight block dispatch of ready later tasks.
                for task in schedule.preflight_candidates():
                    if len(preflights)>=PREFLIGHT_CAP:break
                    if len({r['task'] for r in schedule.rows if r['state']=='pending' and schedule.tasks[r['task']]['state']=='ready'})>=4:break
                    attempt=schedule.begin_preflight(task);checkpoint()
                    probe_env={k:v for k,v in env.items() if k not in ('TAOTOKEN_API_KEY','DEEPSEEK_API_KEY','ANTHROPIC_API_KEY','ANTHROPIC_AUTH_TOKEN')}
                    try:
                        p,log=start(preflight_command(task,attempt),f'preflight-{task}-a{attempt}.log',dict(probe_env,PAIRED_TASK=task))
                        preflights[task]=(p,log,attempt)
                    except OSError:
                        schedule.end_preflight(task,dict(passed=False,exception='preflight_spawn_error',paid_calls=0));checkpoint()
                while row:=schedule.eligible([r for _,_,r in active.values()]):
                    row.update(state='admitted',started=time.time());checkpoint()
                    try:
                        p,log=start(command(row['arm'],row['task'],row['job']),row['job']+'.supervisor.log',dict(env,PAIRED_TASK=row['task']))
                        row.update(state='starting',pid=p.pid);active[row['job']]=(p,log,row)
                    except OSError:row.update(state='launch_error',exception='spawn_error_no_auto_retry')
                    checkpoint()
                running=[snapshot(row) for _,_,row in active.values()]
                health=schedule.health(running,[dict(task=t,attempt=v[2],pid=v[0].pid) for t,v in preflights.items()])
                save('health.json',health);save('summary.json',dict(**health,results=schedule.rows))
                if health['state'] in ('complete','complete_with_failures','needs_attention'):break
                time.sleep(10)
        except BaseException:
            # Preserve admission ledger. Do not orphan active paid tasks by
            # killing their proxy when the status/dispatch loop itself fails.
            save('supervisor-error.json',dict(state='dispatch_failed_draining',active=list(active),type=sys.exc_info()[0].__name__))
            while active or preflights:
                for key,(p,log,row) in list(active.items()):
                    if p.poll() is not None:
                        log.close();del active[key];row.update(snapshot(row),harbor_exit=p.returncode)
                for key,(p,log,attempt) in list(preflights.items()):
                    if p.poll() is not None:
                        log.close();del preflights[key];schedule.end_preflight(key,finish_preflight(key,attempt,p.returncode))
                health=schedule.health([snapshot(r) for _,_,r in active.values()],list(preflights))
                health['state']='dispatch_failed_draining' if active or preflights else 'needs_attention'
                health['pause_reason']='supervisor_exception_reconciliation_required'
                save('health.json',health);save('summary.json',dict(**health,results=schedule.rows));checkpoint()
                time.sleep(10)
            raise
        finally:proxy.shutdown()

def launch():
    validate();bundle=json.loads(sys.stdin.readline(16384));key=bundle.get('key','')
    if not key or not key.isascii() or any(c.isspace() for c in key):raise RuntimeError('Invalid hidden key input')
    with (ROOT/'launch-once.marker').open('x') as stream:stream.write('No automatic paid replay; unlimited task budget\n')
    with (ROOT/'supervisor.log').open('xb',buffering=0) as log:
        child=subprocess.Popen([PYTHON,__file__,'--supervise'],env=dict(os.environ,TAOTOKEN_API_KEY=key,PYTHONPATH=str(ROOT)),stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
    for _ in range(60):
        health=read(ROOT/'health.json')
        if health.get('supervisor_pid')==child.pid:
            print(json.dumps(dict(started=True,pid=child.pid,planned=60,state=health['state'],budget_mode='unlimited',independent_of_local_pc=True)));return
        if child.poll() is not None:raise RuntimeError('Supervisor exited before heartbeat; launch not successful, inspect public supervisor log')
        time.sleep(.25)
    raise RuntimeError('Supervisor heartbeat not confirmed; do not blindly retry or assume successful launch')

if __name__=='__main__':
    if '--supervise' in sys.argv:supervise()
    elif '--launch' in sys.argv:launch()
    else:raise SystemExit('Explicit --launch required. No key collected or work started.')
