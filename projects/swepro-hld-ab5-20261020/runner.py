"""Isolated Docker execution, keyless preflight and pristine-patch evaluation."""
import ast,concurrent.futures,hashlib,json,os,re,select,shlex,shutil,socket,socketserver,subprocess,sys,threading,time,uuid
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from spending import BudgetService,Ledger,server_for
from storage import atomic_json,supervisor_lock
R=Path(__file__).resolve().parent
LABEL='swepro-hld-ab5-20261020'
STATE_LOCK=threading.RLock()
def read(p,default=None):
 try:return json.loads(Path(p).read_text())
 except (FileNotFoundError,ValueError):return {} if default is None else default
def save(p,value):atomic_json(Path(p),value)
def run(args,**kw):return subprocess.run(args,check=True,**kw)
def output(args,**kw):return run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,**kw).stdout
def inspect(name):return json.loads(output(['docker','inspect',name]))[0]
def pump(a,b):
 try:
  while True:
   ready,_,_=select.select([a,b],[],[],600)
   if not ready:return
   for src in ready:
    data=src.recv(65536)
    if not data:return
    (b if src is a else a).sendall(data)
 except OSError:pass
class Proxy(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_CONNECT(self):
  if self.path.lower()!='api.taotoken.net:443':self.send_error(403);return
  try:up=socket.create_connection(('api.taotoken.net',443),20)
  except OSError:self.send_error(502);return
  with up:
   self.send_response(200,'Connection Established');self.end_headers();pump(self.connection,up)
 def do_GET(self):self.send_error(403)
 def do_POST(self):self.send_error(403)
def unix_relay(path,port):
 class Handler(socketserver.BaseRequestHandler):
  def handle(self):
   try:
    with socket.create_connection(('127.0.0.1',port),10) as peer:pump(self.request,peer)
   except OSError:pass
 class Server(socketserver.ThreadingUnixStreamServer):
  daemon_threads=True
 server=Server(str(path),Handler);os.chmod(path,0o777)
 threading.Thread(target=server.serve_forever,daemon=True).start();return server
class Services:
 def __init__(self,budget):
  self.root=R/'relays'/uuid.uuid4().hex;self.root.mkdir(parents=True)
  self.proxy=ThreadingHTTPServer(('127.0.0.1',0),Proxy)
  threading.Thread(target=self.proxy.serve_forever,daemon=True).start()
  self.relays=[unix_relay(self.root/'proxy.sock',self.proxy.server_port),unix_relay(self.root/'budget.sock',budget.server.server_port)]
 def close(self):
  for s in self.relays:s.shutdown();s.server_close()
  self.proxy.shutdown();self.proxy.server_close()
def owner(name):
 doc=inspect(name)
 if doc['Config'].get('Labels',{}).get('experiment')!=LABEL:raise RuntimeError('Refusing to touch unowned container')
 return doc
def remove(name):
 owner(name);run(['docker','rm','-f',name],stdout=subprocess.DEVNULL)
def create(task,name,network='none',mounts=()):
 from dependencies import mount
 mounts=[*mounts,mount()]
 args=['docker','run','-d','--name',name,'--label','experiment='+LABEL,'--network',network,'--cpus','1','--memory','8g','--pids-limit','2048','--security-opt','no-new-privileges','--cap-drop','NET_RAW','--ulimit','nofile=65536:65536','--entrypoint','/bin/bash']
 for src,dst,readonly in mounts:args+=['--mount',f'type=bind,src={src},dst={dst}'+(',readonly' if readonly else '')]
 args +=[task['image_id'],'-c','exec sleep infinity']
 output(args)
 return name
def execute(name,cmd,timeout=60,**kw):
 return subprocess.run(['docker','exec',name,'bash','-c',cmd],timeout=timeout,**kw)
def cwd_of(name):
 r=execute(name,'if test -d /app/.git; then echo /app; elif test -d /testbed/.git; then echo /testbed; else exit 1; fi',capture_output=True,text=True)
 if r.returncode:raise RuntimeError('Repository workdir unavailable')
 return r.stdout.strip()
def task_path(task):return R/'tasks'/task['name']
def parsed_required(task):
 cfg=read(task_path(task)/'tests/config.json')
 def parse(x):return ast.literal_eval(x) if isinstance(x,str) else x
 return set(parse(cfg['fail_to_pass']))|set(parse(cfg['pass_to_pass']))
def required_interface_failure(task,raw):
 """Recognize only local interfaces explicitly requested by these frozen tasks."""
 name=task.get('name','')
 if name not in (
  'instance_flipt-io__flipt-e88e93990e3ec1e7697754b423decc510d5dd5fe',
  'instance_internetarchive__openlibrary-9cd47f4dc21e273320d9e30d889c864f8cb20ccf-v0f5aece3601a5b4419f7ccec1dbda2071be28ee4'):return False
 # Never reinterpret dependency, storage or transport failures as task failures.
 if re.search(r'(?i)(no space left|network is unreachable|TLS handshake timeout|i/o timeout|connection refused|no required module provides|ModuleNotFoundError|could not resolve host)',raw):return False
 instruction=(task_path(task)/'instruction.md').read_text()
 if name.startswith('instance_flipt-io__flipt-'):
  errors=re.findall(r'(?m)^.*\.go:\d+(?::\d+)?: (.+)$',raw)
  return bool(errors) and 'build failed' in raw and all(
   re.search(r'\.FlagKey undefined .*evaluation"?\.(?:Boolean|Variant)EvaluationResponse has no field or method FlagKey\)',e)
   for e in errors) and all(s in instruction for s in ('BooleanEvaluationResponse','VariantEvaluationResponse','flag_key','GetFlagKey()'))
 errors=re.findall(r'(?m)^E\s+(.+)$',raw)
 expected="ImportError: cannot import name 'ALLOWED_COVER_HOSTS' from 'openlibrary.catalog.add_book' (/app/openlibrary/catalog/add_book/__init__.py)"
 return bool(errors) and all(e==expected for e in errors) and 'ERROR collecting openlibrary/catalog/add_book/tests/test_add_book.py' in raw and all(s in instruction for s in ('ALLOWED_COVER_HOSTS','openlibrary/catalog/add_book/__init__.py'))
def assess(task,folder,exit_code):
 p=folder/'verifier';report=read(p/'output.json');tests=report.get('tests',[])
 required=parsed_required(task);passed={t['name'] for t in tests if t.get('status')=='PASSED'}
 reward=(p/'reward.txt').read_text().strip() if (p/'reward.txt').exists() else None
 raw='\n'.join(q.read_text(errors='replace') for q in [p/'run-script-stdout.txt',p/'run-script-stderr.txt'] if q.exists())
 # Some SWE patches introduce an interface required by the hidden tests.
 # The unpatched repo then fails to compile and legitimately reports zero tests.
 compilation_failure=exit_code==1 and reward=='0' and 'build failed' in raw and bool(re.search(r'(?m)^.*\.(?:go|c|cpp|h):\d+(?::\d+)?:.*(?:undefined:|syntax error|cannot use|not enough arguments|too many arguments)',raw))
 interface_failure=exit_code==1 and reward=='0' and required_interface_failure(task,raw)
 valid=exit_code in (0,1) and bool(required) and isinstance(report.get('tests'),list) and (bool(tests) or compilation_failure or interface_failure) and reward in ('0','1') and (reward=='1')==(required<=passed)
 return dict(engineering_clean=valid,reward=int(reward) if reward in ('0','1') else None,required=len(required),required_passed=len(required&passed),reported_tests=len(tests),exit_code=exit_code,failure_kind='required_interface_missing' if interface_failure else ('compilation' if compilation_failure else None))
def grade(task,folder,patch=None,gold=False):
 folder.mkdir(parents=True,exist_ok=True);name=LABEL+'-g-'+uuid.uuid4().hex[:12]
 create(task,name,'none',[(task_path(task)/'tests','/tests',True)])
 try:
  verifier_identity=owner(name)
  assert verifier_identity['HostConfig']['NetworkMode']=='none'
  save(folder/'environment.json',dict(image_id=verifier_identity['Image'],network='none',container=name))
  cwd=cwd_of(name)
  # Harbor normally prepares this directory before launching the verifier.
  # Official test.sh copies reports BEFORE its EXIT trap creates reward.txt.
  ready=execute(name,'mkdir -p /logs/verifier && test -w /logs/verifier',30,capture_output=True)
  if ready.returncode:raise RuntimeError('Verifier output directory is not writable')
  if gold:
   run(['docker','cp',str(task_path(task)/'solution'),name+':/solution'],stdout=subprocess.DEVNULL)
   cmd='bash /solution/solve.sh'
  elif patch is not None and patch.stat().st_size:
   run(['docker','cp',str(patch),name+':/tmp/model.patch'],stdout=subprocess.DEVNULL)
   cmd=f'cd {cwd} && (git apply --verbose /tmp/model.patch || git apply --3way /tmp/model.patch || patch --fuzz=3 -p1 -i /tmp/model.patch)'
  else:cmd='true'
  with (folder/'apply.log').open('wb') as log:
   applied=execute(name,cmd,300,stdout=log,stderr=log)
  save(folder/'apply.json',dict(exit_code=applied.returncode,gold=gold))
  if applied.returncode:raise RuntimeError('Patch application failed')
  from dependencies import prepare
  save(folder/'dependency-readiness.json',prepare(task,name))
  with (folder/'verifier.log').open('wb') as log:
   try:result=execute(name,'bash /tests/test.sh',3050,stdout=log,stderr=log);code=result.returncode
   except subprocess.TimeoutExpired:code=124;run(['docker','stop','-t','2',name],stdout=subprocess.DEVNULL)
  cp=subprocess.run(['docker','cp',name+':/logs/verifier',str(folder/'verifier')],capture_output=True)
  if cp.returncode:raise RuntimeError('Missing verifier artifacts')
  result=assess(task,folder,code);save(folder/'result.json',result);return result
 finally:remove(name)
def install_mounts(services,arm="old"):
 return [(R/('compat' if d in ('node','kz-python','glibc') else 'bundle')/('hld-new' if d=='kz' and arm=='new' else d),'/opt/'+d,True) for d in ['node','kz','recuris-dsh','dsh-baselines','kz-python','glibc']]+[(services.root,'/relay',True)]
def probe(task,arm,services,budget):
 folder=R/'entry-probes'/(arm+'-'+uuid.uuid4().hex[:8]);folder.mkdir(parents=True,exist_ok=False)
 name=LABEL+'-p-'+arm
 create(task,name,mounts=install_mounts(services,arm))
 try:
  cwd=cwd_of(name)
  # No internet interface exists; inspect and exercise both permitted/denied relay paths.
  assert inspect(name)['HostConfig']['NetworkMode']=='none'
  payload=payload_for(arm,'entry-test','Complete the task.',budget,'dummy-offline-never-transmitted')
  p=subprocess.run(['docker','exec','-i','-w',cwd,name,'/opt/node/bin/node','/opt/kz/container-run.mjs'],input=json.dumps(payload).encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120)
  (folder/'stdout.log').write_bytes(p.stdout);(folder/'stderr.log').write_bytes(p.stderr)
  run(['docker','cp',name+':/logs/agent/live',str(folder/'live')],stdout=subprocess.DEVNULL)
  assert read(folder/'live/budget-stop.json').get('reason')=='per_task_budget_exhausted', 'Entrypoint did not reach budget admission'
  assert budget.snapshot()['settled_microcny']==0 and budget.snapshot()['reserved_microcny']==0
  save(folder/'result.json',dict(passed=True,model_calls=0,network='none'))
 finally:remove(name)
def payload_for(arm,job,instruction,budget,key):
 return dict(arm='hld',key=key,instruction=instruction,proxy='http://127.0.0.1:19051',no_proxy='localhost,127.0.0.1',attempt_id=uuid.uuid4().hex,spending=dict(CAMPAIGN_BUDGET_REQUIRED='1',CAMPAIGN_BUDGET_URL='http://127.0.0.1:19052',CAMPAIGN_BUDGET_TOKEN=budget.token,CAMPAIGN_BUDGET_JOB=job,CAMPAIGN_BUDGET_ARM='kz'))
def solve(task,arm,services,budget,key,rows,checkpoint):
 job=f'swp-{task["index"]:02}-{arm}';folder=R/'jobs'/job
 folder.mkdir(parents=True,exist_ok=False);name=LABEL+'-s-'+job
 row=rows[job]
 try:
  create(task,name,mounts=install_mounts(services,arm));cwd=cwd_of(name)
  base=output(['docker','exec','-w',cwd,name,'git','rev-parse','HEAD']).decode().strip()
  save(folder/'identity.json',dict(image_id=task['image_id'],base_commit=base,container=name,cwd=cwd))
  from dependencies import prepare
  with STATE_LOCK:row.update(state='preparing_dependencies',container=name);checkpoint()
  save(folder/'dependency-readiness.json',prepare(task,name,solver=True))
  instruction=(task_path(task)/'instruction.md').read_text()
  payload=payload_for(arm,job,instruction,budget,key)
  with STATE_LOCK:row.update(state='running',started=time.time(),container=name);checkpoint()
  with (folder/'wrapper.log').open('wb') as log:
   try:p=subprocess.run(['docker','exec','-i','-w',cwd,name,'/opt/node/bin/node','/opt/kz/container-run.mjs'],input=json.dumps(payload).encode(),stdout=log,stderr=log,timeout=3060);code=p.returncode
   except subprocess.TimeoutExpired:code=124
  # End all solver/tool processes, including after OOM; restart ONLY PID 1 sleep.
  # Avoid trying to exec pkill in an exhausted/dead solver container.
  collect_state=owner(name)
  save(folder/'container-before-collection.json',dict(state=collect_state['State'],image=collect_state['Image']))
  if collect_state['Config']['Entrypoint']!=['/bin/bash'] or collect_state['Config']['Cmd']!=['-c','exec sleep infinity'] or collect_state['HostConfig']['NetworkMode']!='none':raise RuntimeError('Unexpected recovery entrypoint or network')
  if collect_state['State']['Running']:run(['docker','stop','-t','2',name],stdout=subprocess.DEVNULL,timeout=30)
  run(['docker','cp',name+':/logs/agent/live',str(folder/'live')],stdout=subprocess.DEVNULL)
  run(['docker','start',name],stdout=subprocess.DEVNULL,timeout=30)
  # Stage additions with intent-to-add; compare against immutable starting commit even if agent committed.
  capture=f'cd {cwd} && git add -N . && git diff --binary {shlex.quote(base)} -- . ":(exclude)BENCHMARK_INSTRUCTION.md"'
  with (folder/'model.patch').open('wb') as f:
   result=execute(name,capture,120,stdout=f,stderr=subprocess.PIPE)
  if result.returncode:raise RuntimeError('Patch capture failed')
  save(folder/'solver.json',dict(exit_code=code,patch_sha256=hashlib.sha256((folder/'model.patch').read_bytes()).hexdigest()))
  remove(name);name=None
  with STATE_LOCK:row.update(state='grading',solver_exit=code);checkpoint()
  scored=grade(task,folder/'grade',folder/'model.patch')
  provider=read(folder/'live/provider-state.json');exit_doc=read(folder/'live/agent-exit.json');stop=read(folder/'live/limit-stop.json') or read(folder/'live/budget-stop.json')
  expected_stop=stop.get('reason') in ('per_task_budget_exhausted','per_task_request_limit','per_task_tool_limit') or exit_doc.get('timed_out')
  if not expected_stop:
   from budget_classification import hld_monetary_stop
   expected_stop=hld_monetary_stop(folder/'live','hld',bool(exit_doc),code)
  clean=scored['engineering_clean'] and exit_doc.get('attempt_id')==payload['attempt_id'] and (code==0 or expected_stop) and provider.get('kind') in (None,'available','budget')
  with STATE_LOCK:
   row.update(state='completed' if clean else 'engineering_failed',**{k:v for k,v in scored.items() if k!='engineering_clean'},engineering_clean=clean,official_score_valid=scored['engineering_clean'],budget_stop=stop,provider_kind=provider.get('kind'),finished=time.time());checkpoint()
 except Exception as exc:
  with STATE_LOCK:row.update(state='engineering_failed',error_type=type(exc).__name__,error=str(exc)[:300],finished=time.time());checkpoint()
 finally:
  if name:
   # Preserve an uncollected submission for engineering recovery; stop its processes.
   try:
    owner(name);subprocess.run(['docker','stop','-t','2',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15)
    with STATE_LOCK:row.update(retained_container=name);checkpoint()
   except Exception:pass
def image_prepare(task):
 folder=R/'preflight'/task['name'];folder.mkdir(parents=True,exist_ok=True)
 prior=subprocess.run(['docker','image','inspect',task['image']],capture_output=True)
 task['image_preexisting']=prior.returncode==0
 if prior.returncode:
  error=None
  for attempt in range(1,5):
   name=f'pull-repair-{time.time_ns()}-{attempt}.log'
   with (folder/name).open('wb') as f:
    try:
     run(['skopeo','copy','--retry-times','2','--override-os','linux','--override-arch','amd64','--format','v2s2','docker://'+task['image'],'docker-daemon:'+task['image']],stdout=f,stderr=f,timeout=1800);error=None;break
    except (subprocess.CalledProcessError,subprocess.TimeoutExpired) as exc:error=exc
   save(folder/'download-state.json',dict(state='retrying' if attempt<4 else 'failed',attempt=attempt,log=name))
   if attempt<4:time.sleep([3,10,30][attempt-1])
  if error:raise error
 info=json.loads(output(['docker','image','inspect',task['image']]))[0];task['image_id']=info['Id']
 save(folder/'image.json',dict(id=info['Id'],digests=info.get('RepoDigests'),preexisting=task['image_preexisting']))
 return folder

def validate_preflight(task,folder,empty,gold):
 if not gold.get('engineering_clean') or gold.get('reward')!=1:return False
 if empty.get('engineering_clean') and empty.get('reward')==0:return True
 if empty.get('reward')==0 and empty.get('exit_code')==1 and (task_path(task)/'tests/config.json').exists():
  ep=folder/'dependency-empty';gp=folder/'dependency-gold'
  if read(ep/'result.json')==empty and read(gp/'result.json')==gold and read(ep/'apply.json')==dict(exit_code=0,gold=False) and read(gp/'apply.json')==dict(exit_code=0,gold=True):
   calibrated=assess(task,ep,1);verified_gold=assess(task,gp,gold.get('exit_code'))
   if calibrated['engineering_clean'] and calibrated['failure_kind']=='required_interface_missing' and verified_gold['engineering_clean'] and verified_gold['reward']==1:
    files=[p for root in (ep,gp) for p in root.rglob('*') if p.is_file()]
    save(folder/'interface-negative-control-calibration.json',dict(accepted=True,reason='baseline_missing_task_required_interface',empty=calibrated,gold=verified_gold,source_changes=False,verifier_changes=False,evidence_sha256={str(p.relative_to(folder)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}))
    return True
 # This public task explicitly requires adding netlink as a direct dependency.
 # Empty baseline has no such module; Go's implicit latest resolution is too new
 # for its Go 1.18 toolchain. Gold's full test pass calibrates the same image.
 # Scope this known negative-control failure to its frozen instance and evidence.
 if task['name']!='instance_gravitational__teleport-7744f72c6eb631791434b648ba41083b5f6d2278-vce94f93ad1030e3136852817f2423c1b3ac37bc4':return False
 if empty.get('reward')!=0 or empty.get('exit_code')!=1:return False
 p=folder/'empty/verifier/run-script-stderr.txt'
 raw=p.read_text(errors='replace') if p.exists() else ''
 instruction=(task_path(task)/'instruction.md').read_text()
 expected=('github.com/mdlayher/netlink@v1.11.2/conn.go' in raw and 'package iter is not in GOROOT (/usr/local/go/src/iter)' in raw and 'must be declared as a direct dependency' in instruction)
 if expected:save(folder/'negative-control-calibration.json',dict(accepted=True,reason='baseline_missing_required_dependency',official_reward=0,gold_reward=1,gold_required_passed=gold['required_passed'],source_changes=False,verifier_changes=False))
 return expected
def freeze_validate():
 for task in read(R/'tasks.json')['tasks']:
  for rel,h in task['files'].items():
   assert hashlib.sha256((task_path(task)/rel).read_bytes()).hexdigest()==h
 for rel,h in read(R/'source-lock.json').items():assert hashlib.sha256((R/'bundle'/rel).read_bytes()).hexdigest()==h
def supervise(key):
 freeze_validate()
 with supervisor_lock(R):
  if (R/'health.json').exists():raise RuntimeError('Existing run: explicit recovery required; refusing paid replay')
  budget=BudgetService(R,host='127.0.0.1',port=0);services=Services(budget)
  tasks=read(R/'tasks.json')['tasks'];rows={f'swp-{t["index"]:02}-{a}':dict(task=t['name'],arm=a,state='pending') for t in tasks for a in ('hld','recuris')}
  def checkpoint():
   with STATE_LOCK:
    summary={a:dict(completed=sum(r['arm']==a and r['state']=='completed' for r in rows.values()),passed=sum(r['arm']==a and r['state']=='completed' and r.get('reward')==1 for r in rows.values()),engineering_failed=sum(r['arm']==a and r['state']=='engineering_failed' for r in rows.values())) for a in ('hld','recuris')}
    save(R/'health.json',dict(updated=time.time(),pid=os.getpid(),state='finished' if all(r['state'] in ('completed','engineering_failed') for r in rows.values()) else 'running',summary=summary,rows=rows,spending=budget.snapshot()))
  checkpoint()
  def worker(task):
   jobnames=[f'swp-{task["index"]:02}-{a}' for a in ('hld','recuris')]
   try:
    # Two task slots, at most four solver/verifier containers; no global image pruning.
    while shutil.disk_usage('/var/lib/docker').free<45*1024**3 or shutil.disk_usage(R).free<5*1024**3:
     with STATE_LOCK:
      for j in jobnames:rows[j]['state']='held_low_disk'
      checkpoint()
     time.sleep(20)
    with STATE_LOCK:
     for j in jobnames:rows[j]['state']='preflight'
     checkpoint()
    folder=image_prepare(task)
    empty=grade(task,folder/'empty');gold=grade(task,folder/'gold',gold=True)
    if not empty['engineering_clean'] or empty['reward']!=0 or not gold['engineering_clean'] or gold['reward']!=1:raise RuntimeError('Official empty/gold preflight did not validate')
    save(folder/'ready.json',dict(passed=True,empty=empty,gold=gold))
    # Entry gates are global and run exactly once before any paid call.
    with ENTRY_LOCK:
     if not (R/'entry-ready.json').exists():
      probe_root=R/'probe-budget';probe_root.mkdir()
      profile=read(R/'budget-profile.json');profile.update(campaign_limit_microcny=1,task_limit_microcny=1,jobs=['entry-test']);save(probe_root/'budget-profile.json',profile)
      pb=BudgetService(probe_root,host='127.0.0.1',port=0);ps=Services(pb)
      try:
       for arm in ('hld','recuris'):probe(task,arm,ps,pb)
       save(R/'entry-ready.json',dict(passed=True,model_calls=0))
      finally:ps.close();pb.close()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
     futures=[pool.submit(solve,task,a,services,budget,key,rows,checkpoint) for a in ('hld','recuris')]
     for f in futures:f.result()
   except Exception as exc:
    with STATE_LOCK:
     for j in jobnames:
      if rows[j]['state'] not in ('completed','engineering_failed'):rows[j].update(state='engineering_failed',error_type=type(exc).__name__,error=str(exc)[:300],paid_calls=0)
     checkpoint()
   finally:
    if task.get('image_id') and not task.get('image_preexisting') and all(rows[j]['state']=='completed' for j in jobnames):
     # Only this campaign's newly pulled tag, after both runs have saved patches/results.
     p=subprocess.run(['docker','image','rm',task['image']],capture_output=True,text=True)
     save(R/'preflight'/task['name']/'image-release.json',dict(exit_code=p.returncode,output=p.stdout[-1000:],error=p.stderr[-500:]))
  try:
   with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    futures=[pool.submit(worker,t) for t in tasks]
    while not all(f.done() for f in futures):checkpoint();time.sleep(10)
    for f in futures:f.result()
  finally:checkpoint();services.close();budget.close()
ENTRY_LOCK=threading.Lock()
if __name__=='__main__':
 if '--supervise' in sys.argv:
  credential=Path.home()/'.config/appworld-credentials/taotoken-standby.json'
  supervise(read(credential)['key'])
 elif '--launch' in sys.argv:
  freeze_validate()
  with (R/'launch-once.marker').open('x') as f:f.write(str(time.time()))
  with (R/'supervisor.log').open('xb') as log:p=subprocess.Popen([sys.executable,__file__,'--supervise'],cwd=R,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
  print(json.dumps(dict(pid=p.pid,launched=True,phase='keyless_preflight_first',budget_cny=240)))
