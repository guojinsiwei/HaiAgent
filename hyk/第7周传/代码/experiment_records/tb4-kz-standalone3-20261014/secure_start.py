import getpass,json,subprocess,time,shlex,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
REMOTE='/var/tmp/lizh639-tb4-kz-standalone3-20261014'
PY='/var/tmp/lizh639-tb4-taotoken-smoke-20261011/venv/bin/python'
SSH=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15','-i','C:/Users/54177/.ssh/cubestudio_notebook','lizh639@172.16.108.236']
def status(state,**fields):
 (ROOT/'secure-input-status.json').write_text(json.dumps(dict(state=state,time=time.time(),pid=os.getpid(),**fields)),encoding='utf8')
def precheck():
 code="import sys;from pathlib import Path;sys.path.insert(0,"+repr(REMOTE)+");import resume;resume.validate();assert not (resume.ROOT/'launch-once.marker').exists();print('READY')"
 result=subprocess.run(SSH+[PY+' -c '+shlex.quote(code)],capture_output=True,timeout=45)
 if result.returncode or b'READY' not in result.stdout:
  status('precheck_failed');raise SystemExit('Acceptance not ready. Do not input a key.')
if __name__=='__main__':
 precheck()
 if '--check-only' in sys.argv:print('READY');sys.exit()
 print('Standalone KZ: payments, mvcc, uefi (sequential). Native DSH: resume not-started tasks, never rerun old results.')
 print('Same TaoToken model; 3 hours per task, no request/tool/cost cap. Server continues after PC shutdown.')
 status('ready_for_key');key=getpass.getpass('TaoToken API key (hidden): ').strip()
 if not key:raise SystemExit('Empty key, not started.')
 try:
  status('submitting');result=subprocess.run(SSH+[PY,REMOTE+'/resume.py','--launch'],input=(json.dumps({'key':key})+'\n').encode(),capture_output=True,timeout=60)
  output=(result.stdout+result.stderr).decode(errors='replace').replace(key,'[REDACTED]')
 finally:key=''
 (ROOT/'launch-receipt.txt').write_text(output,encoding='utf8');print(output)
 status('launch_acknowledged' if result.returncode==0 else 'launch_unconfirmed',returncode=result.returncode)
 input('Press Enter to close...')
