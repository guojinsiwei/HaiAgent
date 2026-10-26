"""One-shot experiment dependency queue. Credential stays in process memory."""
import json,os,sys,time,subprocess
from pathlib import Path
from storage import atomic_json
ROOT=Path(__file__).resolve().parent
DSH=ROOT.parent/'tb2-kz-dsh-transport1-20261017'
PARENT=ROOT.parent/'tb2-kz-dsh-repair7-20261017'
def check():
 import campaign
 campaign.precheck()
 result=subprocess.run([str(DSH/'venv/bin/python'),'-c','import campaign; campaign.validate()'],cwd=DSH,capture_output=True)
 if result.returncode:raise RuntimeError('DSH sealed deployment verification failed')
 if (ROOT/'relaunch-once.marker').exists():raise RuntimeError('Already queued')
 print('READY: native three plus dependent DSH one',flush=True)
def run_command(root,args,key=None):
 env=dict(os.environ);env.pop('TAOTOKEN_API_KEY',None)
 x=subprocess.run([str(root/'venv/bin/python'),str(root/args[0]),*args[1:]],cwd=root,env=env,input=(json.dumps({'key':key})+'\n').encode() if key else None,capture_output=True,timeout=120)
 if x.returncode:raise RuntimeError(args[0]+' failed; inspect sealed deployment before retry')
 return x.stdout.decode(errors='replace')
def worker():
 key=os.environ.pop('TAOTOKEN_API_KEY');state=dict(native='pending',dsh='pending',paid_trials_authorized=4)
 def save():atomic_json(ROOT/'relaunch-status.json',dict(state,updated_epoch=time.time()))
 try:
  state['native_ack']=run_command(ROOT,['campaign.py','--launch'],key);state['native']='started';state['dsh']='waiting_for_parent';save()
  while True:
   p=json.loads((PARENT/'admissions.json').read_text())
   if p.get('state')=='finished' and not p.get('active'):break
   time.sleep(30)
  state['budget_ack']=run_command(DSH,['prepare_transport.py','--finalize']);save()
  run_command(DSH,['seal.py'])
  state['dsh_ack']=run_command(DSH,['campaign.py','--launch'],key);state['dsh']='started';save()
 except Exception as e:
  state['error_type']=type(e).__name__;state['needs_inspection']=True;save();raise RuntimeError('Relaunch stopped safely; inspect status') from None
 finally:key=''
def launch():
 check();bundle=json.loads(sys.stdin.readline());key=bundle.pop('key')
 if not isinstance(key,str) or not key.strip():raise ValueError('Fresh key required')
 with (ROOT/'relaunch-once.marker').open('x') as f:f.write(str(time.time()))
 with (ROOT/'relaunch.log').open('xb') as log:
  p=subprocess.Popen([sys.executable,__file__,'--worker'],cwd=ROOT,env=dict(os.environ,TAOTOKEN_API_KEY=key,PYTHONDONTWRITEBYTECODE='1'),stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
 time.sleep(3)
 if p.poll() is not None:raise RuntimeError('Queue failed; inspect before retry')
 print(json.dumps(dict(pid=p.pid,native_trials=3,dsh_trials=1,dsh_waits_for_parent=True,credential_saved=False)))
if __name__=='__main__':worker() if '--worker' in sys.argv else launch() if '--launch' in sys.argv else check()
