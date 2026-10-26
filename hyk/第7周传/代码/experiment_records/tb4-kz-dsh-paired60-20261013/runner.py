"""Detached paired supervisor. One paid attempt per arm/task; public status only.
Credentials pass stdin -> this process -> child environment -> container stdin.
No credentials are serialized to job configs, log files, or process arguments.
"""
import collections,datetime,hashlib,json,os,subprocess,sys,threading,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
PYTHON='/var/tmp/lizh639-tb4-taotoken-smoke-20261011/venv/bin/python'
HARBOR='/var/tmp/lizh639-tb4-taotoken-smoke-20261011/venv/bin/harbor'
def save(name,data):
    p=ROOT/name;t=p.with_suffix('.tmp');t.write_text(json.dumps(data,indent=2));t.replace(p)
def read(p):
    try:return json.loads(p.read_text())
    except (OSError,ValueError):return {}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def validate():
    ready=read(ROOT/'ready.json')
    if not ready.get('passed'):raise RuntimeError('Acceptance not ready; nothing launched')
    for n,h in ready['files'].items():
        if sha(ROOT/n)!=h:raise RuntimeError('Accepted deployment drift: '+n)
    return ready
def command(arm,task,job):
    return [HARBOR,'run','-p',str(ROOT/'official/tasks'/task),'-a','harbor_pair:'+('KZAgent' if arm=='kz' else 'PairAgent'),
      # Solver is killed at 7200s by container-run; outer 120s only permits
      # shutdown/log receipt, never additional model or tool budget.
      '--env','docker','--no-delete','-n','1','-k','1','-r','0','--agent-timeout-multiplier',str(7320/28800),
      '--verifier-timeout-multiplier','1','--job-name',job,'-o',str(ROOT/'jobs')]
def acceptance(task):
    receipt=read(ROOT/'task-acceptance'/f'{task}.json')
    return receipt.get('passed') is True
def preflight_command(task):
    return [HARBOR,'run','-p',str(ROOT/'official/tasks'/task),'-a','harbor_pair:OfflineAgent','--env','docker','--no-delete','-n','1','-k','1','-r','0','--job-name','preflight-'+task,'-o',str(ROOT/'task-preflight')]
def finish_preflight(task,code):
    found=list((ROOT/'task-preflight'/('preflight-'+task)).glob('*/result.json'))
    result=read(found[0]) if len(found)==1 else {}
    passed=code==0 and bool(result.get('verifier_result')) and not result.get('exception_info')
    (ROOT/'task-acceptance').mkdir(exist_ok=True)
    save('task-acceptance/'+task+'.json',dict(passed=passed,paid_calls=0,trial=str(found[0]) if found else None,exception=result.get('exception_info',{}).get('exception_type') if result.get('exception_info') else None))
    return passed
def snapshot(row):
    folder=ROOT/'jobs'/row['job'];trials=[p for p in folder.glob('*') if p.is_dir() and (p/'config.json').exists()]
    if len(trials)!=1:return dict(row)
    trial=trials[0];logs=trial/'agent/live';state=read(logs/'shared-state.json');exit=read(logs/'agent-exit.json');result=read(trial/'result.json')
    record=dict(row,trial=str(trial),requests=state.get('requests',0),tools=state.get('tools',0),budget_stop=state.get('stopped'),cost_upper_cny=state.get('cost',{}).get('spentUpperCny'))
    p=logs/'shared.jsonl'
    record['last_progress']=p.stat().st_mtime if p.exists() else None
    if exit:record['solver_exit']=exit.get('exit_code');record['state']='grading'
    if result:
        record['grade']=result.get('verifier_result');record['exception']=result.get('exception_info',{}).get('exception_type') if result.get('exception_info') else None
        record['state']='graded' if record['grade'] and record['exception'] in (None,'AgentTimeoutError') else 'engineering_failure'
        if record['exception']=='AgentTimeoutError':record['budget_stop']='wall';record['exception']=None
        if exit.get('exit_code',1)!=0 and not state.get('stopped'):record['fault']='solver_exit_'+str(exit.get('exit_code','missing'))
    route=logs/'route.jsonl'
    if route.exists():
        # Only public shape/status audit, never complete prompts or credentials.
        for line in route.read_text().splitlines():
            try:e=json.loads(line)
            except ValueError:continue
            if e.get('status') in (401,403):record['fault']='authentication_or_plan_rejection'
    return record
