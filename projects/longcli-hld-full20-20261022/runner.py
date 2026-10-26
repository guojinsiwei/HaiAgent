"""Latest HLD, fresh official tasks, shared bounded ledger, no paid retries."""
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import json,os,secrets,select,socket,subprocess,sys,threading,time,shutil
from common import ROOT,save,sha,import_tree,export_tree
from spending import Ledger,server_for

def docker(*args,check=True,timeout=120):
 p=subprocess.run(['docker',*map(str,args)],capture_output=True,text=True,timeout=timeout)
 if check and p.returncode:raise RuntimeError(p.stderr[-600:])
 return p

class Proxy:
 def __init__(self,gateway):
  class Handler(BaseHTTPRequestHandler):
   def log_message(self,*args):pass
   def do_CONNECT(self):
    if self.path!='api.taotoken.net:443':self.send_error(403);return
    try:up=socket.create_connection(('api.taotoken.net',443),20)
    except OSError:self.send_error(502);return
    with up:
     self.send_response(200);self.end_headers();peers=(self.connection,up)
     while True:
      ready,_,_=select.select(peers,[],[],600)
      if not ready:return
      for src in ready:
       data=src.recv(65536)
       if not data:return
       (up if src is self.connection else self.connection).sendall(data)
  self.server=ThreadingHTTPServer((gateway,0),Handler);self.server.daemon_threads=True
  threading.Thread(target=self.server.serve_forever,daemon=True).start()
  self.url=f'http://{gateway}:{self.server.server_port}'
 def close(self):self.server.shutdown();self.server.server_close()

def read(path,default=None):
 try:return json.loads(path.read_text())
 except (FileNotFoundError,json.JSONDecodeError):return default

def progress(directory):
 live=directory/'logs/live';shared=read(live/'shared-state.json',{})
 routes=[]
 if (live/'route.jsonl').exists():
  for line in (live/'route.jsonl').read_text(errors='replace').splitlines():
   try:routes.append(json.loads(line))
   except ValueError:pass
 return dict(requests=shared.get('requests',0),tools=shared.get('tools',0),http_200=sum(e.get('event')=='response' and e.get('status')==200 for e in routes),http_errors=[e.get('status') for e in routes if e.get('event')=='response' and e.get('status')!=200],agent_exit=read(live/'agent-exit.json'),budget_stop=read(live/'budget-stop.json'),limit_stop=read(live/'limit-stop.json'),provider_stop=read(live/'provider-stop.json'))

