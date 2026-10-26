"""Isolated paired attempts; stop all paid admission on the first official pass."""
import datetime, fcntl, hashlib, json, os, shutil, subprocess, sys, threading, time, urllib.request
from pathlib import Path
from policy import summarize, passed
from spending import BudgetService
import network_proxy

ROOT=Path(__file__).resolve().parent
TASK_ROOT=Path('/var/tmp/lizh639-tb4-kz-dsh-unlimited-repair-20261014/official/tasks')
RUNTIME=Path('/var/tmp/lizh639-tb4-kz-dsh-ec10-20261014')
PY='/var/tmp/lizh639-tb4-taotoken-smoke-20261011/venv/bin/python'
PORT=28494

def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def read(path):
    try:return json.loads(Path(path).read_text())
    except (FileNotFoundError,ValueError):return {}
def save(name, value):
    target=ROOT/name; temp=target.with_suffix(target.suffix+'.tmp')
    with temp.open('w') as stream:
        json.dump(value,stream,indent=2);stream.flush();os.fsync(stream.fileno())
    temp.replace(target)

def validate():
    ready=read(ROOT/'ready.json')
    if not ready.get('passed'):raise RuntimeError('Offline acceptance is required')
    for name,digest in ready['files'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:raise RuntimeError('Source drift: '+name)
    if hashlib.sha256((RUNTIME/'runtime-final.tar.gz').read_bytes()).hexdigest()!=ready['runtime_sha256']:
        raise RuntimeError('Frozen runtime changed')
    for name,digest in ready['official_files'].items():
        if hashlib.sha256((TASK_ROOT/name).read_bytes()).hexdigest()!=digest:raise RuntimeError('Official task drift: '+name)
    if read(ROOT/'budget-profile.json')['campaign_limit_fen']!=3000:raise RuntimeError('Expected shared 30 yuan ceiling')

def command(row, offline=False):
    agent=('OfflineKZDSH' if offline else 'KZDSH') if row['arm']=='kz' else ('OfflineDSH' if offline else 'DSH')
    return [PY,str(ROOT/'entry_harbor.py'),'run','-p',str(TASK_ROOT/row['task']),'-a','agents:'+agent,
            '--env','docker','--no-delete','-n','1','-k','1','-r','0','--verifier-timeout-multiplier','1',
            '--job-name',('preflight-' if offline else '')+row['job'],'-o',str(ROOT/('preflight' if offline else 'jobs'))]+(['--disable-verification'] if offline else [])

def collect(row,offline=False):
    job=('preflight-' if offline else '')+row['job']
    results=list((ROOT/('preflight' if offline else 'jobs')/job).glob('*/result.json'))
    if len(results)!=1:return dict(passed=False,exception_type='MissingUniqueResult')
    result=read(results[0]); info=summarize(result)
    info['trial']=str(results[0].parent)
    info['official_result']=str(results[0])
    metadata=(result.get('agent_result') or {}).get('metadata') or {}
    if offline:info['install_ok']=metadata.get('install_ok') is True and metadata.get('paid_calls')==0 and not result.get('exception_info')
    else:
        live=results[0].parent/'agent/live'
        info['solver_exit']=read(live/'agent-exit.json')
        info['usage']=read(live/'shared-state.json')
        info['provider']=read(live/'provider-state.json')
        info['budget_stop']=read(live/'budget-stop.json')
    return info

def live_dir(row):
    paths=list((ROOT/'jobs'/row['job']).glob('*/agent/live'))
    return paths[0] if len(paths)==1 else None

def accept_provider(key,budget):
    """Three tiny, fully metered protocol checks; never exposes key or response prose."""
    profile=budget.profile
    def call(number,messages,tools=None,choice=None):
        payload=dict(model=profile['model'],max_tokens=128,stream=True,messages=messages,temperature=0,
                     thinking={'type':'disabled'})
        if tools:payload['tools']=tools
        if choice:payload['tool_choice']=choice
        identity='provider-acceptance-'+str(time.time_ns())+'-'+str(number)
        budget.ledger.reserve(dict(id=identity,job='provider-acceptance',arm='acceptance',endpoint=profile['endpoint'],model=profile['model'],max_tokens=128))
        try:
            req=urllib.request.Request(profile['endpoint'],json.dumps(payload).encode(),headers={
                'Content-Type':'application/json','x-api-key':key,'anthropic-version':'2023-06-01'})
            with urllib.request.urlopen(req,timeout=90) as response:
                status=response.status; content_type=response.headers.get('Content-Type',''); raw=response.read().decode()
            events=[]
            for line in raw.splitlines():
                if line.startswith('data:'):
                    try:events.append(json.loads(line[5:]))
                    except ValueError:pass
            usage={};blocks={};stopped=False
            for event in events:
                if event.get('type')=='message_start':usage.update(event.get('message',{}).get('usage',{}))
                if event.get('type')=='message_delta':usage.update(event.get('usage',{}))
                if event.get('type')=='message_stop':stopped=True
                if event.get('type')=='content_block_start':blocks[event['index']]=dict(event['content_block'])
                if event.get('type')=='content_block_delta':
                    block=blocks.get(event['index'],{}); delta=event.get('delta',{})
                    if delta.get('type')=='input_json_delta':block['_json']=block.get('_json','')+delta.get('partial_json','')
                    if delta.get('type')=='text_delta':block['text']=block.get('text','')+delta.get('text','')
            valid=stopped and all(type(usage.get(k)) is int and usage[k]>=0 for k in ('input_tokens','output_tokens'))
            tokens=sum(usage.get(k,0) for k in ('input_tokens','output_tokens','cache_read_input_tokens','cache_creation_input_tokens')) if valid else None
        except BaseException as error:
            details=dict(type=type(error).__name__,http_status=getattr(error,'code',None),number=number)
            if isinstance(error,urllib.error.HTTPError):
                message=error.read(4096).decode(errors='replace').replace(key,'[REDACTED]')
                import re
                details['response']=re.sub(r'[A-Za-z0-9_+/=.-]{24,}','[LONG_IDENTIFIER]',message)
            save('provider-error.json',details)
            budget.ledger.settle(dict(id=identity,tokens=None));raise
        budget.ledger.settle(dict(id=identity,tokens=tokens))
        receipt=dict(number=number,http_status=status,content_type=content_type,complete=stopped,usage=usage)
        if not valid or status!=200:raise RuntimeError('Provider protocol or usage verification failed')
        return list(blocks.values()),receipt
    receipts=[]
    _,receipt=call(1,[{'role':'user','content':'Reply only OK.'}]);receipts.append(receipt)
    messages=[{'role':'user','content':'Call probe_echo with value OK.'}]
    tool=[{'name':'probe_echo','description':'A harmless protocol echo test.','input_schema':{'type':'object','properties':{'value':{'type':'string'}},'required':['value']}}]
    blocks,receipt=call(2,messages,tool,{'type':'tool','name':'probe_echo'});receipts.append(receipt)
    uses=[block for block in blocks if block.get('type')=='tool_use' and block.get('name')=='probe_echo']
    if len(uses)!=1:raise RuntimeError('Provider did not return a complete tool call')
    block=uses[0]
    if '_json' in block:block['input']=json.loads(block.pop('_json'))
    messages += [{'role':'assistant','content':[block]}, {'role':'user','content':[{'type':'tool_result','tool_use_id':block['id'],'content':'OK'}]}]
    _,receipt=call(3,messages,tool);receipts.append(receipt)
    save('provider-acceptance.json',dict(passed=True,checked_utc=now(),endpoint=profile['endpoint'],model=profile['model'],checks=receipts))

def launch():
    validate()
    if (ROOT/'launch.json').exists():
        if sys.argv[1:]!=['resume-probe']:raise RuntimeError('Existing launch; inspect instead of replaying')
        previous=read(ROOT/'health.json')
        if previous.get('active') or previous.get('rows') or previous.get('state')!='stopped':raise RuntimeError('Only a stopped pre-trial protocol probe can resume')
        from spending import Ledger
        ledger=Ledger(ROOT/'spending.sqlite',read(ROOT/'budget-profile.json'))
        if ledger.status()['halt_reason']!='usage_unavailable':raise RuntimeError('Unexpected hold; inspect manually')
        # Prior uncertain calls stay fully charged at their conservative ceiling.
        # This operator-invoked diagnostic continuation never resets spending.
        history=ROOT/('probe-history-'+str(time.time_ns()));history.mkdir()
        for name in ('launch.json','health.json','supervisor.log','error.json','provider-error.json'):
            if (ROOT/name).exists():(ROOT/name).rename(history/name)
        with ledger.db() as db:db.execute("DELETE FROM meta WHERE key='halt' AND value='usage_unavailable'")
    payload=json.loads(sys.stdin.readline());key=payload.pop('key','')
    if not key:raise RuntimeError('Missing key')
    log=(ROOT/'supervisor.log').open('xb')
    child=subprocess.Popen([PY,str(ROOT/'run.py'),'worker'],stdin=subprocess.PIPE,stdout=log,stderr=log,start_new_session=True)
    child.stdin.write((json.dumps({'key':key})+'\n').encode());child.stdin.close();key=''
    save('launch.json',dict(pid=child.pid,created_utc=now(),campaign=str(ROOT),budget_yuan=30,arms=['kz','dsh']))
    print(json.dumps(read(ROOT/'launch.json')),flush=True)

def worker():
    key=json.loads(sys.stdin.readline())['key']
    with (ROOT/'supervisor.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        validate()
        budget=BudgetService(ROOT,port=28495)
        proxy=network_proxy.ThreadingHTTPServer((network_proxy.HOST,PORT),network_proxy.Handler)
        threading.Thread(target=proxy.serve_forever,daemon=True).start()
        rows=[];active={};reason=None;winner=None
        def checkpoint(state):
            save('health.json',dict(state=state,updated_utc=now(),pid=os.getpid(),stop_reason=reason,winner=winner,
                 spending=budget.snapshot(),rows=rows,active=[dict(job=k,pid=v['process'].pid,offline=v['offline']) for k,v in active.items()]))
        def halt(why):
            nonlocal reason
            if reason is None:reason=why
            budget.ledger.halt(reason)
            # Stop in-flight solvers through their existing scoped watchdog. Harbor
            # continues collecting artifacts and runs its unchanged official verifier.
            for item in active.values():
                if item['offline']:continue
                live=live_dir(item['row'])
                if live:
                    temporary=live/('host-stop-'+str(os.getpid())+'.tmp')
                    try:
                        temporary.write_text(json.dumps({'reason':reason}));temporary.replace(live/'budget-stop.json')
                    except PermissionError:
                        # Preserve the ledger halt even when an unexpected task
                        # identity prevents host file writes. Stop its Harbor process.
                        import signal
                        os.killpg(item['process'].pid,signal.SIGTERM)
        try:
            checkpoint('provider_acceptance')
            accept_provider(key,budget)
            start_index=read(ROOT/'launch-options.json').get('start_index',0)
            if type(start_index) is not int or not 0<=start_index<len(read(ROOT/'tasks.json')['tasks']):raise RuntimeError('Invalid continuation index')
            for index,task in enumerate(read(ROOT/'tasks.json')['tasks']):
                if index<start_index:continue
                if reason:break
                pair=[dict(task=task['name'],arm=arm,job=f'{index+1:02d}-{arm}-{task["name"]}',state='pending') for arm in ('kz','dsh')]
                rows.extend(pair)
                for offline in (True,False):
                    if reason:break
                    if not offline and not all(row.get('preflight',{}).get('install_ok') for row in pair):
                        halt('offline_preflight_failed');break
                    need=max(30*1024**3,2*int(task.get('environment',{}).get('storage_mb',10240))*1024**2)
                    if shutil.disk_usage('/var/lib/docker').free < 2*need or shutil.disk_usage(ROOT).free<2*1024**3:
                        halt('insufficient_disk_for_pair');break
                    fixtures=[]
                    for row in pair:
                        selected_budget=budget
                        if offline:
                            fixture_root=ROOT/'fixture-ledgers'/row['job'];fixture_root.mkdir(parents=True,exist_ok=True)
                            shutil.copyfile(ROOT/'budget-profile.json',fixture_root/'budget-profile.json')
                            selected_budget=BudgetService(fixture_root,port=28496+len(fixtures));fixtures.append(selected_budget)
                        row['state']='preflight_admitted' if offline else 'paid_admitted'
                        checkpoint('starting_pair')
                        env=dict(os.environ,PYTHONPATH=str(ROOT),PYTHONDONTWRITEBYTECODE='1',PAIRED_TASK=row['task'],
                          PAIRED_PROXY_URL=f'http://10.123.0.1:{PORT}',CAMPAIGN_BUDGET_URL=selected_budget.url,CAMPAIGN_BUDGET_TOKEN=selected_budget.token,
                          CAMPAIGN_BUDGET_JOB=row['job'],CAMPAIGN_BUDGET_ARM=row['arm'],CAMPAIGN_BUDGET_REQUIRED='1',
                          MODEL_MESSAGES_ENDPOINT=budget.profile['endpoint'],CAMPAIGN_MODEL=budget.profile['model'])
                        env.pop('TAOTOKEN_API_KEY',None)
                        if not offline:env['TAOTOKEN_API_KEY']=key
                        log=(ROOT/(('preflight-' if offline else '')+row['job']+'.log')).open('xb')
                        process=subprocess.Popen(command(row,offline),env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
                        env.pop('TAOTOKEN_API_KEY',None)
                        row.update(state='preflighting' if offline else 'running',started_utc=now(),pid=process.pid)
                        active[row['job']]=dict(row=row,process=process,log=log,offline=offline)
                    while active:
                        status=budget.snapshot()
                        if status.get('halt_reason'):halt(status['halt_reason'])
                        for job,item in list(active.items()):
                            row=item['row'];process=item['process']
                            if process.poll() is None:
                                if not offline:
                                    # Result may be written before Harbor cleanup exits.
                                    result=collect(row)
                                    if result.get('passed') and winner is None:
                                        winner=dict(task=row['task'],arm=row['arm'],observed_utc=now(),**result);save('first-pass.json',winner);halt('first_official_pass')
                                    live=live_dir(row)
                                    if live:
                                        provider=read(live/'provider-state.json')
                                        row['live']={'provider':provider,'usage':read(live/'shared-state.json')}
                                        if provider.get('kind') in ('credentials','quota','budget'):halt('provider_'+provider['kind'])
                                continue
                            item['log'].close();del active[job]
                            result=collect(row,offline);result['harbor_exit']=process.returncode
                            row['preflight' if offline else 'result']=result
                            row.update(state='preflight_complete' if offline else 'finished',finished_utc=now())
                            if not offline and result.get('passed') and winner is None:
                                winner=dict(task=row['task'],arm=row['arm'],observed_utc=now(),**result);save('first-pass.json',winner);halt('first_official_pass')
                            if not offline and result.get('budget_stop'):halt(result['budget_stop'].get('reason','spending_stopped'))
                        if reason:halt(reason)
                        checkpoint('stopping_after_pass' if winner else 'held' if reason else 'preflighting' if offline else 'running')
                        if active:time.sleep(3)
                    for fixture in fixtures:fixture.close()
                    if not offline:checkpoint('pair_finished')
            if not reason:reason='task_queue_finished'
            checkpoint('completed_first_pass' if winner else 'stopped')
        except BaseException as error:
            halt('supervisor_'+type(error).__name__)
            save('error.json',dict(type=type(error).__name__,time=now()))
            checkpoint('error')
        finally:
            key=''
            # Retain proxy and budget service until admitted Harbor trials finish.
            while active:
                halt(reason or 'supervisor_stopped')
                for job,item in list(active.items()):
                    if item['process'].poll() is not None:
                        item['log'].close();item['row']['result']=collect(item['row'],item['offline']);del active[job]
                if active:time.sleep(3)
            checkpoint('completed_first_pass' if winner else 'stopped')
            proxy.shutdown();budget.close()

if __name__=='__main__':
    if sys.argv[1:] == ['worker']:worker()
    elif sys.argv[1:] == ['precheck']:validate();print('READY')
    else:launch()