def supervise():
    from network_proxy import server,HOST,PORT
    validate();os.chdir(ROOT)
    proxy=server();threading.Thread(target=proxy.serve_forever,daemon=True).start()
    env=dict(os.environ,PYTHONPATH=str(ROOT),PAIRED_PROXY_URL=f'http://{HOST}:{PORT}')
    rows=[]
    for n,r in enumerate(read(ROOT/'tasks.json')['tasks']):
        for arm in (['kz','dsh'] if n%2==0 else ['dsh','kz']):rows.append(dict(arm=arm,task=r['name'],job=f'{n+1:02d}-{arm}-{r["name"]}',state='pending'))
    active={};finished=[];paused=None;faults=collections.Counter();preflight=None
    try:
        while True:
            if preflight and preflight[0].poll() is not None:
                p,log,task=preflight;log.close();preflight=None
                if not finish_preflight(task,p.returncode):paused='environment_or_verifier_preflight:'+task
            for job,(p,log,row) in list(active.items()):
                if p.poll() is not None:
                    log.close();del active[job];r=snapshot(row);r['harbor_exit']=p.returncode
                    if r['state'] not in ('graded','engineering_failure'):r['state']='engineering_failure';r['exception']='missing_result'
                    fault=r.get('exception') or r.get('fault')
                    if fault:
                        faults[fault]+=1
                        # Infrastructure failures fail closed; isolated model JSON
                        # exhaustion keeps its grade and does not discard other tasks.
                        if r['state']=='engineering_failure' or fault=='authentication_or_plan_rejection' or faults[fault]>=2:paused=str(fault)
                    finished.append(r)
            running=[snapshot(r) for _,_,r in active.values()]
            if any(r.get('fault')=='authentication_or_plan_rejection' for r in running):paused='authentication_or_plan_rejection'
            # First paired task is the pilot. Only then increase to 2 pairs (4 total).
            cap=2 if len(finished)<2 else 4
            while rows and len(active)<cap and not paused:
                task=rows[0]['task']
                if len(finished)<2 and task!=read(ROOT/'tasks.json')['tasks'][0]['name']:break
                if not acceptance(task):
                    if preflight is None:
                        log=(ROOT/('preflight-'+task+'.log')).open('xb',buffering=0)
                        # Each new task must prove install + official grading
                        # before either paid arm is admitted. No key in this child.
                        probe_env={k:v for k,v in env.items() if k!='TAOTOKEN_API_KEY'}
                        probe_env['PAIRED_TASK']=task
                        preflight=(subprocess.Popen(preflight_command(task),cwd=ROOT,env=probe_env,stdin=subprocess.DEVNULL,stdout=log,stderr=log),log,task)
                    break
                row=rows.pop(0);row['state']='starting';row['started']=time.time()
                log=(ROOT/(row['job']+'.supervisor.log')).open('xb',buffering=0)
                p=subprocess.Popen(command(row['arm'],row['task'],row['job']),cwd=ROOT,env=dict(env,PAIRED_TASK=row['task']),stdin=subprocess.DEVNULL,stdout=log,stderr=log)
                active[row['job']]=(p,log,row)
            state='needs_attention' if paused and not active and not preflight else 'complete' if not rows and not active and not preflight else 'draining_after_fault' if paused else 'running'
            health=dict(state=state,updated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),supervisor_pid=os.getpid(),planned=60,finished=len(finished),running=[snapshot(r) for _,_,r in active.values()],pending=len(rows),pause_reason=paused,concurrency_cap=cap,unpaid_environment_preflight=preflight[2] if preflight else None)
            save('health.json',health);save('summary.json',dict(**health,results=finished))
            if state in ('complete','needs_attention'):break
            time.sleep(10)
    finally:proxy.shutdown()
def launch():
    validate();bundle=json.loads(sys.stdin.readline(16384));key=bundle.get('key','')
    if not key or not key.isascii() or any(c.isspace() for c in key):raise RuntimeError('Invalid key input')
    with (ROOT/'launch-once.marker').open('x') as out:out.write('60 paired trials, no automatic paid repeats\n')
    with (ROOT/'supervisor.log').open('xb',buffering=0) as log:
        child=subprocess.Popen([PYTHON,__file__,'--supervise'],env=dict(os.environ,TAOTOKEN_API_KEY=key,PYTHONPATH=str(ROOT)),stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
    print(json.dumps(dict(started=True,pid=child.pid,planned=60,independent_of_local_pc=True)))
if __name__=='__main__':
    if '--supervise' in sys.argv:supervise()
    else:launch()
