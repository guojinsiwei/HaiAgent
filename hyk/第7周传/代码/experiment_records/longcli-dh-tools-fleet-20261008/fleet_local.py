"""Secure one-time fleet launch and non-LLM result relay on the user's computer."""
import argparse,json,os,shlex,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
KEY='C:/Users/54177/.ssh/cubestudio_notebook'
COLLEGE_ROOT='/var/tmp/longcli-dh-tools-execution-repair3-20261008'
NODES={
 'college':('lizh639@172.16.108.236',COLLEGE_ROOT,'/mnt/sdb/home/lizh639/terminalbench-v14-setup/runtime/bin/python','college'),
 'cube0':('cubestudio_container','/mnt/lizh639/longcli-dh-tools-fleet-20261008-cube0','/mnt/lizh639/envs/swe-eval/bin/python','cube'),
 'cube1':('cubestudio_container2','/mnt/lizh639/longcli-dh-tools-fleet-20261008-cube1','/mnt/lizh639/envs/swe-eval/bin/python','cube')}
OPTIONS={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
PHASE='initialization'

class FleetOperationError(RuntimeError):
 def __init__(self,slot,reason,return_code=None):
  self.public={'node':slot,'reason':reason,'return_code':return_code}
  super().__init__(reason)

def launch_disposition(snapshot):
 if snapshot.get('launch_alive') or snapshot.get('worker',{}).get('state')=='generation_complete':
  return 'already_started'
 if snapshot.get('launch_claim_exists') or snapshot.get('launch') or snapshot.get('worker'):
  return 'inspect_existing_attempt'
 return 'not_started'
def ssh(slot,script,args='',body=None):
 host,root,py,mode=NODES[slot]
 cmd=shlex.quote(py)+' -B '+shlex.quote(root+'/'+script)+' '+args
 # A read-only SSH check MUST NOT inherit our stdin: it contains the one-time
 # credential pipeline. OpenSSH may drain it even when the remote script does
 # not read input. Only explicit payloads get a dedicated subprocess pipe.
 io={'stdin':subprocess.DEVNULL} if body is None else {'input':body}
 try:
  p=subprocess.run(['ssh','-i',KEY,'-o','BatchMode=yes','-o','ConnectTimeout=15',host,cmd],
     capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60,**io,**OPTIONS)
 except subprocess.TimeoutExpired:raise FleetOperationError(slot,'ssh_timeout') from None
 if p.returncode:raise FleetOperationError(slot,'remote_command_failed',p.returncode)
 lines=p.stdout.strip().splitlines()
 if not lines:raise FleetOperationError(slot,'missing_public_receipt')
 try:return json.loads(lines[-1])
 except (ValueError,IndexError):raise FleetOperationError(slot,'invalid_public_receipt') from None
def scp(source,target):
 p=subprocess.run(['scp','-i',KEY,'-o','BatchMode=yes','-o','ConnectTimeout=15',source,target],
    stdin=subprocess.DEVNULL,capture_output=True,timeout=180,**OPTIONS)
 if p.returncode:raise RuntimeError('artifact_transfer_failed')
def transfer(slot,row):
 host,remote,_,_=NODES[slot];job=row['job'];assert '/' not in job
 local=ROOT/'received'/job;local.mkdir(parents=True,exist_ok=True)
 receipt=local/'imported.json'
 if receipt.exists():return
 s=row['summary'];assert s['state']=='awaiting_grade' and row['artifact_exists']
 scp(host+':'+remote+'/jobs/'+job+'/final-source.tar.gz',str(local/'final-source.tar.gz'))
 import hashlib
 assert hashlib.sha256((local/'final-source.tar.gz').read_bytes()).hexdigest()==s['artifact']['sha256']
 s=dict(s,pid=None,worker_node=slot,remote_source=remote)
 (local/'summary.json').write_text(json.dumps(s,ensure_ascii=False),encoding='utf-8')
 ssh('college','fleet_import.py','--job '+shlex.quote(job)+' --prepare')
 scp(str(local/'final-source.tar.gz'),NODES['college'][0]+':'+COLLEGE_ROOT+'/jobs/'+job+'/final-source.tar.gz')
 # Publish summary LAST so the original grader never reads a partial archive.
 scp(str(local/'summary.json'),NODES['college'][0]+':'+COLLEGE_ROOT+'/jobs/'+job+'/fleet-incoming-summary.json')
 ssh('college','fleet_import.py','--job '+shlex.quote(job)+' --commit')
 receipt.write_text(json.dumps({'imported':True,'sha256':s['artifact']['sha256'],'time':time.time()}))

def bridge():
 lock=(ROOT/'relay.lock').open('a+b')
 lock.seek(0)
 if os.name=='nt':
  import msvcrt
  msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
 else:
  import fcntl
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 plan=json.loads((ROOT/'fleet-plan.json').read_text());all_jobs={'dh_tools--'+r['task'] for r in json.loads((ROOT/'protocol.json').read_text())['tasks']}
 while True:
  snapshots={};errors=[]
  for slot in NODES:
   try:snapshots[slot]=ssh(slot,'fleet_state.py','--slot '+slot)
   except Exception as e:errors.append({'node':slot,'reason':type(e).__name__})
  if 'college' not in snapshots:
   (ROOT/'relay-health.json').write_text(json.dumps({'state':'college_unreachable_not_confirmed_stopped','errors':errors,'updated':time.time()}))
   time.sleep(15);continue
  for slot in ('cube0','cube1'):
   for row in snapshots.get(slot,{}).get('jobs',[]):
    existing=next((r for r in snapshots['college']['jobs'] if r['job']==row['job'] and r.get('summary')),None)
    if existing:
     if row.get('summary') and row['summary'].get('artifact'):
      assert existing['summary'].get('artifact',{}).get('sha256')==row['summary']['artifact']['sha256']
     continue
    if row.get('summary') and row['summary'].get('state')=='awaiting_grade':
     try:transfer(slot,row)
     except Exception as e:errors.append({'node':slot,'job':row['job'],'reason':type(e).__name__})
  completed={r['job'] for r in snapshots['college']['jobs'] if r.get('summary')}
  active={r['job'] for snap in snapshots.values() for r in snap['jobs'] if r.get('alive') and not r.get('summary')}
  remote={r['job']:dict(r['health'],worker_node=slot) for slot in ('cube0','cube1')
          for r in snapshots.get(slot,{}).get('jobs',[]) if r.get('alive') and not r.get('summary')}
  for slot in ('cube0','cube1'):
   for row in snapshots.get(slot,{}).get('jobs',[]):
    if row.get('summary') and (ROOT/'received'/row['job']/'imported.json').exists():completed.add(row['job'])
  pending=all_jobs-active-completed
  terminal=not active and not pending and not errors
  workers_ended=all(s.get('worker',{}).get('state') in ('generation_complete','needs_attention') for s in snapshots.values()) and len(snapshots)==3
  failed_terminal=workers_ended and not active and bool(pending or errors)
  waiting_key=not any(s.get('worker') for s in snapshots.values()) and not active and bool(pending)
  payload={'state':'generation_complete' if terminal else 'needs_attention' if failed_terminal else 'awaiting_credentials' if waiting_key else 'running',
    'pid':snapshots['college']['worker'].get('pid'),'active':sorted(active),
    'pending':sorted(pending),'completed':sorted(completed),'errors':errors,
    'concurrency':12,'node_limits':plan['node_limits'],'remote_live':remote,
    'fleet_relay_on_local_computer':True,'mail_enabled':False}
  try:ssh('college','fleet_state.py','--publish',json.dumps(payload)+'\n')
  except Exception:
   (ROOT/'relay-health.json').write_text(json.dumps({'state':'publish_failed_not_confirmed_stopped','updated':time.time()}))
   time.sleep(15);continue
  (ROOT/'relay-health.json').write_text(json.dumps(dict(payload,updated=time.time()),ensure_ascii=False),encoding='utf-8')
  if terminal or failed_terminal:return
  time.sleep(5)

def main():
 global PHASE
 ap=argparse.ArgumentParser();ap.add_argument('--bridge',action='store_true');ap.add_argument('--check',action='store_true');args=ap.parse_args()
 if args.bridge:return bridge()
 snapshots={}
 for slot,(_,_,_,mode) in NODES.items():
  PHASE='acceptance_'+slot
  ssh(slot,'fleet_worker.py','--slot '+slot+' --mode '+mode+' --check')
  PHASE='launch_status_'+slot
  snapshots[slot]=ssh(slot,'fleet_state.py','--slot '+slot)
  if launch_disposition(snapshots[slot])=='inspect_existing_attempt':
   raise FleetOperationError(slot,'existing_attempt_requires_inspection')
 if args.check:print('{"ready":true,"nodes":3,"max_concurrency":12,"mail_enabled":false}');return
 PHASE='credential_input'
 key=sys.stdin.readline().strip()
 if not key:raise FleetOperationError('local','credential_input_empty')
 if any(c.isspace() for c in key):raise FleetOperationError('local','credential_contains_whitespace')
 launches=[]
 for slot,(_,_,_,mode) in NODES.items():
  PHASE='launch_'+slot
  if launch_disposition(snapshots[slot])=='already_started':
   launches.append({'slot':slot,'already_started':True});continue
  # Re-read immediately before mutation. Never retry an uncertain launch blindly.
  current=ssh(slot,'fleet_state.py','--slot '+slot)
  disposition=launch_disposition(current)
  if disposition=='already_started':
   launches.append({'slot':slot,'already_started':True});continue
  if disposition!='not_started':raise FleetOperationError(slot,'existing_attempt_requires_inspection')
  launches.append(ssh(slot,'fleet_worker.py','--slot '+slot+' --mode '+mode,key+'\n'))
 key=None
 prior=json.loads((ROOT/'relay-health.json').read_text()) if (ROOT/'relay-health.json').exists() else {}
 launch=json.loads((ROOT/'relay-launch.json').read_text()) if (ROOT/'relay-launch.json').exists() else {}
 if time.time()-prior.get('updated',0)>90 or not launch:
  with (ROOT/'relay-out.log').open('ab') as out,(ROOT/'relay-error.log').open('ab') as err:
   p=subprocess.Popen([sys.executable,'-B',str(Path(__file__).resolve()),'--bridge'],stdin=subprocess.DEVNULL,
       stdout=out,stderr=err,**OPTIONS)
  launch={'pid':p.pid,'time':time.time(),'model_calls':0}
  (ROOT/'relay-launch.json').write_text(json.dumps(launch))
 PHASE='complete'
 result={'started':True,'workers':launches,'relay_pid':launch['pid'],'max_concurrency':12,'mail_enabled':False,'time':time.time()}
 (ROOT/'fleet-local-launch.json').write_text(json.dumps(result),encoding='utf-8')
 print(json.dumps(result))

if __name__=='__main__':
 try:main()
 except Exception as e:
  result={'state':'needs_attention','error_type':type(e).__name__,'phase':PHASE,'time':time.time()}
  if isinstance(e,FleetOperationError):result.update(e.public)
  # Never store exception text, subprocess input, API key, or raw remote stderr.
  (ROOT/('launch-failure-'+str(time.time_ns())+'.json')).write_text(json.dumps(result),encoding='utf-8')
  print(json.dumps(result));sys.exit(1)
