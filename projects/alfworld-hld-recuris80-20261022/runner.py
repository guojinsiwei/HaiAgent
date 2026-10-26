"""160 finite paired runs, private worlds, shared bounded ledger, no GPT jobs."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib,json,os,secrets,shutil,subprocess,sys,threading,time,urllib.request
from spending import Ledger,server_for
from net_helpers import Proxy,progress
from budget_classification import hld_monetary_stop

R=Path(__file__).resolve().parent
ARMS=('hld','recuris')
EXISTING=['tb2-hld-recuris39-20261021','tb2-hld-recuris39-repair4-20261021','tb2-hld-polyglot-repair5-20261021']


def read(p):
    try:return json.loads(Path(p).read_text())
    except FileNotFoundError:return {}


def save(p,value):
    p=Path(p);p.parent.mkdir(exist_ok=True,parents=True)
    tmp=p.with_name(p.name+'.'+secrets.token_hex(4)+'.tmp')
    tmp.write_text(json.dumps(value,indent=2,ensure_ascii=False));tmp.replace(p)


def docker(*args,check=True,timeout=180):
    p=subprocess.run(['docker',*map(str,args)],capture_output=True,text=True,timeout=timeout)
    if check and p.returncode:raise RuntimeError('Docker: '+p.stderr[-800:])
    return p


def world_args(row,d,net,name):
    return ['run','-d','--name',name,'--label','experiment='+R.name,'--network',net,'--network-alias','world',
      '--user',f'{os.getuid()}:{os.getgid()}','--cpus','1','--memory','2g','--pids-limit','128',
      '--cap-drop','ALL','--security-opt','no-new-privileges','-e','HOME=/tmp','-e','ALFWORLD_DATA=/data',
      '-v',str(R/'data')+':/data:ro','-v',str(R/'world-venv')+':/runtime-env:ro',
      '-v',str(R/'world_server.py')+':/world_server.py:ro','-v',str(d/'world')+':/results',
      read(R/'image.json')['image'],'/runtime-env/bin/python','-u','/world_server.py','/data/'+row['game'],'100']


def solver_args(d,net,name):
    mounts=[(d/'workspace','/app',False),(d/'audit','/audit',False),(d/'home','/home/agent',False),
      (R/'client.py','/opt/experiment/client.py',True),(R/'container-run.mjs','/opt/experiment/container-run.mjs',True)]
    for part in ['kz','node','kz-python','recuris-dsh','dsh-baselines']:
        mounts.append((R/'runtime'/part,'/opt/'+part,True))
    args=['create','-i','--name',name,'--label','experiment='+R.name,'--network',net,
      '--user',f'{os.getuid()}:{os.getgid()}','--cpus','2','--memory','6g','--pids-limit','256',
      '--cap-drop','ALL','--security-opt','no-new-privileges','-e','HOME=/home/agent',
      '-e','PATH=/opt/node/bin:/usr/local/bin:/usr/bin:/bin','-w','/app']
    for source,target,ro in mounts:
        args+=['--mount',f'type=bind,src={source},dst={target}'+(',readonly' if ro else '')]
    return args+[read(R/'image.json')['image'],'/opt/node/bin/node','/opt/experiment/container-run.mjs']


def get_world(name):
    info=json.loads(docker('inspect',name).stdout)[0]['NetworkSettings']['Networks']
    ip=next(iter(info.values()))['IPAddress']
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for _ in range(90):
        try:
            with opener.open('http://'+ip+':8080/health',timeout=2) as f:return json.load(f)
        except Exception:time.sleep(1)
    raise RuntimeError('World startup timed out')


def prompt(initial):
    return '''Complete the following ALFWorld household task through the persistent text environment.
INITIAL OBSERVATION:
'''+initial['observation']+'''

INTERFACE (identical for both methods):
python /opt/experiment/client.py --observe
python /opt/experiment/client.py "go to countertop 1"
Replace the quoted action with one valid ALFWorld command. Each command performs one
environment action. The response includes observation, available actions, official
won/done flags and action count. Objects keep their state across commands. Read the
actual feedback before deciding subsequent actions. Read-only --observe does not
consume an environment action. There are at most 100 environment actions.
For a public outcome check use:
python /opt/experiment/client.py --assert-won
That check exits successfully only when the environment reports won=true.
The environment automatically ends on success or the action limit. No reset is
available. Local files are notes/scripts; they do not change the simulated world.
Use the observation and action interface to explore and act. The private simulator,
task definitions, expert policies and grading internals are unavailable to you.
'''


def trial(row,arm,key,ledger):
    job=arm+'--'+row['id'];d=R/'jobs'/job;d.mkdir(parents=True,exist_ok=False)
    for part in ['workspace','audit','home','world']:(d/part).mkdir()
    token=secrets.token_hex(6);net='alf-net-'+token;world='alf-world-'+token;solver='alf-solver-'+token
    state=dict(job=job,task=row['id'],type=row['type'],arm=arm,state='preparing',started=time.time(),world=world,solver=solver)
    save(d/'health.json',state);proxy=None;bs=None;process=None
    try:
        docker('network','create','--internal','--label','experiment='+R.name,net)
        gateway=json.loads(docker('network','inspect',net).stdout)[0]['IPAM']['Config'][0]['Gateway']
        docker(*world_args(row,d,net,world));initial=get_world(world)
        assert not initial['won'] and initial['steps']==0
        instruction=prompt(initial);save(d/'initial-observation.json',initial)
        proxy=Proxy(gateway);budget_token=secrets.token_urlsafe(32)
        bs=server_for(ledger,budget_token,host=gateway,port=0)
        threading.Thread(target=bs.serve_forever,daemon=True).start()
        spending=dict(CAMPAIGN_BUDGET_REQUIRED='1',CAMPAIGN_BUDGET_URL=f'http://{gateway}:{bs.server_port}',
          CAMPAIGN_BUDGET_TOKEN=budget_token,CAMPAIGN_BUDGET_JOB=job,CAMPAIGN_BUDGET_ARM='dsh' if arm=='recuris' else 'kz')
        docker(*solver_args(d,net,solver))
        mounts=json.loads(docker('inspect',solver,'--format','{{json .Mounts}}').stdout)
        assert all(Path(m['Source']).resolve().is_relative_to(d.resolve()) for m in mounts if m['RW'])
        assert not any(Path(m['Source']).resolve().is_relative_to((R/'data').resolve()) for m in mounts)
        save(d/'isolation.json',dict(mounts=mounts,network_internal=True,hidden_task_data_mounted=False))
        with (d/'controller.log').open('xb') as log:
            process=subprocess.Popen(['docker','start','-ai',solver],stdin=subprocess.PIPE,stdout=log,stderr=log)
            process.stdin.write((json.dumps(dict(key=key,proxy=proxy.url,no_proxy=gateway+',world,localhost,127.0.0.1',
                spending=spending,arm=arm,instruction=instruction,attempt_id=job))+'\n').encode());process.stdin.close()
            started=time.monotonic();state['state']='solving'
            while process.poll() is None:
                environment=read(d/'world/state.json');state.update(updated=time.time(),environment_steps=environment.get('steps'),**progress(d))
                save(d/'health.json',state)
                if environment.get('done'):
                    state['stop_reason']='environment_success' if environment['won'] else 'environment_action_limit'
                    docker('stop','-t','5',solver,check=False);break
                if time.monotonic()-started>7260:
                    state['stop_reason']='wall_budget';docker('stop','-t','5',solver,check=False);break
                time.sleep(2)
            process.wait(timeout=40)
        final=read(d/'world/state.json');assert isinstance(final.get('won'),bool)
        state.update(exit_code=process.returncode,official_success=final['won'],environment_steps=final['steps'],**progress(d))
        if state.get('budget_exhausted') or hld_monetary_stop(d/'audit',arm,(d/'audit/agent-exit.json').exists(),process.returncode):
            state.setdefault('stop_reason','per_task_budget_exhausted')
        elif state.get('wall_stop'):state.setdefault('stop_reason','wall_budget')
        if process.returncode and not state.get('stop_reason'):
            state['engineering_fault']='solver_process_error'
        rec=read(d/'audit/recuris/state.json')
        if rec.get('faults'):state['engineering_fault']='recuris_degraded';state['algorithm_faults']=rec['faults']
        state['state']='engineering_failure' if state.get('engineering_fault') else 'done'
        save(d/'grade.json',dict(official_success=final['won'],source='TextWorld GameState.won',
            environment_steps=final['steps'],state_sha256=hashlib.sha256((d/'world/state.json').read_bytes()).hexdigest()))
    except Exception as error:
        state.update(state='engineering_failure',engineering_fault=type(error).__name__,error=str(error)[:800].replace(key,'[REDACTED]'))
    finally:
        for name in [solver,world]:
            owner=docker('inspect',name,'--format','{{index .Config.Labels "experiment"}}',check=False).stdout.strip()
            if owner==R.name:
                docker('stop','-t','3',name,check=False)
                logs=docker('logs',name,check=False);(d/(name.split('-')[1]+'-container.log')).write_text(logs.stdout+logs.stderr)
                docker('rm',name,check=False)
        if process and process.poll() is None:process.wait(timeout=40)
        if proxy:proxy.close()
        if bs:bs.shutdown();bs.server_close()
        docker('network','rm',net,check=False)
        state.update(ended=time.time(),updated=time.time());save(d/'summary.json',state);save(d/'health.json',state)
    return state


def available_slots(active):
    # Reserve every unfinished older task, including queued retries, against a
    # combined 12-solver ceiling. Other supervisors can refill without racing us.
    external=0
    for name in EXISTING:
        h=read(R.parent/name/'health.json')
        if not h:return 0
        external+=sum(r['state'] not in ('done','engineering_failure','historical','paused_by_user') for r in h['rows'])
    memory={line.split(':')[0]:int(line.split()[1])*1024 for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:')}
    if memory['MemAvailable']<20*2**30 or shutil.disk_usage('/var/lib/docker').free<40*2**30 or shutil.disk_usage(R).free<8*2**30:return 0
    return max(0,min(12-active,12-external-active))


def campaign():
    assert read(R/'preflight-result.json')['passed'] and read(R/'integration-preflight.json')['passed']
    for name,digest in read(R/'source-lock.json').items():assert hashlib.sha256((R/name).read_bytes()).hexdigest()==digest,name
    secret=read(Path.home()/'.config/appworld-credentials/taotoken-standby.json')
    key=secret.get('key') or secret.get('api_key') or secret.get('apiKey');assert key
    ledger=Ledger(R/'spending.sqlite',read(R/'budget-profile.json'))
    rows=read(R/'manifest.json')['selected'];queue=[]
    for i,row in enumerate(rows):
        for arm in (ARMS if i%2==0 else ARMS[::-1]):queue.append((row,arm))
    results=[];active={}
    with (R/'launch-once.marker').open('x') as f:f.write(str(time.time()))
    with ThreadPoolExecutor(max_workers=12) as pool:
        while queue or active:
            for f in list(active):
                if f.done():
                    row,arm=active.pop(f)
                    try:results.append(f.result())
                    except Exception as e:results.append(dict(task=row['id'],arm=arm,state='engineering_failure',error=type(e).__name__))
            slots=available_slots(len(active));status=ledger.status()
            if status['halt_reason'] or status['remaining_microcny']<=0:
                results.extend(dict(task=r['id'],arm=a,state='not_run_budget') for r,a in queue);queue.clear()
            while queue and slots>0:
                row,arm=queue.pop(0);active[pool.submit(trial,row,arm,key,ledger)]=(row,arm);slots-=1
            summary={a:dict(total=80,completed=sum(x['arm']==a and x['state'] in ('done','engineering_failure') for x in results),
                passed=sum(x['arm']==a and x.get('official_success') is True for x in results),
                engineering_failures=sum(x['arm']==a and x['state']=='engineering_failure' for x in results),
                running=sum(arm==a for row,arm in active.values())) for a in ARMS}
            state=dict(state='running' if active else 'waiting_resources' if queue else 'finished',pid=os.getpid(),updated=time.time(),
              active=[dict(task=row['id'],arm=arm) for row,arm in active.values()],pending=len(queue),summary=summary,results=results,budget=ledger.status(),concurrency_cap=12)
            save(R/'health.json',state)
            if queue or active:time.sleep(5)
    save(R/'final-summary.json',state)


if __name__=='__main__':campaign()
