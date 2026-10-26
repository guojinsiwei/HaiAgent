"""One bounded attempt per arm/task; official LHTB verifier, independent fault handling."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import collections,hashlib,json,os,secrets,select,socket,subprocess,sys,threading,time,uuid
from spending import BudgetService
ROOT=Path(__file__).resolve().parent
PY=ROOT/'venv/bin/python'
def read(p,default=None):
    try:return json.loads(Path(p).read_text())
    except (FileNotFoundError,ValueError):return default
def save(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);q=p.with_name(p.name+'.tmp');q.write_text(json.dumps(v,indent=2));q.replace(p)
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def validate():
    ready=read(ROOT/'ready.json',{});assert ready.get('passed'),'Zero-model acceptance incomplete'
    for name,digest in ready['files'].items():assert sha(ROOT/name)==digest,'Changed sealed source: '+name

class ModelProxy(BaseHTTPRequestHandler):
    def log_message(self,*_):pass
    def do_CONNECT(self):
        if self.path!='api.taotoken.net:443':self.send_error(403);return
        try:up=socket.create_connection(('api.taotoken.net',443),20)
        except OSError:self.send_error(502);return
        with up:
            self.send_response(200);self.end_headers()
            while True:
                try:
                    ready,_,_=select.select((self.connection,up),[],[],600)
                    if not ready:return
                    for src in ready:
                        data=src.recv(65536)
                        if not data:return
                        (up if src is self.connection else self.connection).sendall(data)
                except OSError:return

def command(row,offline):
    name=('preflight-' if offline else '')+row['job']
    agent=('Offline' if offline else '')+('HLD' if row['arm']=='hld' else 'Recuris')
    cfg=dict(job_name=name,jobs_dir=str(ROOT/('preflight' if offline else 'jobs')),n_attempts=1,n_concurrent_trials=1,timeout_multiplier=1.0,
        environment=dict(type='docker',force_build=False,delete=False),
        agents=[dict(import_path='agents:'+agent,override_timeout_sec=10800,kwargs={})],
        datasets=[dict(path=str(ROOT/'upstream/tasks'),task_names=[row['task']])])
    config=ROOT/'configs'/(name+'.json');save(config,cfg)
    return [str(PY),str(ROOT/'entry_harbor.py'),'run','-c',str(config)]

def collect(row,offline):
    directory=ROOT/('preflight' if offline else 'jobs')/(('preflight-' if offline else '')+row['job'])
    paths=list(directory.glob('*/result.json'));assert len(paths)==1,'Missing unique trial result'
    path=paths[0];result=read(path,{})
    rewards=(result.get('verifier_result') or {}).get('rewards') or {}
    reward=rewards.get('reward')
    clean=type(reward) in (float,int) and 0<=reward<=1 and not result.get('exception_info')
    live=path.parent/'agent/live';usage=read(live/'shared-state.json',{})
    stops={n:read(live/n) for n in ['budget-stop.json','limit-stop.json','provider-stop.json','wall-limit.json']}
    out=dict(trial=str(path.parent),reward=reward,official_full_pass=reward==1,solved_095=type(reward) in (float,int) and reward>=.95,
        engineering_clean=clean,exception=result.get('exception_info'),shared_usage=usage,stops=stops,
        continuation=(result.get('agent_result') or {}).get('metadata'),offline=offline)
    # Both official artifacts and operator-only intermediate grading snapshots stay on disk.
    identity=read(path.parent/'operator-container.json',{})
    if clean:
        for item in identity.get('containers',[]):
            info=subprocess.run(['docker','inspect',item['id']],capture_output=True,text=True,timeout=30)
            if info.returncode:continue
            doc=json.loads(info.stdout)[0]
            assert doc['Id']==item['id'] and doc['Name']==item['name']
            assert doc['Config']['Labels'].get('com.docker.compose.project')==item['project']
            diff=subprocess.run(['docker','diff',item['id']],capture_output=True,text=True,timeout=60)
            (path.parent/('filesystem-diff-'+item['id'][:12]+'.txt')).write_text(diff.stdout)
            # Keep immutable submitted task artifacts collected by Harbor; release only this completed container.
            subprocess.run(['docker','rm','-f',item['id']],capture_output=True,timeout=60,check=True)
        network=identity.get('network')
        if network:
            doc=json.loads(subprocess.check_output(['docker','network','inspect',network],text=True))[0]
            assert doc.get('Labels',{}).get('experiment')==ROOT.name
            subprocess.run(['docker','network','rm',network],capture_output=True,timeout=30,check=True)
        out['completed_owned_containers_released']=True
    return out

def run_trial(row,offline,token=None,url=None):
    attempt=uuid.uuid4().hex
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPATH=str(ROOT)+':'+str(ROOT/'vendor-src'),
        PAIRED_TASK=row['task'],PAIRED_ATTEMPT_ID=attempt,PAIRED_PROXY_URL='http://10.123.0.1:29561',
        LHTB_OFFLINE='1' if offline else '0',HB_VERIFIER_FEEDBACK_MODE='binary')
    if offline:env.pop('TAOTOKEN_API_KEY',None)
    else:env.update(CAMPAIGN_BUDGET_REQUIRED='1',CAMPAIGN_BUDGET_URL=url,CAMPAIGN_BUDGET_TOKEN=token,CAMPAIGN_BUDGET_JOB=row['job'],CAMPAIGN_BUDGET_ARM='dsh' if row['arm']=='recuris' else 'kz')
    log=ROOT/(('preflight-' if offline else '')+row['job']+'.log')
    with log.open('xb') as stream:
        proc=subprocess.run(command(row,offline),env=env,stdin=subprocess.DEVNULL,stdout=stream,stderr=stream,timeout=27000)
    result=collect(row,offline);result['harbor_exit']=proc.returncode
    if proc.returncode:result['engineering_clean']=False
    return result

def worker(row,budget):
    row.update(state='preflighting',started=time.time())
    try:
        result=run_trial(row,True)
        row['preflight']=result
        if not result['engineering_clean']:row.update(state='engineering_failure',paid_calls=0);return
        validate();row.update(state='solving',paid_started=time.time())
        result=run_trial(row,False,budget.token,budget.url);row.update(result=result,state='done' if result['engineering_clean'] else 'engineering_failure',ended=time.time())
    except Exception as error:row.update(state='engineering_failure',error_type=type(error).__name__,error=str(error)[:1200],ended=time.time())

def snapshot(rows,active,budget,state):
    summaries={}
    for arm in ['hld','recuris']:
        rr=[r for r in rows if r['arm']==arm]
        summaries[arm]=dict(total=len(rr),finished=sum(r['state'] in ['done','engineering_failure'] for r in rr),
            scored=sum(type(r.get('result',{}).get('reward')) in (float,int) for r in rr),
            passed=sum(r.get('result',{}).get('official_full_pass',False) for r in rr),
            solved_095=sum(r.get('result',{}).get('solved_095',False) for r in rr),engineering_failures=sum(r['state']=='engineering_failure' for r in rr))
    for row in rows:
        if row['state']=='solving':
            paths=list((ROOT/'jobs'/row['job']).glob('*/agent/live/shared-state.json'))
            if len(paths)==1:row['live']=read(paths[0],{})
    save(ROOT/'health.json',dict(state=state,pid=os.getpid(),updated=time.time(),concurrency_limit=6,active=[r['job'] for r in active.values()],summary=summaries,rows=rows,spending=budget.snapshot()))

def supervise():
    validate();budget=BudgetService(ROOT,port=29562)
    proxy=ThreadingHTTPServer(('10.123.0.1',29561),ModelProxy);proxy.daemon_threads=True
    threading.Thread(target=proxy.serve_forever,daemon=True).start()
    rows=read(ROOT/'queue.json')['rows'];active={}
    try:
        with ThreadPoolExecutor(max_workers=6) as pool:
            while True:
                for future,row in list(active.items()):
                    if future.done():future.result();del active[future]
                busy=collections.Counter(row['arm'] for row in active.values())
                for row in rows:
                    if len(active)>=6:break
                    if row['state']!='pending' or busy[row['arm']]>=3:continue
                    image=read(ROOT/'image-cache'/row['task']/'ready.json',{})
                    if not image.get('ready'):continue
                    import shutil
                    if shutil.disk_usage('/var/lib/docker').free<12*2**30 or shutil.disk_usage(ROOT).free<4*2**30:continue
                    row['state']='admitted';save(ROOT/'admitted-queue.json',dict(rows=rows))
                    active[pool.submit(worker,row,budget)]=row;busy[row['arm']]+=1
                finished=not active and all(r['state'] in ['done','engineering_failure'] for r in rows)
                snapshot(rows,active,budget,'finished' if finished else 'running')
                if finished:break
                time.sleep(10)
    finally:proxy.shutdown();proxy.server_close();budget.close()

def launch():
    assert not (ROOT/'PAID_START_HOLD').exists(), 'Continuation acceptance pending'
    validate()
    with (ROOT/'launch-once.marker').open('x') as marker:marker.write(str(time.time()))
    secret=read(Path.home()/'.config/appworld-credentials/taotoken-standby.json',{})
    key=secret.get('key') or secret.get('api_key') or secret.get('apiKey');assert key
    with (ROOT/'supervisor.log').open('xb') as log:
        process=subprocess.Popen([str(PY),__file__,'--supervise'],env=dict(os.environ,TAOTOKEN_API_KEY=key,PYTHONDONTWRITEBYTECODE='1'),stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
    receipt=dict(pid=process.pid,started=time.time(),tasks=24,trials=48,arms=['HLD v8','Recuris'],per_run_cny=24,campaign_cny=1152,concurrency=6)
    save(ROOT/'launch-receipt.json',receipt);print(json.dumps(receipt))
if __name__=='__main__':
    if '--supervise' in sys.argv:supervise()
    else:launch()
