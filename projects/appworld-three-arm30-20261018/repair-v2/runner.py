"""Four arms, matched tasks, independent worlds and persistent bounded accounting."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib,json,os,secrets,shutil,subprocess,sys,threading,time,urllib.request
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from spending import Ledger,server_for
from repair_classification import classify
from runtime_helper import Proxy,progress
V=Path(__file__).resolve().parent
R=V.parent
TB=R.parent/'tb2-three-arm50-20261017'
GRADE_LOCK=threading.Lock()
def save(path,data):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(data,indent=2,ensure_ascii=False));tmp.replace(p)
def read(path):
    try:return json.loads(Path(path).read_text())
    except (FileNotFoundError,ValueError):return {}
def docker(*args,check=True,timeout=180):
    p=subprocess.run(['docker',*map(str,args)],capture_output=True,text=True,timeout=timeout)
    if check and p.returncode:raise RuntimeError(p.stderr[-1000:])
    return p
def instruction(row):
    return (row['instruction']+'\n\n'+
      'You operate a simulated AppWorld task. Current date/time: '+row['datetime']+'.\n'+
      'Task supervisor (synthetic benchmark identity): '+json.dumps(row['supervisor'])+'.\n'+
      'Read API_GUIDE.md for the execution interface and api_docs/ for public API documentation. '
      'Use Python cells through python /opt/experiment/client.py to interact with the apps; variables persist across cells. '
      'Only app API operations change the task world. Workspace files alone do not complete the task. '
      'Use the documented supervisor complete_task API to submit exactly once, after public read-back. Information requests require an answer; operation-only tasks omit answer. Submission seals application mutations. '
      'Verify outcomes using ordinary public APIs. Hidden grading feedback is unavailable. No external internet access is required.\n'+POLICY)
POLICY='\nPUBLIC APPWORLD EXECUTION RULES\nUse collect_pages(apis.APP.API, ...) to explicitly exhaust list APIs; it checks for an empty page and refuses incomplete/repeated pagination. Inspect public API parameters first. The helper defaults to page_limit=5. Do not pass a default first page off as ALL records.\nBefore a bulk mutation, enumerate the complete candidate set, then select by every public constraint: identity/relationship, time window and semantic description. Yesterday evening is narrower than yesterday; inspect the timestamps and descriptions. Save the original selected records before deletion, retaining all fields to preserve.\nKeep writes within the public task. Verify by reading actual results; never send probe messages/payments or export/email artifacts to prove an API path. Deleting a probe may leave global records.\nFor payment tasks prefer a valid payment card directly. Do not top up a balance or create cross-app payments as a verification step. Any prerequisite writes must be necessary for the public task.\nPrepare API assertion scripts in the workspace and execute them inside AppWorld using: python /opt/experiment/client.py --read-only --file /app/check.py\nThe --file interface executes the script inside the persistent AppWorld interpreter where apis and collect_pages exist. Ordinary local Python does not have apis. Assertions produce a nonzero exit on failure.\nUse client.py --read-only for observation and verification. After complete_task, application writes are blocked; continue only read-only verification if needed. Do not create documentation/probe subgoals after completing the requested operation.\n'
GUIDE='''# AppWorld execution interface
Run Python in the persistent AppWorld interpreter using native bash:

python /opt/experiment/client.py <<'PY'
print(apis.api_docs.show_app_descriptions())
PY

Discover one application's APIs:
print(apis.api_docs.show_api_descriptions(app_name="supervisor"))
Read one API's documented arguments and response:
print(apis.api_docs.show_api_doc(app_name="supervisor", api_name="show_account_passwords"))

The public API docs are also available under api_docs/. Use their exact API names and parameters.
Python variables persist between successful cells. print values you want to inspect.
Task date/time and supervisor identity are in INSTRUCTION.md.
Use the supervisor API to obtain synthetic task account credentials when necessary.
The workspace is for your notes and scripts. Its filesystem is separate from the AppWorld interpreter.
All actual app operations must pass through the client. Local mock data or local state changes cannot satisfy the task.
Execution failures produce a nonzero client exit. A command exiting successfully only shows it ran; verify the desired app state separately.
Do not look for or infer hidden grading code. The grader runs only after your solver has stopped.
'''
def world_args(row,d,net,name,image):
    return ['run','-d','--name',name,'--label','experiment='+R.name,'--network',net,'--network-alias','world',
        '--user',f'{os.getuid()}:{os.getgid()}','--cpus','1','--memory','4g','--pids-limit','128','--cap-drop','ALL','--security-opt','no-new-privileges',
        '-e','HOME=/tmp','-v',str(R/'public-data')+':/appworld/data:ro','-v',str(d/'world')+':/appworld/experiments',
        '-v',str(V/'appworld_guard.py')+':/appworld_guard.py:ro','-v',str(V/'world_server.py')+':/world_server.py:ro',image,'python','-u','/world_server.py',row['task']]
def solver_args(d,net,name,arm,image):
    mounts=[(d/'workspace','/app',False),(d/'home','/dsh-home',False),(d/'audit','/audit',False),
      (V/'runtime'/arm,'/opt/kz',True),(TB/'runtime/kz/node_modules','/opt/kz/node_modules',True),
      (TB/'runtime/node','/opt/node',True),(V/'client.py','/opt/experiment/client.py',True),
      (V/'container-run.mjs','/opt/experiment/container-run.mjs',True),
      (R/'public-data/api_docs','/app/api_docs',True)]
    if arm=='recuris':
        for part in ['recuris-dsh','dsh-baselines']:
            mounts.extend([(R/'runtime'/part,'/opt/'+part,True),(TB/'runtime/kz/node_modules','/opt/'+part+'/node_modules',True)])
    args=['create','-i','--name',name,'--label','experiment='+R.name,'--network',net,
      '--user',f'{os.getuid()}:{os.getgid()}','--cpus','2','--memory','8g','--pids-limit','256','--cap-drop','ALL','--security-opt','no-new-privileges',
      '-e','HOME=/dsh-home','-e','PATH=/opt/node/bin:/opt/recuris/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin','-w','/app']
    for source,target,ro in mounts:args+=['--mount',f'type=bind,src={source},dst={target}'+(',readonly' if ro else '')]
    return args+[image,'/opt/node/bin/node','/opt/experiment/container-run.mjs']
def wait_world(name,seconds=90):
    ip=json.loads(docker('inspect',name).stdout)[0]['NetworkSettings']['Networks'];ip=next(iter(ip.values()))['IPAddress']
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}));end=time.monotonic()+seconds
    while time.monotonic()<end:
        try:
            with opener.open('http://'+ip+':8080/health',timeout=2) as f:return json.load(f)
        except Exception:time.sleep(1)
    raise RuntimeError('world startup timeout')
def grade(row,d,image):
    result_dir=d/'grade';result_dir.mkdir(exist_ok=True)
    name='aw-grade-'+secrets.token_hex(5)
    try:
        p=docker('run','--name',name,'--label','experiment='+R.name,'--network','none','--user',f'{os.getuid()}:{os.getgid()}',
          '--cpus','2','--memory','6g','-e','HOME=/tmp','-v',str(R/'assets/data')+':/appworld/data:ro',
          '-v',str(d/'world')+':/appworld/experiments','-v',str(result_dir)+':/result',
          '-v',str(R/'grade.py')+':/grade_task.py:ro',image,'python','/grade_task.py',row['task'],check=False,timeout=300)
        (result_dir/'stdout.log').write_text(p.stdout);(result_dir/'stderr.log').write_text(p.stderr)
        if p.returncode:raise RuntimeError('Official grader failed; saved world can be regraded without solver')
        result=read(result_dir/'result.json')
        assert isinstance(result.get('success'),bool) and result.get('total_count',0)>0
        return result
    finally:
        if docker('inspect',name,check=False).returncode==0:docker('rm','-f',name,check=False)
def trial(row,key,arm,ledger):
    job=row.get('_job',arm+'--'+row['task']);d=R/'jobs'/job;d.mkdir(parents=True,exist_ok=False)
    save(d/'repair-version.json',{'version':2,'attempt':row.get('_attempt',1),'rerun_of':row.get('_rerun_of')})
    for part in ['workspace','home','audit','world']:(d/part).mkdir()
    prompt=instruction(row);(d/'workspace/INSTRUCTION.md').write_text(prompt);(d/'workspace/API_GUIDE.md').write_text(GUIDE+POLICY)
    token=secrets.token_hex(5);net='aw-net-'+token;world='aw-world-'+token;solver='aw-solver-'+token
    image=read(R/'image.json')['image'];proxy=None;bs=None;p=None
    s=dict(job=job,arm=arm,task=row['task'],scenario=row['scenario'],state='preparing',started=time.time(),world=world,solver=solver,repair_version=2,attempt=row.get('_attempt',1),rerun_of=row.get('_rerun_of'))
    save(d/'health.json',s)
    try:
        docker('network','create','--internal','--label','experiment='+R.name,net)
        gateway=json.loads(docker('network','inspect',net).stdout)[0]['IPAM']['Config'][0]['Gateway']
        docker(*world_args(row,d,net,world,image));ready=wait_world(world);assert ready['task']==row['task'] and not ready['ground_truth_loaded']
        proxy=Proxy(gateway);budget_token=secrets.token_urlsafe(32)
        bs=server_for(ledger,budget_token,host=gateway,port=0);threading.Thread(target=bs.serve_forever,daemon=True).start()
        spending={'CAMPAIGN_BUDGET_REQUIRED':'1','CAMPAIGN_BUDGET_URL':f'http://{gateway}:{bs.server_port}',
          'CAMPAIGN_BUDGET_TOKEN':budget_token,'CAMPAIGN_BUDGET_JOB':job,'CAMPAIGN_BUDGET_ARM':'dsh' if arm=='dsh' else 'kz'}
        docker(*solver_args(d,net,solver,arm,image))
        actual=json.loads(docker('inspect',solver,'--format','{{json .Mounts}}').stdout)
        assert all(Path(m['Source']).resolve().is_relative_to(d.resolve()) for m in actual if m['RW'])
        save(d/'isolation.json',{'solver_mounts':actual,'world_ready':ready,'network_internal':True,'image':image})
        with (d/'controller.log').open('xb') as log:
            p=subprocess.Popen(['docker','start','-ai',solver],stdin=subprocess.PIPE,stdout=log,stderr=log)
            p.stdin.write((json.dumps({'key':key,'proxy':proxy.url,'no_proxy':gateway+',localhost,127.0.0.1','spending':spending,'arm':arm,'instruction':prompt})+'\n').encode());p.stdin.close()
            s['state']='solving';started=time.monotonic()
            while p.poll() is None:
                s.update(updated=time.time(),**progress(d));save(d/'health.json',s)
                if any(x in (400,401,403,404) for x in s['http_errors']):
                    s['engineering_fault']='provider_request_rejected';docker('stop','-t','3',solver,check=False);break
                if time.monotonic()-started>7260:
                    s['stop_reason']='wall_budget';docker('stop','-t','3',solver,check=False);break
                time.sleep(5)
            p.wait(timeout=30)
        docker('stop','-t','3',solver,check=False);docker('stop','-t','3',world,check=False)
        s.update(exit_code=p.returncode,**progress(d))
        if s.get('budget_exhausted'):s['stop_reason']=s.get('budget_reason')
        elif s.get('wall_stop'):s['stop_reason']='wall_budget'
        elif p.returncode==0:s['stop_reason']='native_completed'
        elif not s.get('stop_reason'):s['engineering_fault']=s.get('engineering_fault','solver_process_error')
        if s.get('provider_stop') and not s.get('budget_exhausted'):s['engineering_fault']='provider_transport_or_http'
        s=classify(s,d)
        rec=read(d/'audit/recuris/state.json')
        if rec.get('faults'):s['algorithm_faults']=rec['faults'];s.setdefault('engineering_fault','recuris_degraded')
        # Every world.execute persists DBs and logs; hash the saved final DB snapshot before grading.
        files={str(f.relative_to(d/'world')):hashlib.sha256(f.read_bytes()).hexdigest() for f in (d/'world').rglob('*') if f.is_file()}
        assert files,'Missing final world snapshot';save(d/'world-manifest.json',files)
        s['state']='grading';save(d/'health.json',s)
        with GRADE_LOCK:result=grade(row,d,image)
        s.update(official_success=result['success'],passed_tests=result['pass_count'],total_tests=result['total_count'],grading='complete')
        s['state']='needs_attention' if s.get('engineering_fault') else 'graded'
    except Exception as e:
        s.update(state='needs_attention',engineering_fault=type(e).__name__,error=str(e)[:1000].replace(key,'[REDACTED]'))
    finally:
        for name in [solver,world]:
            if docker('inspect',name,check=False).returncode==0:
                owner=docker('inspect',name,'--format','{{index .Config.Labels "experiment"}}').stdout.strip()
                if owner==R.name:
                    logs=docker('logs',name,check=False);(d/(name.split('-')[1]+'-container.log')).write_text(logs.stdout+logs.stderr)
                    docker('rm','-f',name,check=False)
        if p and p.poll() is None:p.wait(timeout=30)
        if proxy:proxy.close()
        if bs:bs.shutdown();bs.server_close()
        docker('network','rm',net,check=False)
        s.update(ended=time.time(),updated=time.time());save(d/'summary.json',s);save(d/'health.json',s)
    return s
def validate():
    ready=read(V/'ready.json');assert ready.get('passed'),'Repair acceptance required'
    for name,value in ready['hashes'].items():assert hashlib.sha256((R/name).read_bytes()).hexdigest()==value,name
    plan=read(V/'resume-plan.json');assert plan['campaign_limit_cny']==720 and plan['attempt_limit_cny']==8
    return plan

def campaign(key):
    plan=validate();ledger=Ledger(R/'spending.sqlite',read(R/'budget-profile.json'))
    ledger.reconcile_restart()
    queue=[(item['row'],item['arm']) for item in plan['queue']]
    complete=plan['previous_completed'];active={}
    with ThreadPoolExecutor(max_workers=6) as pool:
        while queue or active:
            for future in list(active):
                if future.done():
                    row,arm=active.pop(future)
                    try:complete.append(future.result())
                    except Exception as e:complete.append({'task':row['task'],'arm':arm,'state':'needs_attention','engineering_fault':type(e).__name__})
            budget=ledger.status()
            if budget['halt_reason'] or budget['remaining_microcny']<387072 and not active:
                complete.extend({'task':r['task'],'arm':a,'state':'not_run_budget'} for r,a in queue);queue=[]
            while queue and len(active)<6 and not budget['halt_reason'] and shutil.disk_usage('/var/lib/docker').free>30*2**30 and shutil.disk_usage(R).free>15*2**30:
                row,arm=queue.pop(0);active[pool.submit(trial,row,key,arm,ledger)]=(row,arm)
            s={'state':'running' if active else 'waiting_for_storage' if queue else 'complete','updated':time.time(),'pid':os.getpid(),
               'concurrency':len(active),'completed':complete,'active':[{'task':r['task'],'arm':a,'job':r.get('_job',a+'--'+r['task'])} for r,a in active.values()],
               'pending':[{'task':r['task'],'arm':a,'job':r.get('_job',a+'--'+r['task'])} for r,a in queue],'budget':ledger.status()}
            save(V/'health.json',s)
            if queue or active:time.sleep(5)
    s['state']='complete_with_engineering_failures' if any(r['state']=='needs_attention' for r in complete) else 'complete';save(V/'summary.json',s);save(V/'health.json',s)
if __name__=='__main__':
    if '--supervise' in sys.argv:campaign(json.loads(sys.stdin.readline(16384))['key'])
    elif '--launch' in sys.argv:
        validate();key=json.loads(sys.stdin.readline(16384))['key'];assert key and key.isascii() and not any(c.isspace() for c in key)
        (V/'launch-once.marker').open('x').write('Authorized budget repair and selective retries; cumulative campaign ledger retained.\n')
        with (V/'supervisor.log').open('ab',buffering=0) as log:
            p=subprocess.Popen([sys.executable,__file__,'--supervise'],stdin=subprocess.PIPE,stdout=log,stderr=log,start_new_session=True)
            p.stdin.write((json.dumps({'key':key})+'\n').encode());p.stdin.close()
        key='';time.sleep(2);assert p.poll() is None
        print(json.dumps({'started':True,'pid':p.pid,'queued_attempts':len(read(V/'resume-plan.json')['queue']),'workers':6,'campaign_cny':720,'repair_version':2}))
    else:validate();print('READY_NO_MODEL_CALLS')
