import getpass,json,subprocess,time,shlex,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
REMOTE='/mnt/sdb/home/lizh639/tb4-native-kz-dsh-full30-recovery-20261014'
PY='/var/tmp/lizh639-tb4-taotoken-smoke-20261011/venv/bin/python'
SSH=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15','-i','C:/Users/54177/.ssh/cubestudio_notebook','lizh639@172.16.108.236']
def status(state,**fields):
 (ROOT/'secure-input-status.json').write_text(json.dumps(dict(state=state,time=time.time(),pid=os.getpid(),**fields)),encoding='utf8')
def precheck():
 result=subprocess.run(SSH+['env','PYTHONDONTWRITEBYTECODE=1',PY,REMOTE+'/campaign.py'],capture_output=True,timeout=60)
 if result.returncode or b'READY' not in result.stdout:
  status('precheck_failed');print(result.stderr.decode(errors='replace')[-1500:]);raise SystemExit('Source or Docker precheck failed. No key requested and no model called.')
def wait_acceptance():
 code="import json; from pathlib import Path; p=Path('"+REMOTE+"/lifecycle-health.json'); print(p.read_text() if p.exists() else '{}')"
 while True:
  r=subprocess.run(SSH+[PY,'-c',shlex.quote(code)],capture_output=True,timeout=60)
  if r.returncode:raise RuntimeError('Cannot verify offline acceptance; no launch')
  state=json.loads(r.stdout)
  if state.get('state')=='finished':
   if not state.get('passed'):raise RuntimeError('Offline lifecycle acceptance failed; no launch')
   return
  status('waiting_offline_acceptance');print('Waiting for keyless Harbor lifecycle acceptance; credential stays in this process only.',flush=True);time.sleep(15)
if __name__=='__main__':
 precheck()
 if '--check-only' in sys.argv:print('READY');sys.exit()
 print('Native KZ repair1: all 30 tasks; DSH also reruns all 30 tasks with the same fresh environment locks.')
 print('Max 120 trials (60 first pass + up to 60 engineering retries). No score gate. Finish first pass, then retry engineering failures once. Max 1 active task per arm; 3 hours per trial. Low disk pauses dispatch, keeps scheduler alive.')
 status('ready_for_key');key=getpass.getpass('TaoToken API key (hidden): ').strip()
 if not key:raise SystemExit('Empty key, not started.')
 try:
  wait_acceptance()
  status('submitting');result=subprocess.run(SSH+['env','PYTHONDONTWRITEBYTECODE=1',PY,REMOTE+'/campaign.py','--launch'],input=(json.dumps({'key':key})+'\n').encode(),capture_output=True,timeout=60)
  output=(result.stdout+result.stderr).decode(errors='replace').replace(key,'[REDACTED]')
 finally:key=''
 (ROOT/'launch-receipt.txt').write_text(output,encoding='utf8');print(output)
 status('launch_acknowledged' if result.returncode==0 else 'launch_unconfirmed',returncode=result.returncode)
 input('Press Enter to close...')