def solve(row,key,ledger,probe=False):
 job='hld--'+row['task'];directory=ROOT/('entry-probes' if probe else 'jobs')/job
 directory.mkdir(parents=True,exist_ok=False)
 assert sha(row['starter_path'])==row['starter_sha256']
 import_tree(row['starter_path'],directory/'workspace')
 for part in ['home','logs']:(directory/part).mkdir()
 instruction=row['instruction']+'\n\n'+(directory/'workspace/INSTRUCTION.md').read_text()
 token=secrets.token_hex(6);name='hld-lcli-'+token;net='hld-lcli-net-'+token
 summary=dict(job=job,task=row['task'],state='preparing',started=time.time(),container=name,version='HLD v8',offline_probe=probe)
 proxy=None;server=None;created=False;network=False
 try:
  docker('network','create','--internal','--label','experiment='+ROOT.name,net);network=True
  gateway=json.loads(docker('network','inspect',net).stdout)[0]['IPAM']['Config'][0]['Gateway']
  auth=secrets.token_urlsafe(32);server=server_for(ledger,auth,host=gateway,port=0)
  threading.Thread(target=server.serve_forever,daemon=True).start()
  if not probe:proxy=Proxy(gateway)
  payload=dict(key=key,arm='hld-new',instruction=instruction,proxy=proxy.url if proxy else 'http://127.0.0.1:1',no_proxy=gateway+',localhost,127.0.0.1',attempt_id=job,spending=dict(CAMPAIGN_BUDGET_REQUIRED='1',CAMPAIGN_BUDGET_URL=f'http://{gateway}:{server.server_port}',CAMPAIGN_BUDGET_TOKEN=auth,CAMPAIGN_BUDGET_JOB=job,CAMPAIGN_BUDGET_ARM='kz'))
  mounts=[(directory/'workspace','/app',False),(directory/'home','/dsh-home',False),(directory/'logs','/logs/agent',False),(ROOT/'runtime/kz','/opt/kz',True),(ROOT/'runtime/node','/opt/node',True),(ROOT/'empty-tests','/tests',True)]
  args=['create','-i','--name',name,'--label','experiment='+ROOT.name,'--user',f'{os.getuid()}:{os.getgid()}','--network',net,'--cpus','2','--memory','8g','--pids-limit','256','--cap-drop','ALL','--security-opt','no-new-privileges','-e','HOME=/dsh-home','-w','/app']
  for source,target,ro in mounts:args+=['--mount',f'type=bind,src={source},dst={target}'+(',readonly' if ro else '')]
  docker(*args,row['image_id'],'/opt/node/bin/node','/opt/kz/container-run.mjs');created=True
  actual=json.loads(docker('inspect',name,'--format','{{json .Mounts}}').stdout)
  assert all(Path(m['Source']).resolve().is_relative_to(directory.resolve()) for m in actual if m['RW'])
  assert next(m for m in actual if m['Destination']=='/tests')['RW'] is False
  save(directory/'isolation.json',dict(mounts=actual,network_internal=True,image=row['image_id']))
  with (directory/'controller.log').open('xb') as out:
   p=subprocess.Popen(['docker','start','-ai',name],stdin=subprocess.PIPE,stdout=out,stderr=out)
   p.stdin.write(json.dumps(payload).encode());p.stdin.close();payload={}
   summary['state']='solving';start=time.time()
   while p.poll() is None:
    summary.update(updated=time.time(),**progress(directory));save(directory/'health.json',summary)
    if time.time()-start>(120 if probe else 7260):
     summary['outer_timeout']=True;docker('stop','-t','3',name,check=False);break
    time.sleep(2 if probe else 10)
   p.wait(timeout=30)
  summary.update(exit_code=p.returncode,**progress(directory))
  if probe:
   assert summary['budget_stop']['reason']=='per_task_budget_exhausted',summary
   assert ledger.status()['settled_microcny']==0 and ledger.status()['reserved_microcny']==0
   summary.update(state='passed',paid_calls=0)
  else:
   docker('stop','-t','3',name,check=False)
   summary['artifact']=export_tree(directory/'workspace',directory/'final-source.tar.gz',source_only=True)
   summary['state']='grading';save(directory/'health.json',summary)
   from college_grader import grade
   report=grade(job,directory/'final-source.tar.gz',summary['artifact']['sha256'])
   summary.update(grading_state=report['grading_state'],official_success=report.get('official_success'),f2p=report.get('f2p'),state='graded' if report['grading_state']=='complete' else 'needs_attention')
   if report['grading_state']!='complete':summary['engineering_fault']='grading_failed'
   if summary['provider_stop']:summary['engineering_fault']='provider_stop'
   if p.returncode and not any(summary.get(k) for k in ['budget_stop','limit_stop','provider_stop']) and not (summary.get('agent_exit') or {}).get('timed_out'):
    summary['engineering_fault']='native_error_inspect_logs'
 except Exception as e:summary.update(state='needs_attention',engineering_fault=type(e).__name__,error=str(e)[:700].replace(key,'[REDACTED]'))
 finally:
  if created:
   docker('stop','-t','3',name,check=False)
   if docker('inspect',name,'--format','{{index .Config.Labels "experiment"}}',check=False).stdout.strip()==ROOT.name:docker('rm',name,check=False)
  if proxy:proxy.close()
  if server:server.shutdown();server.server_close()
  if network:docker('network','rm',net,check=False)
  summary.update(ended=time.time(),updated=time.time());save(directory/'summary.json',summary);save(directory/'health.json',summary)
 return summary

def validate():
 ready=read(ROOT/'ready.json',{});assert ready.get('passed'),'Preflight incomplete'
 for name,digest in ready['hashes'].items():assert sha(ROOT/name)==digest,'Changed sealed deployment: '+name
 return read(ROOT/'protocol.json')

def campaign(key):
 protocol=validate();ledger=Ledger(ROOT/'spending.sqlite',read(ROOT/'budget-profile.json'));pending=list(protocol['tasks']);results=[];active={}
 with ThreadPoolExecutor(max_workers=6) as pool:
  while pending or active:
   for future,row in list(active.items()):
    if future.done():results.append(future.result());del active[future]
   # Exact owned jobs only; individual task failures never stop unrelated tasks.
   while pending and len(active)<6 and min(shutil.disk_usage('/var/lib/docker').free,shutil.disk_usage(ROOT).free)>8*2**30:
    row=pending.pop(0);active[pool.submit(solve,row,key,ledger)]=row
   save(ROOT/'health.json',dict(state='running' if active else 'complete',updated=time.time(),pid=os.getpid(),concurrency_limit=6,active=[r['task'] for r in active.values()],pending=[r['task'] for r in pending],completed=results,budget=ledger.status()))
   if active or pending:time.sleep(10)
 save(ROOT/'summary.json',read(ROOT/'health.json'))

def launch():
 validate()
 secret=read(Path.home()/'.config/appworld-credentials/taotoken-standby.json',{})
 key=secret.get('key') or secret.get('api_key') or secret.get('apiKey');assert key,'Authorized saved credential unavailable'
 with (ROOT/'launch-once.marker').open('x') as f:f.write('HLD v8 full20, 8 CNY/task 160 total, all roles, no paid retries\n')
 with (ROOT/'supervisor.log').open('ab',buffering=0) as log:
  p=subprocess.Popen([sys.executable,__file__,'--supervise'],stdin=subprocess.PIPE,stdout=log,stderr=log,start_new_session=True)
  p.stdin.write((json.dumps({'key':key})+'\n').encode());p.stdin.close()
 save(ROOT/'launch-receipt.json',dict(pid=p.pid,started=time.time(),tasks=20,concurrency=6,budget_cny=160))
 print('Started',p.pid,flush=True)

if __name__=='__main__':
 if '--supervise' in sys.argv:campaign(json.loads(sys.stdin.readline(16384))['key'])
 else:launch()
