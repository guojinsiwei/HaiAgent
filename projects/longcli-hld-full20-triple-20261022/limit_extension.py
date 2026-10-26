"""Scoped resource-limit extension. No algorithm changes or new task attempts."""
import json,pathlib,sys,time,os,hashlib,subprocess,secrets,tempfile,sqlite3
ROOT=pathlib.Path(__file__).resolve().parent
RUNTIME=ROOT/'runtime/kz'
TARGETS=['61810_fs','61810_lock','61810_mmap','61810_net']
def read(p):return json.loads(p.read_text())
def save(p,value,private=False):
 q=p.with_name(p.name+'.tmp');q.write_text(json.dumps(value,indent=2));q.chmod(0o600 if private else 0o644);q.replace(p)
def replace_once(text,old,new):
 assert text.count(old)==1,(old,text.count(old));return text.replace(old,new)

def stage():
 assert ROOT.name=='longcli-hld-full20-triple-20261022'
 assert not (ROOT/'limit-adjustment.json').exists(),'already staged'
 jobs=['hld--'+t for t in TARGETS if not (ROOT/'jobs'/('hld--'+t)).exists()]
 assert jobs,'No unstarted target remains'
 plan=dict(created=time.time(),jobs=jobs,requests_per_task=800,max_output_tokens=32768,
   task_limit_microcny=24000000,campaign_limit_microcny=480000000,
   eligibility='unstarted at stage; early-run criterion <=5 minutes and <=30 requests had no match',
   algorithm='HLD v8 unchanged',paid_restart=False)
 save(ROOT/'limit-adjustment.json',plan);save(RUNTIME/'limit-adjustment.json',plan)
 entry=RUNTIME/'container-run.mjs';original=entry.read_text()
 (ROOT/'container-run.before-limit-extension.mjs').write_text(original)
 gate=r"""
// Operator-authorized resource profile for the explicitly listed unstarted jobs.
let limitExtension=null;
const limitPlan=JSON.parse(fs.readFileSync('/opt/kz/limit-adjustment.json','utf8'));
if(limitPlan.jobs.includes(bundle.spending.CAMPAIGN_BUDGET_JOB)) {
  const start=Date.now();
  while(!fs.existsSync('/opt/kz/limit-adjustment.ready.json')) {
    if(Date.now()-start>900000)throw Error('Scoped limit extension preflight unavailable; no model call made');
    await new Promise(resolve=>setTimeout(resolve,500));
  }
  limitExtension=JSON.parse(fs.readFileSync('/opt/kz/limit-adjustment.ready.json','utf8'));
  if(!limitExtension.jobs.includes(bundle.spending.CAMPAIGN_BUDGET_JOB))throw Error('Scoped limit authorization mismatch');
  Object.assign(bundle.spending,{CAMPAIGN_BUDGET_URL:new URL(bundle.spending.CAMPAIGN_BUDGET_URL).origin.replace(/:\d+$/,':'+limitExtension.port),CAMPAIGN_BUDGET_TOKEN:limitExtension.token});
  fs.writeFileSync(logs+'/effective-limits.json',JSON.stringify({requests:800,max_output_tokens:32768,task_limit_cny:24,campaign_limit_cny:480,algorithm:'HLD v8',resumed:false}));
}
"""
 patched=replace_once(original,"const cwd=process.cwd();if(cwd==='/')throw Error('Explicit task workspace required');", "const cwd=process.cwd();if(cwd==='/')throw Error('Explicit task workspace required');\n"+gate)
 patched=replace_once(patched,"for(const patch of ['config/common.patch.yml','route.patch.yml','.runtime/transport.patch.yml',...(bundle.arm==='hld-old'?['.runtime/hld-old.patch.yml']:['.runtime/kz.patch.yml']),'.runtime/hld-new-context.patch.yml'])", "for(const patch of ['config/common.patch.yml',limitExtension?'route-high-output.patch.yml':'route.patch.yml','.runtime/transport.patch.yml',...(bundle.arm==='hld-old'?['.runtime/hld-old.patch.yml']:[limitExtension?'.runtime/kz-high-limits.patch.yml':'.runtime/kz.patch.yml']),'.runtime/hld-new-context.patch.yml'])")
 temp=entry.with_suffix('.staged.mjs');temp.write_text(patched)
 subprocess.run([str(ROOT/'runtime/node/bin/node'),'--check',str(temp)],check=True)
 temp.replace(entry)
 # Re-read immediate admission state to detect a race that loaded the old entry.
 save(ROOT/'limit-stage-receipt.json',dict(jobs=jobs,at=time.time(),existing_at_end=[j for j in jobs if (ROOT/'jobs'/j).exists()]))
 print(json.dumps(dict(staged=True,jobs=jobs)))

