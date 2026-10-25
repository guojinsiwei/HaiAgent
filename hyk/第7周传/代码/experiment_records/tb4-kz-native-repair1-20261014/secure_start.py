import getpass,json,subprocess,time,shlex,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
REMOTE='/mnt/sdb/home/lizh639/tb4-kz-native-repair1-20261014'
PY='/var/tmp/lizh639-tb4-taotoken-smoke-20261011/venv/bin/python'
SSH=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15','-i','C:/Users/54177/.ssh/cubestudio_notebook','lizh639@172.16.108.236']
def status(state,**fields):
 (ROOT/'secure-input-status.json').write_text(json.dumps(dict(state=state,time=time.time(),pid=os.getpid(),**fields)),encoding='utf8')
def precheck():
 result=subprocess.run(SSH+['env','PYTHONDONTWRITEBYTECODE=1',PY,REMOTE+'/campaign.py'],capture_output=True,timeout=60)
 if result.returncode or b'READY' not in result.stdout:
  status('precheck_failed');print(result.stderr.decode(errors='replace')[-1500:]);raise SystemExit('Source, disk or Docker precheck failed. No key requested and no model called.')
if __name__=='__main__':
 precheck()
 if '--check-only' in sys.argv:print('READY');sys.exit()
 print('Native KZ repair1: 3 development reruns, then 27 only if all 3 are engineering-clean and at least one passes.')
 print('At most 30 paid trials, one attempt per task; 3 hours each; sequential. Existing DSH is not restarted.')
 status('ready_for_key');key=getpass.getpass('TaoToken API key (hidden): ').strip()
 if not key:raise SystemExit('Empty key, not started.')
 try:
  status('submitting');result=subprocess.run(SSH+['env','PYTHONDONTWRITEBYTECODE=1',PY,REMOTE+'/campaign.py','--launch'],input=(json.dumps({'key':key})+'\n').encode(),capture_output=True,timeout=60)
  output=(result.stdout+result.stderr).decode(errors='replace').replace(key,'[REDACTED]')
 finally:key=''
 (ROOT/'launch-receipt.txt').write_text(output,encoding='utf8');print(output)
 status('launch_acknowledged' if result.returncode==0 else 'launch_unconfirmed',returncode=result.returncode)
 input('Press Enter to close...')