def scoped_ledger(path,profile,jobs):
 from spending import Ledger
 ledger=Ledger(path,profile)
 # Preserve the original immutable monetary profile and every existing charge.
 # This isolated service has a narrower job allowlist and the authorized limits.
 ledger.profile={**profile,'jobs':jobs,'requests_per_task':800,'max_output_tokens':32768}
 assert ledger.limit==480000000 and ledger.profile['task_limit_microcny']==24000000
 return ledger

def preflight():
 from spending import BudgetError
 p=read(ROOT/'budget-profile.json');plan=read(ROOT/'limit-adjustment.json');job=plan['jobs'][0]
 with tempfile.TemporaryDirectory(prefix='limit-preflight-',dir=ROOT) as tmp:
  ledger=scoped_ledger(pathlib.Path(tmp)/'test.sqlite',p,plan['jobs'])
  req=dict(id='test',job=job,arm='kz',endpoint=p['endpoint'],model=p['model'],max_tokens=32768)
  assert ledger.reserve(req)['reserved_microcny']==518144
  ledger.settle(dict(id='test',tokens=0))
  for field,value,reason in [('job','hld--cs61_fa24_hog','job_not_authorized'),('max_tokens',32769,'invalid_output_reservation')]:
   try:ledger.reserve({**req,field:value,'id':'invalid'})
   except BudgetError as e:assert e.reason==reason
   else:raise AssertionError('Invalid request admitted')
  with ledger.db() as db:
   for i in range(798):db.execute('INSERT INTO calls VALUES (?,?,?,?,?,?,?)',(str(i),job,'kz',0,0,'settled',time.time()))
  ledger.reserve({**req,'id':'800th'});ledger.settle(dict(id='800th',tokens=0))
  try:ledger.reserve({**req,'id':'801st'})
  except BudgetError as e:assert e.reason=='per_task_request_limit'
  else:raise AssertionError('Request ceiling bypassed')
  with ledger.db() as db:
   db.execute('DELETE FROM calls');db.execute('INSERT INTO calls VALUES (?,?,?,?,?,?,?)',('past',job,'kz',23900000,23900000,'settled',time.time()))
  try:ledger.reserve({**req,'id':'over24'})
  except BudgetError as e:assert e.reason=='per_task_budget_exhausted'
  else:raise AssertionError('Money ceiling bypassed')
 shared=(RUNTIME/'shared-budget.mjs').read_text().replace('maxTokens:16384','maxTokens:32768').replace('state.requests>=400','state.requests>=800').replace('requests:400,tools:600','requests:800,tools:600')
 assert 'state.requests>=800' in shared and 'maxTokens:32768' in shared
 (RUNTIME/'shared-budget-high.mjs').write_text(shared)
 route=(RUNTIME/'route.patch.yml').read_text().replace('maxTokens: 16384','maxTokens: 32768').replace('/opt/kz/shared-budget.mjs','/opt/kz/shared-budget-high.mjs')
 (RUNTIME/'route-high-output.patch.yml').write_text(route)
 kz=(RUNTIME/'.runtime/kz.patch.yml').read_text().replace('maxRequests: 400','maxRequests: 800').replace('maxOutputTokens: 16384','maxOutputTokens: 32768')
 assert 'limitCny: 24' in kz and 'maxTools: 600' in kz and 'wallSeconds: 7200' in kz
 (RUNTIME/'.runtime/kz-high-limits.patch.yml').write_text(kz)
 context=(RUNTIME/'.runtime/hld-new-context.patch.yml').read_text().replace('headroomTokens: 16384','headroomTokens: 32768')
 (RUNTIME/'.runtime/hld-high-context.patch.yml').write_text(context)
 entry=RUNTIME/'container-run.mjs';text=entry.read_text()
 text=replace_once(text,"'.runtime/hld-new-context.patch.yml'])", "limitExtension?'.runtime/hld-high-context.patch.yml':'.runtime/hld-new-context.patch.yml'])")
 tmp=entry.with_suffix('.context.mjs');tmp.write_text(text)
 subprocess.run([str(ROOT/'runtime/node/bin/node'),'--check',str(tmp)],check=True);tmp.replace(entry)
 subprocess.run([str(ROOT/'runtime/node/bin/node'),'--check',str(RUNTIME/'shared-budget-high.mjs')],check=True)
 save(ROOT/'limit-preflight.json',dict(passed=True,model_calls=0,checks=['32768 output reserved at full upper bound','unauthorized job refused','32769 output refused','800th attempt allowed','801st refused','24 CNY retained','original monetary ledger unchanged','600 tools and 7200 seconds retained'],time=time.time()))
 print('Offline ledger preflight passed; no model calls')

def service():
 from spending import server_for
 plan=read(ROOT/'limit-adjustment.json');profile=read(ROOT/'budget-profile.json')
 assert read(ROOT/'limit-preflight.json')['passed']
 ledger=scoped_ledger(ROOT/'spending.sqlite',profile,plan['jobs'])
 token=secrets.token_urlsafe(32);server=server_for(ledger,token,host='0.0.0.0',port=0)
 # Each new task has a dedicated internal Docker gateway. A host service on all
 # interfaces is reached through that task's existing gateway, never an external API.
 ready=dict(jobs=plan['jobs'],port=server.server_port,token=token,pid=os.getpid())
 save(ROOT/'limit-service.private.json',ready,True)
 server.serve_forever()

def activate():
 assert read(ROOT/'limit-preflight.json')['passed']
 if not (ROOT/'limit-service.private.json').exists():
  with (ROOT/'limit-service.log').open('ab',buffering=0) as log:
   proc=subprocess.Popen([sys.executable,__file__,'service'],stdout=log,stderr=log,start_new_session=True)
  for _ in range(100):
   if (ROOT/'limit-service.private.json').exists():break
   assert proc.poll() is None,'service exited';time.sleep(.1)
 ready=read(ROOT/'limit-service.private.json')
 # Entry uses the original job's internal gateway with the new service port.
 # Validate HTTP authorization/status locally before releasing any task.
 import urllib.request
 request=urllib.request.Request('http://127.0.0.1:'+str(ready['port'])+'/status',data=b'{}',headers={'Authorization':'Bearer '+ready['token'],'Content-Type':'application/json'})
 with urllib.request.urlopen(request,timeout=5) as r:assert json.load(r)['limit_microcny']==480000000
 running=[]
 for q in (ROOT/'jobs').glob('*/health.json'):
  h=read(q)
  if h.get('state')=='solving':running.append(h['container'])
 assert running,'No active container available for internal-network status probe'
 container=running[0]
 networks=json.loads(subprocess.check_output(['docker','inspect',container,'--format','{{json .NetworkSettings.Networks}}'],text=True))
 network=next(iter(networks.values()))
 gateway=json.loads(subprocess.check_output(['docker','network','inspect',network['NetworkID']],text=True))[0]['IPAM']['Config'][0]['Gateway']
 probe="const fs=require('fs'); const c=JSON.parse(fs.readFileSync(0,'utf8')); fetch(c.url,{method:'POST',headers:{Authorization:'Bearer '+c.token,'Content-Type':'application/json'},body:'{}'}).then(async r=>{const x=await r.json(); if(r.status!==200||x.limit_microcny!==480000000)process.exit(2); console.log('internal-network budget status OK');}).catch(()=>process.exit(3));"
 result=subprocess.run(['docker','exec','-i',container,'/opt/node/bin/node','-e',probe],input=json.dumps(dict(url='http://'+gateway+':'+str(ready['port'])+'/status',token=ready['token'])),capture_output=True,text=True,timeout=20)
 assert result.returncode==0,'Internal-network service preflight failed'
 old=read(ROOT/'ready.json');save(ROOT/'ready.before-limit-extension.json',old)
 protocol=read(ROOT/'protocol.json');protocol['resource_limit_overrides']={job:dict(requests_per_task=800,max_output_tokens=32768,task_budget_cny=24,reason='user_matched_historical_limits_for_unstarted_tasks') for job in ready['jobs']}
 save(ROOT/'protocol.json',protocol)
 for rel in ['protocol.json','runtime/kz/container-run.mjs','runtime/kz/shared-budget-high.mjs','runtime/kz/route-high-output.patch.yml','runtime/kz/.runtime/kz-high-limits.patch.yml','runtime/kz/.runtime/hld-high-context.patch.yml','runtime/kz/limit-adjustment.json','limit_extension.py']:
  old['hashes'][rel]=hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()
 old['limit_extension']=dict(jobs=ready['jobs'],preflight='limit-preflight.json',monetary_limits_unchanged=True)
 save(ROOT/'ready.json',old)
 save(RUNTIME/'limit-adjustment.ready.json',ready,True)
 save(ROOT/'limit-activation.json',dict(jobs=ready['jobs'],pid=ready['pid'],port=ready['port'],time=time.time(),paid_restart=False,task_limit_cny=24,campaign_limit_cny=480))
 print(json.dumps(dict(activated=True,jobs=ready['jobs'],pid=ready['pid'])))

if __name__=='__main__':globals()[sys.argv[1]]()
